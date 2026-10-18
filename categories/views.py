import csv
import io
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, IntegerField, ProtectedError, Q, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from categories.forms import CATEGORY_CSV_MAX_BYTES, CATEGORY_CSV_MAX_ROWS, CategoryForm, CategoryImportForm
from categories.models import Category, validate_parent_hierarchy
from core.csv import export_row
from core.navigation import ReturnContextMixin, return_url


class CategoryListView(LoginRequiredMixin, ListView):
    """List and filter the logged-in user's categories (FR10, FR12)."""

    model = Category
    template_name = 'categories/list.html'
    context_object_name = 'categories'

    def _selected_level(self):
        level = self.request.GET.get('level')
        return level if level in ('top', 'sub') else ''

    def _selected_type(self):
        kind = self.request.GET.get('type', '')
        return kind if kind in (*Category.TransactionType.values, 'unclassified') else ''

    def _owned_queryset(self):
        return Category.objects.filter(user=self.request.user).select_related(
            'parent_category'
        ).annotate(
            usage_count=Count('transactions', filter=Q(transactions__user=self.request.user)),
            group_name=Coalesce('parent_category__name', 'name'),
            hierarchy_order=Case(When(parent_category__isnull=True, then=Value(0)), default=Value(1), output_field=IntegerField()),
        ).order_by('group_name', 'hierarchy_order', 'name')

    def get_queryset(self):
        queryset = self._owned_queryset()
        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(name__icontains=search)

        level = self._selected_level()
        if level:
            queryset = queryset.filter(parent_category__isnull=level == 'top')

        selected_type = self._selected_type()
        if selected_type in Category.TransactionType.values:
            queryset = queryset.filter(transaction_type=selected_type)
        elif selected_type == 'unclassified':
            queryset = queryset.filter(Q(transaction_type__isnull=True) | Q(transaction_type=''))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['selected_level'] = self._selected_level()
        context['selected_type'] = self._selected_type()
        context['has_filters'] = bool(context['search_query'] or context['selected_level'] or context['selected_type'])
        context['has_categories'] = Category.objects.filter(user=self.request.user).exists()
        # Matching descendants retain owned ancestors as navigation context,
        # not extra matches. Never infer or expose a foreign parent relationship.
        categories = list(context['categories'])
        context['result_count'] = len(categories)
        matched_ids = {category.pk for category in categories}
        if context['has_filters'] and categories:
            owned = {category.pk: category for category in self._owned_queryset()}
            visible = set(matched_ids)
            for category in categories:
                parent_id = category.parent_category_id
                while parent_id in owned and parent_id not in visible:
                    visible.add(parent_id)
                    parent_id = owned[parent_id].parent_category_id
            categories = [category for category in owned.values() if category.pk in visible]
        visible_ids = {category.pk for category in categories}
        for category in categories:
            category.display_parent_name = category.parent_category.name if (
                category.parent_category_id and category.parent_category.user_id == self.request.user.pk
            ) else ''
        children = defaultdict(list)
        roots = []
        for category in categories:
            if category.parent_category_id in visible_ids:
                children[category.parent_category_id].append(category)
            else:
                roots.append(category)
        groups, visited = [], set()
        for category in [*roots, *categories]:
            pending = [(category, groups)]
            while pending:
                current, siblings = pending.pop()
                if current.pk in visited:
                    continue
                visited.add(current.pk)
                group = {'category': current, 'children': [], 'context_only': current.pk not in matched_ids,
                         'expanded': context['has_filters']}
                siblings.append(group)
                pending.extend((child, group['children']) for child in reversed(children[current.pk]))
        context['category_groups'] = groups
        context['has_category_groups'] = any(group['children'] for group in groups)
        return context


class CategoryFormMixin(ReturnContextMixin, LoginRequiredMixin):
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

    def get_initial(self):
        initial = super().get_initial()
        parent_id = self.request.GET.get('parent', '')
        if parent_id.isdigit() and not getattr(self, 'object', None):
            parent = Category.objects.filter(pk=parent_id, user=self.request.user, parent_category__isnull=True).first()
            if parent is not None:
                initial.update(parent_category=parent.pk, transaction_type=parent.transaction_type)
        return initial

    def form_valid(self, form):
        """Last line of defence for the unique-name constraint.

        The form already rejects duplicates, but that check and the INSERT are
        not atomic: two submits of the same name — a double-clicked button is
        enough, since two overlapping submissions can both pass
        validation before either writes. The loser hits the constraint in the
        database, and without this it surfaces as a 500.
        """
        try:
            # Recheck inside SQLite's write transaction: overlapping hierarchy
            # edits must not validate against the same stale parent graph.
            with transaction.atomic():
                form.instance.full_clean()
                return super().form_valid(form)
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
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


