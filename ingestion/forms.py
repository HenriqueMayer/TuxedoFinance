# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from banking.forms import INPUT_CLASSES
from banking.models import BankAccount
from core.dates import configure_date_fields
from ingestion.models import ImportedRow
from ingestion.parsers import MAX_BYTES
from ingestion.services import validate_decision


class StatementForm(forms.Form):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        configure_date_fields(self, user)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES


class UploadForm(StatementForm):
    account = forms.ModelChoiceField(queryset=BankAccount.objects.none(), label=_('Statement account'))
    file_format = forms.ChoiceField(choices=[('', _('Choose a format')), ('CSV', 'CSV'), ('OFX', 'OFX')], label=_('File format'))
    encoding = forms.ChoiceField(choices=[('', _('Choose an encoding')), ('utf-8-sig', 'UTF-8'), ('cp1252', 'Windows-1252')], label=_('File encoding'))
    statement = forms.FileField(label=_('Local statement file'), help_text=_('CSV or OFX, at most 2 MiB and 500 entries. The file stays in this installation.'))
    closing_balance = forms.DecimalField(max_digits=16, decimal_places=2, required=False, label=_('Statement closing balance'), widget=forms.NumberInput(attrs={'step': '0.01'}))
    closing_date = forms.DateField(required=False, label=_('Statement closing date'))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields['account'].queryset = BankAccount.objects.filter(user=user).select_related('bank')

    def clean_statement(self):
        statement = self.cleaned_data['statement']
        if statement.size > MAX_BYTES:
            raise ValidationError(_('The statement must be no larger than 2 MiB.'))
        return statement

    def clean(self):
        cleaned = super().clean()
        if (cleaned.get('closing_balance') is None) != (cleaned.get('closing_date') is None):
            self.add_error('closing_date', _('Enter both the closing balance and its date.'))
        return cleaned


