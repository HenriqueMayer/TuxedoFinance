# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Guided holdings and product/asset registration."""

from decimal import Decimal
from django import forms
from django.utils.translation import gettext_lazy as _
from core.dates import configure_date_fields
from core.widgets import SegmentedChoice
from banking.models import Bank
from accounts.models import UserPreference
from investments.models import Asset, InvestmentProduct, CURRENCY_CHOICES
from investments.appearance import DEFAULT_ICON, ICON_CHOICES
from ._styles import INPUT_CLASSES


class GuidedInvestmentForm(forms.Form):
    """Describe a holding without exposing the product/asset storage hierarchy."""

    new_institution = forms.BooleanField(required=False, label=_('Add a new institution'))
    institution = forms.ModelChoiceField(queryset=Bank.objects.none(), required=False,
        label=_('Institution'), empty_label=_('Choose an institution'))
    institution_name = forms.CharField(required=False, max_length=100, label=_('Institution name'))
    name = forms.CharField(max_length=100, label=_('Investment name'))
    icon = forms.ChoiceField(required=False, initial=DEFAULT_ICON, choices=ICON_CHOICES,
                             label=_('Application icon'), widget=SegmentedChoice)
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
            if isinstance(field.widget, SegmentedChoice):
                field.widget.attrs['class'] = 'entry-segment-options'
            elif isinstance(field, forms.BooleanField):
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

    def clean_icon(self):
        return self.cleaned_data.get('icon') or DEFAULT_ICON


class PositionAppearanceForm(forms.Form):
    icon = forms.ChoiceField(label=_('Application icon'), choices=ICON_CHOICES,
                             widget=SegmentedChoice(attrs={'class': 'entry-segment-options'}))


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
