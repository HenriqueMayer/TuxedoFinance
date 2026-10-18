from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.dates import configure_date_fields
from core.currencies import CURRENCIES

from banking.models import Bank, BankAccount, LoyaltyProgram
from banking.services import MissingExchangeRate, convert
from accounts.models import UserPreference
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation, CURRENCY_CHOICES
from investments.services import (
    YIELD_INPUT_AMOUNT,
    YIELD_INPUT_ENDING_BALANCE,
    calculate_monetary_yield,
)


INPUT_CLASSES = (
    'w-full rounded-xl border border-forest/20 bg-white px-4 py-3 text-sm text-forest '
    'placeholder:text-forest/40 focus:border-caramel focus:outline-hidden focus:ring-2 focus:ring-caramel/30 '
    'dark:border-cream/20 dark:bg-night dark:text-cream dark:placeholder:text-night-muted'
)


class InvestmentChartFilterForm(forms.Form):
    scope = forms.ChoiceField(
        label=_('Show positions'), required=False,
        choices=(('', _('Overall')), ('portfolio', _('Portfolio')), ('cash', _('Remunerated cash'))),
        widget=forms.Select(attrs={'class': INPUT_CLASSES, 'id': 'investment-chart-scope'}),
    )


class GuidedInvestmentForm(forms.Form):
    """Describe a holding without exposing the product/asset storage hierarchy."""

    new_institution = forms.BooleanField(required=False, label=_('Add a new institution'))
    institution = forms.ModelChoiceField(queryset=Bank.objects.none(), required=False,
        label=_('Institution'), empty_label=_('Choose an institution'))
    institution_name = forms.CharField(required=False, max_length=100, label=_('Institution name'))
    name = forms.CharField(max_length=100, label=_('Investment name'))
    valuation_mode = forms.ChoiceField(label=_('How do you record it?'), choices=[
        ('', _('Choose a value type')), ('MONETARY', _('Balance in money')),
        ('UNITS', _('Units and acquisition cost'))])
    purpose = forms.ChoiceField(required=False, label=_('What is this balance for?'), choices=[
        ('', _('Choose a purpose')), ('INVESTMENT', _('Investment')),
        ('MONTHLY_CASH', _('Remunerated cash'))],
        help_text=_('Remunerated cash can support bills. An investment stays outside monthly availability.'))
    planning_enabled = forms.BooleanField(required=False,
        label=_('Include this balance in monthly planning'),
        help_text=_('Unchecked balances stay in your holdings and history, outside monthly availability.'))
    currency = forms.ChoiceField(choices=CURRENCY_CHOICES, label=_('Currency'))
    opening_balance = forms.DecimalField(required=False, max_digits=16, decimal_places=2,
        min_value=Decimal('0'), label=_('Existing balance'))
    opening_quantity = forms.DecimalField(required=False, max_digits=20, decimal_places=8,
        min_value=Decimal('0'), label=_('Existing units'))
    opening_unit_price = forms.DecimalField(required=False, max_digits=20, decimal_places=8,
        min_value=Decimal('0'), label=_('Acquisition cost per unit'),
        help_text=_('Use the recorded acquisition cost, not a current market quote.'))
    opening_date = forms.DateField(required=False, label=_('Position start date'),
        help_text=_('Required for a nonzero opening. This records existing holdings without charging a bank account.'))
    code = forms.CharField(required=False, max_length=20, label=_('Identifier'),
        help_text=_('Optional. An internal identifier is generated when omitted.'))
    asset_class = forms.ChoiceField(required=False, label=_('Asset class'),
        choices=[('', _('Unclassified')), *Asset.AssetClass.choices],
        help_text=_('Optional classification. Choose it before recording operations; existing history locks this choice.'))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['institution'].queryset = Bank.objects.filter(user=user)
        self.initial.setdefault('currency', UserPreference.for_user(user).base_currency)
        configure_date_fields(self, user)
        for name, field in self.fields.items():
            if isinstance(field, forms.BooleanField):
                field.widget.attrs['class'] = 'h-4 w-4 rounded border-forest/30 text-caramel focus:ring-caramel'
            else:
                field.widget.attrs['class'] = INPUT_CLASSES
            if name in ('opening_quantity', 'opening_unit_price'):
                field.widget.attrs.update(step='0.00000001', min='0')
            if name in ('opening_balance', 'opening_quantity', 'opening_unit_price'):
                # The guided entry accepts the user's decimal convention;
                # native number controls cannot retain Brazilian comma input.
                field.localize = True
                field.widget = forms.TextInput(attrs={'class': INPUT_CLASSES, 'inputmode': 'decimal'})

    def clean(self):
        data = super().clean()
        if data.get('new_institution'):
            data['institution'] = None
            if not data.get('institution_name'):
                self.add_error('institution_name', _('Enter the institution name.'))
            elif Bank.objects.filter(user=self.user, name=data['institution_name']).exists():
                self.add_error('institution_name', _('This institution already exists. Choose it from the list.'))
        else:
            data['institution_name'] = ''
            if not data.get('institution') and 'institution' not in self.errors:
                self.add_error('institution', _('Choose an institution.'))
        mode = data.get('valuation_mode')
        if mode == Asset.ValuationMode.MONETARY:
            data['opening_quantity'] = data['opening_unit_price'] = Decimal('0')
            if not data.get('purpose') and 'purpose' not in self.errors:
                self.add_error('purpose', _('Choose a purpose.'))
        elif mode == Asset.ValuationMode.UNITS:
            data['opening_balance'] = Decimal('0')
            if data.get('purpose') == InvestmentProduct.Purpose.MONTHLY_CASH:
                self.add_error('purpose', _('Remunerated cash requires a balance in money.'))
            data['purpose'] = InvestmentProduct.Purpose.INVESTMENT
            if bool(data.get('opening_quantity')) != bool(data.get('opening_unit_price')):
                self.add_error('opening_unit_price', _('Enter units and their acquisition cost together.'))
        for name in ('opening_balance', 'opening_quantity', 'opening_unit_price'):
            data[name] = data.get(name) or Decimal('0')
        has_opening = bool(data['opening_balance'] or data['opening_quantity'])
        if has_opening and not data.get('opening_date') and 'opening_date' not in self.errors:
            self.add_error('opening_date', _('Enter the date of the opening position.'))
        elif not has_opening:
            data['opening_date'] = None
        data['planning_enabled'] = bool(data.get('planning_enabled') and data.get('purpose') == 'MONTHLY_CASH')
        data['code'] = data.get('code', '').upper()
        if data['code'] and Asset.objects.filter(user=self.user, code=data['code']).exists():
            self.add_error('code', _('You already have an asset with this code.'))
        if data.get('institution') and data.get('name') and InvestmentProduct.objects.filter(
                user=self.user, bank=data['institution'], name=data['name']).exists():
            self.add_error('name', _('This institution already has an investment with this name. Use its existing position or the full configuration.'))
        return data


