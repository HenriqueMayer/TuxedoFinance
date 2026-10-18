# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Shared visual adoption must preserve native forms and financial precision."""
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from unittest.mock import patch

from django import forms
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.utils.translation import override

from accounts.models import UserPreference
from banking.forms import BankAccountForm, BankTransferForm, ExchangeRateFilterForm
from categories.models import Category
from core.dates import PreferredDateInput, configure_date_fields
from ingestion.forms import UploadForm
from investments.forms import (
    AssetForm,
    GuidedInvestmentForm,
    InvestmentForm,
    InvestmentOperationFilterForm,
    PriceObservationForm,
)
from pages.templatetags.form_ui import form_control
from planning.forms import FinancialGoalForm
from transactions.forms import TransactionDateFilterForm, TransactionForm


class ControlMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(str(html))

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def find(self, tag, **attrs):
        return next(values for name, values in self.elements
                    if name == tag and all(values.get(key) == value for key, value in attrs.items()))


class SharedInterfaceRendererTests(SimpleTestCase):
    def test_ordinary_controls_keep_native_attributes_and_bound_values(self):
        definitions = {
            'title': forms.CharField(initial='Unbound title'),
            'password': forms.CharField(widget=forms.PasswordInput(attrs={
                'autocomplete': 'current-password',
            })),
            'account': forms.ChoiceField(choices=[('1520', 'Owned account')]),
            'notes': forms.CharField(widget=forms.Textarea(attrs={'rows': 3})),
            'quantity': forms.DecimalField(max_digits=20, decimal_places=8,
                widget=forms.NumberInput(attrs={'step': '0.00000001', 'min': '0'})),
        }
        form = forms.Form(data={
            'entry-title': 'Current title', 'entry-password': 'private-unsaved-value',
            'entry-account': '1520', 'entry-notes': 'Saved text <with markup>',
            'entry-quantity': '123.12345678',
        }, prefix='entry')
        form.fields.update(definitions)
        for name, field in form.fields.items():
            field.widget.attrs.update({'id': f'owned-{name}', 'class': 'domain-control',
                                       'data-owner': 'existing-form'})
        self.assertTrue(form.is_valid(), form.errors)
        for name in definitions:
            with self.subTest(control=name):
                bound = form[name]
                native = str(bound.as_widget())
                adopted = str(form_control(bound))
                # The shared presentation adds a class, not a replacement widget
                # or an interpretation of number, password or record values.
                self.assertEqual(adopted.replace('domain-control entry-input', 'domain-control'), native)
                control_tag = 'select' if name == 'account' else 'textarea' if name == 'notes' else 'input'
                attrs = ControlMarkup(adopted).find(control_tag)
                self.assertEqual(attrs['name'], f'entry-{name}')
                self.assertEqual(attrs['id'], f'owned-{name}')
        quantity = ControlMarkup(form_control(form['quantity'])).find('input')
        self.assertEqual(quantity['type'], 'number')
        self.assertEqual(quantity['step'], '0.00000001')
        self.assertEqual(quantity['value'], '123.12345678')
        self.assertEqual(form.cleaned_data['quantity'], Decimal('123.12345678'))
        password = ControlMarkup(form_control(form['password'])).find('input')
        self.assertEqual(password['autocomplete'], 'current-password')
        self.assertNotIn('value', password)

    def test_specialized_native_widgets_are_not_restyled_as_text_entries(self):
        widgets = (
            forms.HiddenInput(), forms.CheckboxInput(), forms.RadioSelect(choices=[('A', 'A')]),
            forms.CheckboxSelectMultiple(choices=[('A', 'A')]), forms.FileInput(),
            forms.ClearableFileInput(), forms.TextInput(attrs={'type': 'color'}),
        )
        for widget in widgets:
            with self.subTest(widget=widget.__class__.__name__, type=widget.attrs.get('type')):
                form = forms.Form()
                widget.attrs['class'] = 'own-special-control'
                form.fields['choice'] = forms.CharField(required=False, widget=widget)
                native = str(form['choice'].as_widget())
                adopted = str(form_control(form['choice']))
                self.assertEqual(adopted, native)
                self.assertNotIn('entry-input', adopted)

    def test_rendering_preserves_error_recovery_help_and_widget_state(self):
        form = forms.Form(data={'operation-units': 'not-a-number'}, prefix='operation')
        form.fields['units'] = forms.DecimalField(decimal_places=8, help_text='Recorded units.',
            widget=forms.NumberInput(attrs={
                'class': 'domain-control', 'id': 'holding-units',
                'step': '0.00000001', 'aria-describedby': 'unit-context unit-context',
            }))
        original = form.fields['units'].widget.attrs.copy()
        self.assertFalse(form.is_valid())
        first = str(form_control(form['units']))
        self.assertEqual(first, str(form_control(form['units'])))
        self.assertEqual(form.fields['units'].widget.attrs, original)
        attrs = ControlMarkup(first).find('input')
        self.assertEqual(attrs['aria-describedby'].split(), [
            'unit-context', 'holding-units-help', 'holding-units-error-1',
        ])
        self.assertEqual(attrs['aria-invalid'], 'true')
        self.assertEqual(attrs['value'], 'not-a-number')
        html = render_to_string('partials/form_field.html', {'field': form['units']})
        markup = ControlMarkup(html)
        self.assertEqual(markup.find('label')['for'], 'holding-units')
        self.assertEqual(markup.find('p', id='holding-units-error-1')['role'], 'alert')

    def test_boolean_row_keeps_bound_native_checkbox_label_help_and_errors(self):
        form = forms.Form(data={})
        form.fields['confirm'] = forms.BooleanField(label='Confirm operation',
            help_text='Confirmation is required.', widget=forms.CheckboxInput(attrs={'class': 'w-full'}))
        self.assertFalse(form.is_valid())
        html = render_to_string('partials/form_field.html', {'field': form['confirm']})
        markup = ControlMarkup(html)
        self.assertIn('entry-checkbox-choice', html)
        attrs = markup.find('input', type='checkbox')
        self.assertEqual(attrs['name'], 'confirm')
        self.assertEqual(attrs['aria-invalid'], 'true')
        self.assertNotIn('checked', attrs)
        self.assertEqual(markup.find('label')['for'], attrs['id'])
        self.assertEqual(markup.find('p', id='id_confirm-error-1')['role'], 'alert')
        self.assertIn('id_confirm-help', attrs['aria-describedby'])
        bound = forms.Form(data={'confirm': 'on'})
        bound.fields['confirm'] = form.fields['confirm']
        self.assertTrue(bound.is_valid())
        checked = ControlMarkup(render_to_string('partials/form_field.html', {'field': bound['confirm']}))
        self.assertIn('checked', checked.find('input', type='checkbox'))

    def test_numeric_validation_and_precision_are_not_changed_by_rendering(self):
        form = forms.Form(data={'price': '123.123456789'})
        form.fields['price'] = forms.DecimalField(max_digits=20, decimal_places=8)
        self.assertFalse(form.is_valid())
        errors = form.errors.as_data()['price']
        native = ControlMarkup(form['price'].as_widget()).find('input')
        html = str(form_control(form['price']))
        attrs = ControlMarkup(html).find('input')
        self.assertEqual(attrs['value'], '123.123456789')
        self.assertEqual(attrs['step'], native['step'])
        self.assertEqual(Decimal(attrs['step']), Decimal('0.00000001'))
        self.assertNotIn('data-money-input', attrs)
        self.assertEqual(form.errors.as_data()['price'], errors)


