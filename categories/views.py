from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from categories.forms import CategoryForm
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
        enough, since gunicorn runs several threads per worker — can both pass
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
