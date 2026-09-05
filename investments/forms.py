from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from banking.models import Bank, BankAccount, LoyaltyProgram
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import (
    YIELD_INPUT_AMOUNT,
    YIELD_INPUT_ENDING_BALANCE,
    calculate_monetary_yield,
)


INPUT_CLASSES = (
    'w-full rounded-xl border border-forest/20 bg-white px-4 py-3 text-sm text-forest '
    'placeholder:text-forest/40 focus:border-caramel focus:outline-none focus:ring-2 focus:ring-caramel/30 '
    'dark:border-cream/20 dark:bg-night dark:text-cream dark:placeholder:text-night-muted'
)


class InvestmentSelect(forms.Select):
    """Expose scoped asset metadata to the progressive operation form."""

    choice_data = None

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if self.choice_data and value:
            option['attrs'].update(self.choice_data.get(str(value), {}))
        return option


class InvestmentForm(forms.ModelForm):
    yield_input_mode = forms.ChoiceField(
        choices=(
            (YIELD_INPUT_ENDING_BALANCE, _('Use the final balance')),
            (YIELD_INPUT_AMOUNT, _('Enter the yield amount')),
        ),
        initial=YIELD_INPUT_ENDING_BALANCE,
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
            'product', 'asset', 'kind', 'amount', 'quantity', 'unit_price', 'fees',
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
            'product': _('Product destination'),
            'asset': _('Asset'),
            'kind': _('Type'),
            'amount': _('Investment amount'),
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
            'amount': _('Required for monetary assets such as savings pots; it is also used for the bank movement.'),
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
        self.user = user
        self.yield_preview = None
        if user is not None:
            self.instance.user = user
            self.fields['product'].queryset = InvestmentProduct.objects.filter(
                user=user, bank__user=user
            ).select_related('bank')
            self.fields['asset'].queryset = Asset.objects.filter(user=user)
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
            if name == 'yield_input_mode':
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
        return data


class InvestmentProductForm(forms.ModelForm):
    class Meta:
        model = InvestmentProduct
        fields = ('bank', 'name')
        labels = {'bank': _('Bank'), 'name': _('Name')}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.instance.user = user
        self.fields['bank'].queryset = Bank.objects.filter(user=user)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES

    def clean(self):
        data = super().clean()
        bank, name = data.get('bank'), data.get('name')
        if bank and name:
            duplicate = InvestmentProduct.objects.filter(bank=bank, name=name)
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error('name', _('This bank already has a product with this name.'))
        return data


class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = (
            'name', 'code', 'asset_class', 'currency', 'valuation_mode',
            'opening_balance', 'opening_quantity', 'opening_unit_price', 'opening_product',
        )
        labels = {
            'name': _('Name'),
            'code': _('Code'),
            'asset_class': _('Asset class'),
            'currency': _('Currency'),
            'valuation_mode': _('How this asset is valued'),
            'opening_balance': _('Opening balance'),
            'opening_quantity': _('Opening quantity'),
            'opening_unit_price': _('Opening unit price'),
            'opening_product': _('Opening balance product'),
        }
        help_texts = {
            'code': _('Short identifier, for example BTC, USD, PETR4, or CDB-2028.'),
            'asset_class': _('What the asset is: for example BTC is Crypto and PETR4 is Equity.'),
            'currency': _('Currency used to price it: for example PETR4 is priced in BRL.'),
            'valuation_mode': _('Monetary value is for savings pots and cash-like investments; units and price is for traded assets.'),
            'opening_balance': _('Existing balance before you start recording operations. Monetary assets only.'),
            'opening_quantity': _('Existing units before you start recording operations. Unit-based assets only.'),
            'opening_unit_price': _('Price per existing unit. Unit-based assets only.'),
            'opening_product': _('Required when an opening balance or opening position is provided.'),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.instance.user = user
        self.original_currency = self.instance.currency if self.instance.pk else None
        self.original_asset_class = self.instance.asset_class if self.instance.pk else None
        self.original_valuation_mode = self.instance.valuation_mode if self.instance.pk else None
        self.original_opening_balance = self.instance.opening_balance if self.instance.pk else None
        self.original_opening_quantity = self.instance.opening_quantity if self.instance.pk else None
        self.original_opening_unit_price = self.instance.opening_unit_price if self.instance.pk else None
        self.original_opening_product = self.instance.opening_product_id if self.instance.pk else None
        self.fields['opening_product'].queryset = InvestmentProduct.objects.filter(user=user)
        self.fields['opening_quantity'].widget = forms.NumberInput(
            attrs={'step': '0.00000001', 'min': '0'}
        )
        self.fields['opening_unit_price'].widget = forms.NumberInput(
            attrs={'step': '0.00000001', 'min': '0'}
        )
        self.fields['opening_balance'].widget = forms.NumberInput(
            attrs={'step': '0.01', 'min': '0'}
        )
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES

    def clean_code(self):
        code = self.cleaned_data['code'].upper()
        duplicate = Asset.objects.filter(user=self.user, code=code)
        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError(_('You already have an asset with this code.'))
        return code

    def clean_currency(self):
        currency = self.cleaned_data['currency']
        if (
            self.instance.pk
            and currency != self.original_currency
            and self.instance.operations.exists()
        ):
            raise forms.ValidationError(
                _('Currency cannot be changed after this asset has investment operations.')
            )
        return currency

    def clean_asset_class(self):
        asset_class = self.cleaned_data['asset_class']
        if (
            self.instance.pk
            and asset_class != self.original_asset_class
            and self.instance.operations.exists()
        ):
            raise forms.ValidationError(
                _('Asset class cannot be changed after this asset has investment operations.')
            )
        return asset_class

    def clean_valuation_mode(self):
        valuation_mode = self.cleaned_data['valuation_mode']
        if self.instance.pk and valuation_mode != self.original_valuation_mode and self.instance.operations.exists():
            raise forms.ValidationError(_('Valuation mode cannot be changed after this asset has investment operations.'))
        return valuation_mode

    def clean_opening_balance(self):
        opening_balance = self.cleaned_data['opening_balance']
        if self.instance.pk and opening_balance != self.original_opening_balance and self.instance.operations.exists():
            raise forms.ValidationError(_('Opening balance cannot be changed after this asset has investment operations.'))
        return opening_balance

    def clean_opening_product(self):
        opening_product = self.cleaned_data['opening_product']
        if self.instance.pk and (opening_product.pk if opening_product else None) != self.original_opening_product and self.instance.operations.exists():
            raise forms.ValidationError(_('Opening balance product cannot be changed after this asset has investment operations.'))
        return opening_product

    def _clean_opening_units_after_operations(self, value, original, label):
        if self.instance.pk and value != original and self.instance.operations.exists():
            raise forms.ValidationError(
                _('%(label)s cannot be changed after this asset has investment operations.')
                % {'label': label}
            )
        return value

    def clean_opening_quantity(self):
        return self._clean_opening_units_after_operations(
            self.cleaned_data['opening_quantity'],
            self.original_opening_quantity,
            _('Opening quantity'),
        )

    def clean_opening_unit_price(self):
        return self._clean_opening_units_after_operations(
            self.cleaned_data['opening_unit_price'],
            self.original_opening_unit_price,
            _('Opening unit price'),
        )