class SharedCalendarPresentationTests(SimpleTestCase):
    def date_form(self, value=None, order='DMY'):
        form = forms.Form(data={'posting-booked': value} if value is not None else None,
                          prefix='posting')
        form.fields['booked'] = forms.DateField(widget=forms.DateInput(attrs={
            'type': 'date', 'class': 'own-date-control', 'id': 'owned-booked-date',
            'min': '2020-01-01', 'max': '2030-12-31', 'data-origin': 'ledger',
        }))
        with patch('core.dates.date_order', return_value=order):
            configure_date_fields(form)
        return form

    def test_calendar_opt_in_keeps_native_identity_limits_and_date_metadata(self):
        for order, text in (('DMY', '14/08/2026'), ('MDY', '08/14/2026')):
            with self.subTest(order=order):
                form = self.date_form('2026-08-14', order)
                self.assertTrue(form.is_valid(), form.errors)
                widget = form.fields['booked'].widget
                self.assertIsInstance(widget, PreferredDateInput)
                self.assertTrue(widget.entry_calendar)
                attrs = ControlMarkup(form_control(form['booked'])).find('input')
                self.assertEqual(attrs['type'], 'text')
                self.assertEqual(attrs['data-date-picker'], 'true')
                self.assertEqual(attrs['data-date-order'], order)
                self.assertEqual(attrs['name'], 'posting-booked')
                self.assertEqual(attrs['id'], 'owned-booked-date')
                self.assertEqual(attrs['min'], '2020-01-01')
                self.assertEqual(attrs['max'], '2030-12-31')
                self.assertEqual(attrs['data-origin'], 'ledger')
                self.assertIn('own-date-control', attrs['class'].split())
                self.assertEqual(attrs['value'], text)
                html = render_to_string('partials/form_field.html', {
                    'field': form['booked'], 'USER_DATE_FORMAT': 'm/d/Y' if order == 'MDY' else 'd/m/Y',
                })
                markup = ControlMarkup(html)
                self.assertIn('data-entry-date', markup.find('div', **{'data-form-field': None}))
                helper = markup.find('input', type='date')
                self.assertNotIn('name', helper)
                self.assertEqual(helper['tabindex'], '-1')
                self.assertEqual(helper['aria-hidden'], 'true')
                self.assertIn('hidden', markup.find('button', type='button'))

    def test_invalid_bound_text_is_preserved_alongside_calendar_and_server_error(self):
        for order, text in (('DMY', '31/02/2026'), ('MDY', '02/31/2026')):
            with self.subTest(order=order):
                form = self.date_form(text, order)
                self.assertFalse(form.is_valid())
                html = render_to_string('partials/form_field.html', {
                    'field': form['booked'], 'USER_DATE_FORMAT': 'm/d/Y' if order == 'MDY' else 'd/m/Y',
                })
                markup = ControlMarkup(html)
                control = markup.find('input', name='posting-booked')
                self.assertEqual(control['value'], text)
                self.assertEqual(control['aria-invalid'], 'true')
                self.assertEqual(control['data-date-picker'], 'true')
                self.assertEqual(markup.find('p', id='owned-booked-date-error-1')['role'], 'alert')

    def test_iso_and_preferred_inputs_keep_the_same_calendar_day(self):
        for order, preferred in (('DMY', '03/04/2026'), ('MDY', '04/03/2026')):
            for value in ('2026-04-03', preferred):
                with self.subTest(order=order, value=value):
                    form = self.date_form(value, order)
                    self.assertTrue(form.is_valid(), form.errors)
                    self.assertEqual(form.cleaned_data['booked'], date(2026, 4, 3))

    def test_month_and_other_native_controls_are_not_converted_to_full_dates(self):
        form = forms.Form()
        form.fields['month'] = forms.CharField(widget=forms.TextInput(attrs={
            'type': 'month', 'min': '2020-01', 'class': 'native-month',
        }))
        form.fields['count'] = forms.IntegerField(widget=forms.NumberInput(attrs={'step': '1'}))
        originals = {name: (field.widget, field.widget.attrs.copy()) for name, field in form.fields.items()}
        with patch('core.dates.date_order') as preference:
            configure_date_fields(form)
        preference.assert_not_called()
        for name, (widget, attrs) in originals.items():
            self.assertIs(form.fields[name].widget, widget)
            self.assertEqual(form.fields[name].widget.attrs, attrs)


class DomainInterfaceAdoptionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('shared-interface-owner')
        cls.category = Category.objects.create(user=cls.user, name='Owned category', pk=1520)

    def test_model_choices_keep_shared_search_and_unlocalized_record_identifiers(self):
        form = forms.Form(data={'category': '1520', 'parent_category': '1520', 'assets': ['1520']})
        owned = Category.objects.filter(user=self.user)
        form.fields['category'] = forms.ModelChoiceField(queryset=owned)
        form.fields['parent_category'] = forms.ModelChoiceField(queryset=owned)
        form.fields['assets'] = forms.ModelMultipleChoiceField(queryset=owned,
            widget=forms.SelectMultiple(attrs={'data-search-id': 'owned-asset-search', 'class': 'owned-record'}))
        self.assertTrue(form.is_valid(), form.errors)
        for name, search_id in (('category', 'category-search'), ('parent_category', 'parent-category-search'),
                                ('assets', 'owned-asset-search')):
            with self.subTest(field=name), override('pt-br'):
                widget = form.fields[name].widget
                original = widget.attrs.copy()
                markup = ControlMarkup(form_control(form[name]))
                control = markup.find('select')
                self.assertIn('data-search-select', control)
                self.assertEqual(control['data-search-id'], search_id)
                self.assertEqual(control['name'], name)
                self.assertEqual(control['id'], f'id_{name}')
                option = markup.find('option', value='1520')
                self.assertIn('selected', option)
                self.assertEqual(widget.attrs, original)
        self.assertEqual(form.cleaned_data['category'], self.category)
        self.assertEqual(list(form.cleaned_data['assets']), [self.category])

    def test_full_date_fields_share_calendar_opt_in_across_domain_forms(self):
        form_classes = (
            TransactionForm, TransactionDateFilterForm, BankAccountForm, BankTransferForm,
            ExchangeRateFilterForm, GuidedInvestmentForm, InvestmentForm,
            InvestmentOperationFilterForm, AssetForm, PriceObservationForm,
            FinancialGoalForm, UploadForm,
        )
        for order in ('DMY', 'MDY'):
            UserPreference.objects.update_or_create(user=self.user, defaults={'date_format': order})
            for form_class in form_classes:
                form = form_class(user=self.user)
                dates = {name: field for name, field in form.fields.items() if isinstance(field, forms.DateField)}
                self.assertTrue(dates, form_class.__name__)
                for name, field in dates.items():
                    with self.subTest(form=form_class.__name__, field=name, order=order):
                        self.assertIsInstance(field.widget, PreferredDateInput)
                        self.assertTrue(field.widget.entry_calendar)
                        self.assertEqual(field.widget.attrs['data-date-picker'], 'true')
                        self.assertEqual(field.widget.attrs['data-date-order'], order)
                        self.assertEqual(field.clean('2024-02-29'), date(2024, 2, 29))
                        self.assertNotIn('data-money-input', field.widget.attrs)
