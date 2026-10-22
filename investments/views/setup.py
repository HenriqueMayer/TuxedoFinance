# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Guided holdings and product/asset configuration lifecycle."""

from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.text import format_lazy
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.http import require_POST, require_http_methods
from django.views.generic import CreateView, DeleteView, TemplateView, UpdateView
from banking.models import Bank
from investments.forms import AssetForm, InvestmentProductForm
from investments.forms import GuidedInvestmentForm
from investments.models import Asset, InvestmentProduct
from investments.services import create_guided_investment
from core.navigation import ReturnContextMixin, return_url, with_return_url


@login_required
@require_http_methods(['GET', 'POST'])
def guided_investment(request):
    form = GuidedInvestmentForm(request.POST or None, user=request.user)
    destination = return_url(request, reverse('investments:list'))
    if request.method == 'POST' and form.is_valid():
        try:
            product, asset = create_guided_investment(request.user, form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            if isinstance(error, IntegrityError):
                form.add_error(None, _('The institution or investment already exists. Review the configuration.'))
            else:
                mapping = {'bank': 'institution', 'name': 'name', 'code': 'code'}
                for field, errors in getattr(error, 'message_dict', {'__all__': error.messages}).items():
                    for message in errors:
                        form.add_error(mapping.get(field, field) if mapping.get(field, field) in form.fields else None, message)
        else:
            messages.success(request, _('Investment added. Existing holdings were recorded without a bank payment.'))
            return redirect(with_return_url(reverse('investments:position_detail', args=[product.pk, asset.pk]), destination))
    return render(request, 'investments/guided_form.html', {'form': form, 'return_url': destination})


def _investment_setup(user):
    has_bank = Bank.objects.filter(user=user).exists()
    has_products = InvestmentProduct.objects.filter(user=user, bank__user=user).exists()
    has_assets = Asset.objects.filter(user=user, is_archived=False).exists()
    return {
        'has_bank': has_bank,
        'has_products': has_products,
        'has_assets': has_assets,
        'setup_complete': has_bank and has_products and has_assets,
    }


class InvestmentSettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'investments/settings/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_investment_setup(self.request.user))
        context['products'] = InvestmentProduct.objects.filter(
            user=self.request.user, bank__user=self.request.user
        ).select_related('bank').annotate(operation_count=Count('operations')).order_by('bank__name', 'bank_id', 'name')
        assets = list(Asset.objects.filter(user=self.request.user).annotate(
            operation_count=Count('operations')
        ))
        context['assets'] = [asset for asset in assets if not asset.is_archived]
        context['archived_assets'] = [asset for asset in assets if asset.is_archived]
        context['show_archived_assets'] = any(
            str(asset.pk) == self.request.GET.get('archived') for asset in context['archived_assets']
        )
        return context


class SetupFormMixin(ReturnContextMixin, LoginRequiredMixin):
    template_name = 'investments/setup_form.html'
    success_url = reverse_lazy('investments:settings')
    entity_label = ''
    setup_description = ''
    duplicate_field = 'name'
    duplicate_message = gettext_lazy('This item already exists.')

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        action = gettext_lazy('Edit') if self.object else gettext_lazy('Add')
        context['setup_title'] = format_lazy('{} {}', action, self.entity_label)
        context['setup_description'] = self.setup_description
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        try:
            with transaction.atomic():
                return super().form_valid(form)
        except IntegrityError:
            form.add_error(self.duplicate_field, self.duplicate_message)
            return self.form_invalid(form)


class ProductFormMixin(SetupFormMixin):
    model = InvestmentProduct
    form_class = InvestmentProductForm
    entity_label = gettext_lazy('investment product')
    setup_description = gettext_lazy('Name a product and assign it to a bank registered in Accounts.')
    duplicate_message = gettext_lazy('This bank already has a product with this name.')

    def get_queryset(self):
        return super().get_queryset().filter(bank__user=self.request.user)


class InvestmentProductCreateView(ProductFormMixin, SuccessMessageMixin, CreateView):
    success_message = gettext_lazy('Investment product "%(name)s" created.')


class InvestmentProductUpdateView(ProductFormMixin, SuccessMessageMixin, UpdateView):
    success_message = gettext_lazy('Investment product "%(name)s" updated.')


class AssetFormMixin(SetupFormMixin):
    model = Asset
    form_class = AssetForm
    entity_label = gettext_lazy('asset')
    setup_description = gettext_lazy('Class describes what it is; currency describes how its unit price is quoted.')
    duplicate_field = 'code'
    duplicate_message = gettext_lazy('You already have an asset with this code.')


class AssetCreateView(AssetFormMixin, SuccessMessageMixin, CreateView):
    success_message = gettext_lazy('Asset "%(name)s" created.')


class AssetUpdateView(AssetFormMixin, SuccessMessageMixin, UpdateView):
    success_message = gettext_lazy('Asset "%(name)s" updated.')


class SetupDeleteView(ReturnContextMixin, LoginRequiredMixin, DeleteView):
    template_name = 'investments/settings/confirm_delete_entity.html'
    success_url = reverse_lazy('investments:settings')
    entity_label = ''

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['entity_label'] = self.entity_label
        if isinstance(self.object, Asset):
            context['delete_warning'] = self.object.deletion_block_reason
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, _('This item has an opening position or investment history and cannot be deleted.'))
            return redirect(self.get_return_url())
        messages.success(
            self.request,
            _('%(entity)s deleted.') % {'entity': self.entity_label.title()},
        )
        return response


class InvestmentProductDeleteView(SetupDeleteView):
    model = InvestmentProduct
    context_object_name = 'entity'
    entity_label = gettext_lazy('investment product')

    def get_queryset(self):
        return super().get_queryset().filter(bank__user=self.request.user)


class AssetDeleteView(SetupDeleteView):
    model = Asset
    context_object_name = 'entity'
    entity_label = gettext_lazy('asset')


def _set_asset_archived(request, pk, archived):
    asset = get_object_or_404(Asset, pk=pk, user=request.user)
    asset.is_archived = archived
    asset.save(update_fields=['is_archived', 'updated_at'])
    message = (
        _('Asset "%(name)s" archived. Its positions and history remain available.') if archived
        else _('Asset "%(name)s" restored. It is available for new operations.')
    )
    messages.success(request, message % {'name': asset.name})
    url = reverse('investments:settings')
    if archived:
        url += '?' + urlencode({'archived': asset.pk})
    # Native submissions land on the changed asset; same-page HTMX keeps focus
    # on its stable action button, which becomes Restore after archiving.
    return redirect(f'{url}#asset-{asset.pk}')


@login_required
@require_POST
def archive_asset(request, pk):
    return _set_asset_archived(request, pk, True)


@login_required
@require_POST
def restore_asset(request, pk):
    return _set_asset_archived(request, pk, False)
