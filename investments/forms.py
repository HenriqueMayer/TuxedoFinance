from django import forms
from django.utils.translation import gettext_lazy as _

from banking.models import Bank, BankAccount, LoyaltyProgram
from investments.models import Asset, Investment, InvestmentProduct


INPUT_CLASSES = (
    'w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-[#313335] px-3.5 py-2.5 '
    'text-slate-900 dark:text-neutral-100 placeholder:text-slate-400 dark:placeholder:text-neutral-500 '
    'focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40'
)


class InvestmentForm(forms.ModelForm):
    class Meta:
        model = Investment
        fields = (
            'product', 'asset', 'kind', 'quantity', 'unit_price', 'fees',
            'cash_amount', 'source_account', 'source_program', 'source_points',
            'destination_account', 'date', 'reason', 'notes',
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'quantity': forms.NumberInput(attrs={'step': '0.00000001', 'min': '0.00000001'}),
            'unit_price': forms.NumberInput(attrs={'step': '0.00000001', 'min': '0.00000001'}),
            'fees': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'cash_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'source_points': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'product': _('Product destination'),
            'asset': _('Asset'),
            'kind': _('Type'),
            'quantity': _('Quantity'),
            'unit_price': _('Unit price'),
            'fees': _('Fees'),
            'cash_amount': _('Cash amount'),
            'source_account': _('Source account'),
            'source_program': _('Source program'),
            'source_points': _('Source points'),
            'destination_account': _('Destination account'),
            'date': _('Date'),
            'reason': _('Reason'),
            'notes': _('Notes'),
        }
        help_texts = {
            'quantity': _('Asset units added or removed.'),
            'unit_price': _('Price per asset unit, denominated in the asset currency.'),
            'fees': _('Operation fees; this does not change gross value.'),
            'cash_amount': _('Actual debit/credit in the selected account native currency.'),
            'source_account': _('For an account-funded deposit only.'),
            'source_program': _('For a points-funded deposit only.'),
            'destination_account': _('For a withdrawal only.'),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
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
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES


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
        fields = ('name', 'code', 'asset_class', 'currency')
        labels = {
            'name': _('Name'),
            'code': _('Code'),
            'asset_class': _('Asset class'),
            'currency': _('Currency'),
        }
        help_texts = {
            'code': _('Short identifier, for example BTC, USD, PETR4, or CDB-2028.'),
            'asset_class': _('What the asset is: for example BTC is Crypto and PETR4 is Equity.'),
            'currency': _('Currency used to price it: for example PETR4 is priced in BRL.'),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.instance.user = user
        self.original_currency = self.instance.currency if self.instance.pk else None
        self.original_asset_class = self.instance.asset_class if self.instance.pk else None
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