class InvestmentOperationFilterForm(forms.Form):
    currency = forms.ChoiceField(label=_('Currency'), required=False,
        choices=[('', _('All currencies'))] + [(code, code) for code in CURRENCIES])
    asset_class = forms.ChoiceField(label=_('Asset class'), required=False,
        choices=[('', _('All asset classes'))] + list(Asset.AssetClass.choices))
    date_from = forms.DateField(label=_('From date'), required=False)
    date_to = forms.DateField(label=_('To date'), required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': INPUT_CLASSES, 'id': f'investment-{name.replace("_", "-")}'})
        configure_date_fields(self, user)

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            self.add_error('date_to', _('The end date must be on or after the start date.'))
        return data


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


class InvestmentProductForm(forms.ModelForm):
    class Meta:
        model = InvestmentProduct
        fields = ('bank', 'name', 'purpose')
        labels = {'bank': _('Bank'), 'name': _('Name'), 'purpose': _('Purpose')}
        help_texts = {
            'purpose': _('Monthly cash pots remain available for bills. Moving money to or from them is an internal transfer.'),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.instance.user = user
        self.fields['bank'].queryset = Bank.objects.filter(user=user)
        self.fields['purpose'].required = False
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES

    def clean_purpose(self):
        return self.cleaned_data.get('purpose') or InvestmentProduct.Purpose.INVESTMENT

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
            'opening_balance', 'opening_quantity', 'opening_unit_price', 'opening_product', 'opening_date',
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
            'opening_date': _('Opening position date'),
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
            'opening_date': _('The position exists at the start of this date, before its recorded operations. An older unknown date remains unknown until you provide it.'),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.instance.user = user
        if not self.is_bound and not self.instance.pk and 'valuation_mode' not in (kwargs.get('initial') or {}):
            self.initial['valuation_mode'] = ''
        self.fields['valuation_mode'].choices = [('', _('Choose how this asset is valued')), *Asset.ValuationMode.choices]
        self.original_currency = self.instance.currency if self.instance.pk else None
        self.original_asset_class = self.instance.asset_class if self.instance.pk else None
        self.original_valuation_mode = self.instance.valuation_mode if self.instance.pk else None
        self.original_opening_balance = self.instance.opening_balance if self.instance.pk else None
        self.original_opening_quantity = self.instance.opening_quantity if self.instance.pk else None
        self.original_opening_unit_price = self.instance.opening_unit_price if self.instance.pk else None
        self.original_opening_product = self.instance.opening_product_id if self.instance.pk else None
        self.fields['opening_product'].queryset = InvestmentProduct.objects.filter(user=user)
        configure_date_fields(self, user)
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
        if self.instance.pk and currency != self.original_currency and self.instance.price_observations.exists():
            raise forms.ValidationError(_('Currency cannot be changed after this asset has price observations.'))
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
        if self.instance.pk and valuation_mode != self.original_valuation_mode and self.instance.price_observations.exists():
            raise forms.ValidationError(_('Valuation mode cannot be changed after this asset has price observations.'))
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


class PriceObservationFilterForm(forms.Form):
    asset = forms.ModelChoiceField(queryset=Asset.objects.none(), required=False,
        label=_('Asset'), empty_label=_('All assets'))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        # Consultation includes archived assets; only new observations exclude them.
        self.fields['asset'].queryset = Asset.objects.filter(user=user)
        self.fields['asset'].widget.attrs.update({
            'id': 'investment-price-asset', 'class': INPUT_CLASSES, 'data-live-change': '',
        })


class PriceObservationForm(forms.ModelForm):
    class Meta:
        model = PriceObservation
        fields = ('asset', 'date', 'unit_price', 'source')
        labels = {'asset': _('Asset')}
        widgets = {'unit_price': forms.NumberInput(attrs={'step': '0.00000001', 'min': '0.00000001'})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.user = user
        available = Q(is_archived=False)
        if self.instance.pk:
            available |= Q(pk=self.instance.asset_id)
        self.fields['asset'].queryset = Asset.objects.filter(user=user, valuation_mode=Asset.ValuationMode.UNITS).filter(available)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES
        configure_date_fields(self, user)

    def clean(self):
        data = super().clean()
        if data.get('asset') and data.get('date'):
            matching = PriceObservation.objects.filter(asset=data['asset'], date=data['date'])
            if self.instance.pk:
                matching = matching.exclude(pk=self.instance.pk)
            if matching.exists():
                self.add_error('date', _('A price exists for this asset and date. Edit that observation instead.'))
        return data
