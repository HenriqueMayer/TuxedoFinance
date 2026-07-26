from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from categories.forms import CategoryForm
from categories.models import Category


class CategoryListView(LoginRequiredMixin, ListView):
    """List the logged-in user's categories (PRD 4.2.1, FR10, FR12)."""

    model = Category
    template_name = 'categories/list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user).select_related('parent_category')


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


class CategoryCreateView(SuccessMessageMixin, CategoryFormMixin, CreateView):
    """Create a category owned by the logged-in user (PRD 4.2.2)."""

    success_message = 'Category "%(name)s" created.'

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class CategoryUpdateView(SuccessMessageMixin, CategoryFormMixin, UpdateView):
    """Update one of the logged-in user's own categories (PRD 4.2.3)."""

    success_message = 'Category "%(name)s" updated.'


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
                f'"{name}" cannot be deleted because it is still '
                'used by existing transactions.',
            )
            return redirect('categories:list')
        messages.success(self.request, f'Category "{name}" deleted.')
        return response