class CategoryDeleteView(ReturnContextMixin, LoginRequiredMixin, DeleteView):
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
                _('"%(name)s" cannot be deleted because it is still used by existing transactions or budgets.')
                % {'name': name},
            )
            return redirect(self.get_return_url())
        messages.success(
            self.request,
            _('Category "%(name)s" deleted.') % {'name': name},
        )
        return response


@login_required
@require_http_methods(['GET', 'POST'])
def delete_all_categories(request):
    """Confirm and atomically delete every unused category owned by the user."""
    categories = Category.objects.filter(user=request.user)
    category_count = categories.count()
    destination = return_url(request, reverse('categories:list'))

    if request.method == 'POST':
        if categories.filter(Q(transactions__isnull=False) | Q(transaction_splits__isnull=False) | Q(budgets__isnull=False)).exists():
            messages.error(
                request,
                _('Categories cannot be deleted while they are used by existing transactions or budgets.'),
            )
            return redirect(destination)

        with transaction.atomic():
            categories.delete()
        messages.success(request, _('All categories deleted.'))
        return redirect(destination)

    return render(
        request,
        'categories/confirm_delete_all.html',
        {'category_count': category_count, 'return_url': destination},
    )


@login_required
def export_categories(request):
    spreadsheet = request.GET.get('format') == 'spreadsheet'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = 'categories-spreadsheet.csv' if spreadsheet else 'categories.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(('name', 'transaction_type', 'parent_category'))
    categories = Category.objects.filter(user=request.user).select_related('parent_category')
    for category in categories:
        writer.writerow(export_row((
            category.name,
            category.transaction_type or '',
            category.parent_category.name if category.parent_category else '',
        ), spreadsheet=spreadsheet))
    return response


def _read_category_csv(uploaded_file):
    try:
        content = uploaded_file.read(CATEGORY_CSV_MAX_BYTES + 1)
        if len(content) > CATEGORY_CSV_MAX_BYTES:
            raise ValueError(_('The category CSV must be no larger than 2 MiB.'))
        content = content.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError(_('The CSV file must use UTF-8 encoding.')) from error

    reader = csv.reader(io.StringIO(content, newline=''), strict=True)
    expected_columns = ['name', 'transaction_type', 'parent_category']
    if next(reader, None) != expected_columns:
        raise ValueError(
            _('The CSV header must be: name,transaction_type,parent_category.')
        )

    rows = []
    names = set()
    valid_types = {choice for choice, _label in Category.TransactionType.choices}
    for line_number, row in enumerate(reader, start=2):
        if line_number > CATEGORY_CSV_MAX_ROWS + 1:
            raise ValueError(_('Import at most 500 category rows per CSV file.'))
        # Entirely empty physical lines are harmless, but still count toward
        # the bounded record budget. Every actual record needs three cells.
        if not row:
            continue
        if len(row) != len(expected_columns):
            raise ValueError(_('Line %(line)s must contain exactly three columns.') % {'line': line_number})
        name, category_type, parent_name = (value.strip() for value in row)
        category_type = category_type.upper()
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
        names.add(name)
        rows.append((name, category_type, parent_name))
    return rows


@login_required
@require_http_methods(['GET', 'POST'])
def import_categories(request):
    destination = return_url(request, reverse('categories:list'))
    form = CategoryImportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        try:
            rows = _read_category_csv(form.cleaned_data['file'])
            created = 0
            with transaction.atomic():
                existing = {
                    category.name: category
                    for category in Category.objects.filter(user=request.user)
                }
                available_names = set(existing) | {name for name, _type, _parent in rows}
                missing_parents = sorted({
                    parent_name for _name, _type, parent_name in rows
                    if parent_name and parent_name not in available_names
                })
                if missing_parents:
                    raise ValueError(_('Parent category not found: %(name)s.') % {'name': missing_parents[0]})
                owned_names = {category.pk: category.name for category in existing.values()}
                parent_by_name = {
                    name: owned_names.get(category.parent_category_id, category.parent_category_id)
                    for name, category in existing.items()
                }
                # Existing names are skipped, so validate their real parents,
                # not hypothetical replacements supplied in the imported rows.
                parent_by_name.update({name: parent or None for name, _type, parent in rows if name not in existing})
                for name, _type, parent_name in rows:
                    if name not in existing:
                        validate_parent_hierarchy(name, parent_name or None, parent_by_name)
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
        except (ValueError, csv.Error) as error:
            if isinstance(error, csv.Error):
                error = _('The category CSV is malformed. Check its quoting and row structure.')
            form.add_error('file', error)
        except ValidationError as error:
            form.add_error('file', error.messages)
        else:
            skipped = len(rows) - created
            messages.success(
                request,
                _('%(created)s categories imported; %(skipped)s existing categories skipped.')
                % {'created': created, 'skipped': skipped},
            )
            return redirect(destination)

    return render(request, 'categories/import.html', {'form': form, 'return_url': destination})
