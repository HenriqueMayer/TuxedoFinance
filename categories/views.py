import csv
import io

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from categories.forms import CategoryForm, CategoryImportForm
from categories.models import Category


class CategoryListView(LoginRequiredMixin, ListView):
    """List and filter the logged-in user's categories (FR10, FR12)."""

    model = Category
    template_name = 'categories/list.html'
    context_object_name = 'categories'

    def _selected_level(self):
        level = self.request.GET.get('level')
        return level if level in ('top', 'sub') else ''

    def get_queryset(self):
        queryset = Category.objects.filter(user=self.request.user).select_related(
            'parent_category'
        )

        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(name__icontains=search)

        level = self._selected_level()
        if level:
            queryset = queryset.filter(parent_category__isnull=level == 'top')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['selected_level'] = self._selected_level()
        return context


class CategoryFormMixin(LoginRequiredMixin):
    """Shared plumbing for the create/update CBVs (per-user isolation, PRD R3)."""

    model = Category
    form_class = CategoryForm
    template_name = 'categories/form.html'
    success_url = reverse_lazy('categories:list')

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        """Last line of defence for the unique-name constraint.

        The form already rejects duplicates, but that check and the INSERT are
        not atomic: two submits of the same name — a double-clicked button is
        enough, since two overlapping submissions can both pass
        validation before either writes. The loser hits the constraint in the
        database, and without this it surfaces as a 500.
        """
        try:
            return super().form_valid(form)
        except IntegrityError:
            form.add_error('name', _('You already have a category with this name.'))
            return self.form_invalid(form)


# `CategoryFormMixin` must precede `SuccessMessageMixin` in the bases below.
# Its `form_valid` can turn a save into a *failure*, and the success message
# has to stay unwritten when it does — which only holds while the exception
# propagates through `SuccessMessageMixin.form_valid` instead of being caught
# underneath it. Reversing the two announces "created" over a form that is
# still showing an error.
class CategoryCreateView(CategoryFormMixin, SuccessMessageMixin, CreateView):
    """Create a category owned by the logged-in user (PRD 4.2.2)."""

    success_message = gettext_lazy('Category "%(name)s" created.')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class CategoryUpdateView(CategoryFormMixin, SuccessMessageMixin, UpdateView):
    """Update one of the logged-in user's own categories (PRD 4.2.3)."""

    success_message = gettext_lazy('Category "%(name)s" updated.')


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a category with confirmation (PRD 4.2.4).

    `Transaction.category` uses `on_delete=PROTECT` (PRD §8.5), so deleting
    a category still referenced by a transaction raises `ProtectedError`.
    Catch it here and show a friendly message instead of a 500.
    """

    model = Category
    template_name = 'categories/confirm_delete.html'
    context_object_name = 'category'
    success_url = reverse_lazy('categories:list')

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def form_valid(self, form):
        name = self.object.name
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                _('"%(name)s" cannot be deleted because it is still used by existing transactions.')
                % {'name': name},
            )
            return redirect('categories:list')
        messages.success(
            self.request,
            _('Category "%(name)s" deleted.') % {'name': name},
        )
        return response


@login_required
def export_categories(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="categories.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(('name', 'transaction_type', 'parent_category'))
    categories = Category.objects.filter(user=request.user).select_related('parent_category')
    for category in categories:
        writer.writerow((
            category.name,
            category.transaction_type or '',
            category.parent_category.name if category.parent_category else '',
        ))
    return response


def _read_category_csv(uploaded_file):
    try:
        content = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError(_('The CSV file must use UTF-8 encoding.')) from error

    reader = csv.DictReader(io.StringIO(content))
    expected_columns = ['name', 'transaction_type', 'parent_category']
    if reader.fieldnames != expected_columns:
        raise ValueError(
            _('The CSV header must be: name,transaction_type,parent_category.')
        )

    rows = []
    names = set()
    valid_types = {choice for choice, _label in Category.TransactionType.choices}
    for line_number, row in enumerate(reader, start=2):
        name = (row['name'] or '').strip()
        category_type = (row['transaction_type'] or '').strip().upper()
        parent_name = (row['parent_category'] or '').strip()
        if not name and not category_type and not parent_name:
            continue
        if not name:
            raise ValueError(_('Line %(line)s has no category name.') % {'line': line_number})
        if len(name) > 100 or len(parent_name) > 100:
            raise ValueError(_('Line %(line)s contains a name longer than 100 characters.') % {'line': line_number})
        if category_type and category_type not in valid_types:
            raise ValueError(
                _('Line %(line)s has an invalid transaction type.') % {'line': line_number}
            )
        if name in names:
            raise ValueError(_('The category "%(name)s" appears more than once.') % {'name': name})
        if name == parent_name:
            raise ValueError(_('The category "%(name)s" cannot be its own parent.') % {'name': name})
        names.add(name)
        rows.append((name, category_type, parent_name))
    return rows


@login_required
@require_http_methods(['GET', 'POST'])
def import_categories(request):
    form = CategoryImportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        try:
            rows = _read_category_csv(form.cleaned_data['file'])
            existing = {
                category.name: category
                for category in Category.objects.filter(user=request.user)
            }
            available_names = set(existing) | {name for name, _type, _parent in rows}
            missing_parents = sorted({
                parent_name
                for _name, _type, parent_name in rows
                if parent_name and parent_name not in available_names
            })
            if missing_parents:
                raise ValueError(
                    _('Parent category not found: %(name)s.') % {'name': missing_parents[0]}
                )

            parent_by_name = {name: parent for name, _type, parent in rows if parent}
            for name in parent_by_name:
                visited = set()
                current = name
                while current in parent_by_name:
                    if current in visited:
                        raise ValueError(_('The CSV contains a circular category hierarchy.'))
                    visited.add(current)
                    current = parent_by_name[current]

            created = 0
            with transaction.atomic():
                categories = dict(existing)
                for name, category_type, _parent_name in rows:
                    if name not in categories:
                        categories[name] = Category.objects.create(
                            user=request.user,
                            name=name,
                            transaction_type=category_type or None,
                        )
                        created += 1
                for name, _category_type, parent_name in rows:
                    category = categories[name]
                    if name in existing or not parent_name:
                        continue
                    category.parent_category = categories[parent_name]
                    category.save(update_fields=['parent_category', 'updated_at'])
        except ValueError as error:
            form.add_error('file', error)
        else:
            skipped = len(rows) - created
            messages.success(
                request,
                _('%(created)s categories imported; %(skipped)s existing categories skipped.')
                % {'created': created, 'skipped': skipped},
            )
            return redirect('categories:list')

    return render(request, 'categories/import.html', {'form': form})