class MappingForm(StatementForm):
    date_column = forms.ChoiceField(label=_('Date column'))
    description_column = forms.ChoiceField(label=_('Description column'))
    amount_mode = forms.ChoiceField(choices=[('', _('Choose an amount layout')), ('signed', _('One signed amount column')), ('separate', _('Separate debit and credit columns'))], label=_('Amount layout'))
    amount_column = forms.ChoiceField(required=False, label=_('Signed amount column'))
    debit_column = forms.ChoiceField(required=False, label=_('Debit column'))
    credit_column = forms.ChoiceField(required=False, label=_('Credit column'))
    id_column = forms.ChoiceField(required=False, label=_('Bank identifier column'), help_text=_('Only a stable bank identifier is a strong duplicate key. Leave empty when the statement has none.'))
    currency_column = forms.ChoiceField(required=False, label=_('Currency column'))
    date_format = forms.ChoiceField(choices=[('', _('Choose a date format')), ('%Y-%m-%d', 'YYYY-MM-DD'), ('%d/%m/%Y', 'DD/MM/YYYY'), ('%m/%d/%Y', 'MM/DD/YYYY')], label=_('Dates in this CSV'))
    decimal_mark = forms.ChoiceField(choices=[('', _('Choose a decimal separator')), ('.', _('Decimal point (1,234.56)')), (',', _('Decimal comma (1.234,56)'))], label=_('Amounts in this CSV'))

    def __init__(self, *args, headers, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('date_column', 'description_column', 'amount_column', 'debit_column', 'credit_column', 'id_column', 'currency_column'):
            self.fields[name].choices = [('', _('Choose a column'))] + [(header, header) for header in headers]

    def clean(self):
        cleaned = super().clean()
        required = ('amount_column',) if cleaned.get('amount_mode') == 'signed' else ('debit_column', 'credit_column')
        for name in required:
            if not cleaned.get(name):
                self.add_error(name, _('Choose the required amount column.'))
        if cleaned.get('amount_mode') == 'signed':
            cleaned['debit_column'] = cleaned['credit_column'] = ''
        else:
            cleaned['amount_column'] = ''
        return cleaned

    def mapping(self):
        return {name: self.cleaned_data[name] for name in self.fields if name != 'amount_mode'}


class CachedModelChoice(forms.ModelChoiceField):
    """Owned records loaded once for this review; preserve the shared picker."""
    def __init__(self, records, **kwargs):
        records = list(records)
        self.records = {str(record.pk): record for record in records}
        super().__init__(queryset=kwargs.pop('queryset'), required=False, **kwargs)
        self.choices = [('', self.empty_label)] + [(record.pk, self.label_from_instance(record)) for record in records]

    def label_from_instance(self, record):
        if hasattr(record, 'source_key'):
            return f'{record.get_kind_display()} · {record.description} · #{record.pk}'
        return str(record)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        record = self.records.get(str(value))
        if record is None:
            raise ValidationError(self.error_messages['invalid_choice'], code='invalid_choice', params={'value': value})
        return record


class ReviewRowForm(StatementForm):
    action = forms.ChoiceField(choices=[('', _('Choose an action'))] + list(ImportedRow.Action.choices), label=_('Entry action'))
    counterparty_amount = forms.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal('0.01'), required=False,
        label=_('Actual amount in the other account'), widget=forms.NumberInput(attrs={'step': '0.01'}))

    def __init__(self, *args, row, resources, **kwargs):
        self.row = row
        if not args or args[0] is None:
            kwargs.setdefault('initial', {
                'action': row.action, 'category': row.category_id,
                'matched_movement': row.matched_movement_id, 'invoice': row.invoice_id,
                'counterparty_account': row.counterparty_account_id, 'counterparty_amount': row.counterparty_amount,
            })
        super().__init__(*args, user=row.batch.user, **kwargs)
        kind = 'INCOME' if row.amount > 0 else 'EXPENSE'
        choices = {
            'category': ([record for record in resources['categories'] if not record.transaction_type or record.transaction_type == kind], _('Category')),
            'matched_movement': (resources['matches'].get((row.date, row.amount), []), _('Existing cash movement')),
            'invoice': ([record for record in resources['invoices'] if record.account.currency == row.currency], _('Manual invoice')),
            'counterparty_account': ([record for record in resources['accounts'] if record.pk != row.batch.account_id], _('Other owned account')),
        }
        for name, (records, label) in choices.items():
            self.fields[name] = CachedModelChoice(records, queryset=resources['models'][name].objects.none(), label=label)
            self.fields[name].widget.attrs['class'] = INPUT_CLASSES
        self.order_fields(['action', 'category', 'matched_movement', 'invoice', 'counterparty_account', 'counterparty_amount'])

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get('action')
        dependencies = {'CREATE': 'category', 'MATCH': 'matched_movement', 'PAY_INVOICE': 'invoice', 'TRANSFER': 'counterparty_account'}
        for candidate in ('category', 'matched_movement', 'invoice', 'counterparty_account'):
            if candidate != dependencies.get(action):
                cleaned[candidate] = None
        if action != 'TRANSFER':
            cleaned['counterparty_amount'] = None
        if self.errors:
            return cleaned
        self.row.action = action
        for name in ('category', 'matched_movement', 'invoice', 'counterparty_account'):
            setattr(self.row, name, cleaned[name])
        self.row.counterparty_amount = cleaned['counterparty_amount']
        try:
            validate_decision(self.row)
        except ValidationError as error:
            if hasattr(error, 'message_dict'):
                for messages in error.message_dict.values():
                    for message in messages:
                        self.add_error(None, message)
            else:
                self.add_error(None, error)
        return cleaned

    def decision(self):
        return {'action': self.cleaned_data['action'], 'counterparty_amount': self.cleaned_data['counterparty_amount'],
            **{name + '_id': self.cleaned_data[name].pk if self.cleaned_data[name] else None
               for name in ('category', 'matched_movement', 'invoice', 'counterparty_account')}}


class ConfirmationForm(StatementForm):
    digest = forms.CharField(widget=forms.HiddenInput)
    reviewed = forms.BooleanField(label=_('I reviewed every action and the account opening balance.'))
