# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Operation entry, funding and yield controls."""

from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from core.dates import configure_date_fields
from banking.models import BankAccount, LoyaltyProgram
from banking.services import MissingExchangeRate, convert
from accounts.models import UserPreference
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import YIELD_INPUT_AMOUNT, YIELD_INPUT_ENDING_BALANCE, calculate_monetary_yield
from ._styles import INPUT_CLASSES


class InvestmentSelect(forms.Select):
    """Expose scoped asset metadata to the progressive operation form."""

    choice_data = None

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if self.choice_data and value:
            option['attrs'].update(self.choice_data.get(str(value), {}))
        return option


class InvestmentForm(forms.ModelForm):
    funding_source = forms.ChoiceField(
        choices=(('', _('Choose a funding source')), ('ACCOUNT', _('Bank account')),
                 ('POINTS', _('Loyalty program'))),
        required=False,
        label=_('Fund this deposit with'),
    )
    yield_input_mode = forms.ChoiceField(
        choices=(
            (YIELD_INPUT_ENDING_BALANCE, _('Use the final balance')),
            (YIELD_INPUT_AMOUNT, _('Enter the yield amount')),
        ),
        initial=None,
        required=False,
        widget=forms.RadioSelect,
        label=_('How to enter the yield'),
        help_text=_('Choose the final balance to calculate the yield, or enter the yield directly.'),
    )
    ending_balance = forms.DecimalField(
        required=False,
        max_digits=16,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
        label=_('New investment balance'),
        help_text=_('Total balance after the yield is credited.'),
    )

    class Meta:
        model = Investment
        fields = (
            'product', 'asset', 'kind', 'amount', 'quantity', 'unit_price', 'fees', 'fees_in_asset_currency',
            'cash_amount', 'source_account', 'source_program', 'source_points',
            'destination_account', 'date', 'reason', 'notes',
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'quantity': forms.NumberInput(attrs={'step': '0.00000001', 'min': '0.00000001'}),
            'unit_price': forms.NumberInput(attrs={'step': '0.00000001', 'min': '0.00000001'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'fees': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'cash_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'source_points': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'product': _('Product'),
            'asset': _('Asset'),
            'kind': _('Type'),
            'amount': _('Operation amount'),
            'quantity': _('Quantity (unit-based assets)'),
            'unit_price': _('Unit price (unit-based assets)'),
            'fees': _('Fees'),
            'cash_amount': _('Cash amount (unit-based assets)'),
            'source_account': _('Source account'),
            'source_program': _('Source program'),
            'source_points': _('Source points'),
            'destination_account': _('Destination account'),
            'date': _('Date'),
            'reason': _('Reason'),
            'notes': _('Notes'),
        }
        help_texts = {
            'amount': _('Value of this operation in the asset currency. Yield changes only the position, without a bank movement.'),
            'quantity': _('Required only for assets valued by units and price.'),
            'unit_price': _('Required only for assets valued by units and price.'),
            'fees': _('Operation fees; this does not change gross value.'),
            'cash_amount': _('Actual debit/credit in the selected account native currency.'),
            'source_account': _('For an account-funded deposit only.'),
            'source_program': _('For a points-funded deposit only.'),
            'destination_account': _('For a withdrawal only.'),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user or (self.instance.user if self.instance.pk else None)
        if (self.instance.pk and self.instance.fx_snapshot_status == Investment.FxSnapshotStatus.UNKNOWN
                and self.instance.currency != UserPreference.for_user(self.user).base_currency):
            self.fields['capture_missing_fx'] = forms.BooleanField(
                label=_('Record the missing historical conversion'), required=False, initial=False,
                help_text=_('Use the registered exchange rate on or before the operation date. This records only missing evidence; existing conversions stay unchanged.'),
                widget=forms.CheckboxInput(attrs={'class': 'h-4 w-4 accent-caramel'}),
            )
        configure_date_fields(self, user)
        self.yield_preview = None
        self.operation_copy = {
            'DEPOSIT': {'amount': _('Deposit amount'), 'quantity': _('Quantity acquired'),
                        'unit_price': _('Purchase unit price'), 'cash_amount': _('Amount debited')},
            'WITHDRAWAL': {'amount': _('Withdrawal amount'), 'quantity': _('Quantity withdrawn'),
                           'unit_price': _('Sale unit price'), 'cash_amount': _('Amount received')},
            'YIELD': {'amount': _('Yield amount'), 'quantity': _('Quantity earned'),
                      'unit_price': _('Yield unit price'), 'cash_amount': _('Cash amount (unit-based assets)')},
        }
        kind = self.data.get('kind') if self.is_bound else self.initial.get('kind')
        for name, label in self.operation_copy.get(kind, {}).items():
            self.fields[name].label = label

        # Old submissions and the native form can identify the source directly.
        # The UI selector must not change the ledger's exactly-one-source rule.
        if self.is_bound and not self.data.get('funding_source'):
            self.data = self.data.copy()
            self.data['funding_source'] = (
                'ACCOUNT' if self.data.get('source_account') else
                'POINTS' if self.data.get('source_program') else ''
            )
        elif not self.is_bound:
            self.initial.setdefault('funding_source',
                'ACCOUNT' if self.initial.get('source_account') else
                'POINTS' if self.initial.get('source_program') else '')
        if user is not None:
            self.instance.user = user
            self.fields['product'].queryset = InvestmentProduct.objects.filter(
                user=user, bank__user=user
            ).select_related('bank')
            available_assets = Q(is_archived=False)
            # The current asset must remain selectable when correcting history.
            if self.instance.pk:
                available_assets |= Q(pk=self.instance.asset_id)
            self.fields['asset'].queryset = Asset.objects.filter(user=user).filter(available_assets)
            accounts = BankAccount.objects.filter(user=user).select_related('bank')
            self.fields['source_account'].queryset = accounts
            self.fields['destination_account'].queryset = accounts
            self.fields['source_program'].queryset = LoyaltyProgram.objects.filter(user=user)
        assets = list(self.fields['asset'].queryset)
        asset_widget = InvestmentSelect(attrs=self.fields['asset'].widget.attrs.copy())
        asset_widget.choice_data = {
            str(asset.pk): {
                'data-valuation-mode': asset.valuation_mode,
                'data-currency': asset.currency,
            }
            for asset in assets
        }
        asset_widget.choices = self.fields['asset'].choices
        self.fields['asset'].widget = asset_widget
        for name, field in self.fields.items():
            if name in ('yield_input_mode', 'capture_missing_fx', 'fees_in_asset_currency'):
                field.widget.attrs['class'] = 'h-4 w-4 accent-caramel'
            else:
                field.widget.attrs['class'] = INPUT_CLASSES
            described_by = []
            if field.help_text:
                described_by.append(f'{field.widget.attrs.get("id", "id_" + name)}-help')
            if self.is_bound and self.errors.get(name):
                field.widget.attrs['aria-invalid'] = 'true'
                described_by.extend(
                    f'{field.widget.attrs.get("id", "id_" + name)}-error-{index}'
                    for index in range(1, len(self.errors[name]) + 1)
                )
            if described_by:
                field.widget.attrs['aria-describedby'] = ' '.join(described_by)

        # A final balance replaces the amount only for a monetary yield. The
        # model still stores the derived yield amount, so amount cannot remain
        # a required browser field in that entry mode.
        self.fields['amount'].required = False

        if (
            not self.is_bound
            and self.instance.pk
            and self.instance.kind == Investment.Kind.YIELD
            and self.instance.asset.valuation_mode == Asset.ValuationMode.MONETARY
        ):
            preview = calculate_monetary_yield(
                user=self.instance.user,
                product=self.instance.product,
                asset=self.instance.asset,
                operation_date=self.instance.date,
                input_mode=YIELD_INPUT_AMOUNT,
                value=self.instance.amount,
                operation=self.instance,
            )
            self.initial.setdefault('yield_input_mode', YIELD_INPUT_ENDING_BALANCE)
            self.initial.setdefault('ending_balance', preview.ending_balance)
            self.yield_preview = preview

    def _calculate_yield(self, data, *, lock=False):
        asset = data.get('asset')
        if not (
            asset
            and data.get('product')
            and data.get('date')
            and asset.valuation_mode == Asset.ValuationMode.MONETARY
            and data.get('kind') == Investment.Kind.YIELD
        ):
            return None

        input_mode = data.get('yield_input_mode')
        if input_mode not in (YIELD_INPUT_AMOUNT, YIELD_INPUT_ENDING_BALANCE):
            raise ValidationError({'yield_input_mode': _('Choose how to enter the yield.')})
        input_field = 'ending_balance' if input_mode == YIELD_INPUT_ENDING_BALANCE else 'amount'
        value = data.get(input_field)
        preview = calculate_monetary_yield(
            user=self.user,
            product=data.get('product'),
            asset=asset,
            operation_date=data.get('date'),
            input_mode=input_mode,
            value=value,
            operation=self.instance if self.instance.pk else None,
            lock=lock,
        )
        data['amount'] = preview.yield_amount
        self.instance.amount = preview.yield_amount
        self.yield_preview = preview
        return preview

    def refresh_yield_amount(self, *, lock=False):
        """Recalculate the persisted amount immediately before saving."""
        return self._calculate_yield(self.cleaned_data, lock=lock)

    def clean(self):
        data = super().clean()
        if data.get('capture_missing_fx') and data.get('asset') and data.get('date'):
            try:
                convert(self.user, Decimal('1'), data['asset'].currency,
                        UserPreference.for_user(self.user).base_currency, as_of=data['date'])
            except MissingExchangeRate:
                self.add_error('capture_missing_fx', _('Register an exchange rate on or before the operation date first.'))
        if data.get('kind') == Investment.Kind.DEPOSIT:
            source = data.get('funding_source')
            if not source:
                self.add_error('funding_source', _('Choose a funding source.'))
            elif source == 'ACCOUNT' and not data.get('source_account'):
                self.add_error('source_account', _('Choose the account funding this deposit.'))
            elif source == 'POINTS' and not data.get('source_program'):
                self.add_error('source_program', _('Choose the loyalty program funding this deposit.'))
        asset = data.get('asset')
        if asset and asset.valuation_mode == Asset.ValuationMode.MONETARY and data.get('kind') == Investment.Kind.YIELD:
            try:
                self._calculate_yield(data)
            except ValidationError as error:
                for field, messages in error.message_dict.items():
                    for message in messages:
                        self.add_error(field, message)
        elif asset and asset.valuation_mode == Asset.ValuationMode.MONETARY:
            data['cash_amount'] = data.get('amount')
            self.instance.cash_amount = data['cash_amount']
        if asset and asset.valuation_mode == Asset.ValuationMode.MONETARY and data.get('fees_in_asset_currency'):
            self.add_error('fees_in_asset_currency', _('Fee cost allocation is for unit-based assets.'))
        return data
