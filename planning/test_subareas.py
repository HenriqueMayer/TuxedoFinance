# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from html import unescape
from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import re

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation

from accounts.models import UserPreference
from investments.models import Asset
from planning.forms import GoalCreationForm, SignalSettingsForm
from planning.models import CategoryBudget, SignalSettings
from planning.services import goal_progress
from planning.tests import PlanningFixture


class ProgressValues(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.values = []
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        if tag == 'progress':
            self.values.append(dict(attributes)['value'])


class PlanningSubareaTests(PlanningFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_review_groups_keep_all_fields_and_invalid_disabled_rule_settings(self):
        form = SignalSettingsForm(user=self.user)
        names = [field.name for group in form.review_groups
                 for field in [group['enabled'], group['threshold']] if field is not None]
        self.assertCountEqual(names, form.fields)
        self.assertEqual(len(names), len(set(names)))
        path = reverse('planning:signals_settings')
        response = self.client.post(path, {'duplicate_days': '99', 'subscription_increase_percent': '12.34',
            'forecast_days': '45', 'budgetoverspend_enabled': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form']['duplicate_days'].value(), '99')
        self.assertFalse(response.context['form']['duplicates_enabled'].value())
        self.assertContains(response, 'value="12.34"')
        self.assertContains(response, 'value="45"')
        self.assertContains(response, 'role="alert"')
        for name in names:
            self.assertContains(response, f'name="{name}"', count=1)
        self.assertFalse(SignalSettings.objects.filter(user=self.user).exists())
        self.assertRedirects(self.client.post(path, {'duplicate_days': '4',
            'subscription_increase_percent': '12.34', 'forecast_days': '45',
            'budgetoverspend_enabled': 'on'}), reverse('planning:signals'))
        settings = SignalSettings.objects.get(user=self.user)
        self.assertFalse(settings.duplicates_enabled)
        self.assertEqual((settings.duplicate_days, settings.subscription_increase_percent,
                          settings.forecast_days), (4, Decimal('12.34'), 45))

    def test_cash_source_names_stay_short_but_disambiguate_same_named_assets(self):
        self.asset.name = self.product.name
        self.asset.save(update_fields=['name'])
        key = f'pot:{self.product.pk}:{self.asset.pk}'
        choices = dict(GoalCreationForm(user=self.user).fields['source'].choices)
        self.assertEqual(choices[key], f'{self.product.name} · {self.bank.name} · BRL 500.00')
        self.assertEqual(choices[f'account:{self.account.pk}'], f'{self.account.name} · {self.bank.name} · BRL 1000.00')
        duplicate = Asset.objects.create(user=self.user, name=self.product.name, code='SECOND-CASH',
            currency='BRL', asset_class='LIQUIDITY', valuation_mode='MONETARY', opening_balance='25',
            opening_product=self.product, opening_date=date(2020, 1, 1))
        choices = dict(GoalCreationForm(user=self.user).fields['source'].choices)
        self.assertIn(f'({self.asset.code})', choices[key])
        self.assertIn(f'({duplicate.code})', choices[f'pot:{self.product.pk}:{duplicate.pk}'])

    def test_progress_attributes_accept_decimal_context_without_localizing_machine_values(self):
        goal = self.goal(target_amount='400')
        self.reserve(goal=goal, amount='3')
        row = goal_progress(self.user)[0]
        # The current service intentionally rounds percentages to integers.
        # The reusable presentation must also accept a future decimal context.
        row['percent'] = Decimal('0.75')
        budget = CategoryBudget(user=self.user, category=self.category, month=self.month,
                                currency='BRL', amount='400')
        budget.pk = 1234
        with translation.override('pt-br'):
            summary = render_to_string('planning/_goal_summary.html', {'row': row, 'USER_DATE_FORMAT': 'd/m/Y'})
            budget_html = render_to_string('planning/_budget_row.html', {'row': {
                'budget': budget, 'actual': Decimal('3'), 'actual_percent': Decimal('0.75'),
                'remaining': Decimal('397'), 'forecast': Decimal('3'), 'complete': True}})
            with patch('planning.views.goal_progress', return_value=[row]):
                response = self.client.get(reverse('planning:goals'))
        for html in [summary, budget_html, response.content.decode()]:
            self.assertEqual(ProgressValues(html).values, ['0.75'])
        self.assertIn('id="budget-1234"', budget_html)

    def test_signal_source_editor_preserves_reviewed_origin_and_date_preference_without_changing_evidence(self):
        first = self.expense(title='Review duplicate')
        self.expense(title='Review duplicate')
        path = reverse('planning:signals') + '?reviewed=1'
        before = self.client.get(path)
        key = before.context['signals'][0]['key']
        preference = UserPreference.for_user(self.user)
        preference.date_format = 'MDY'
        preference.save(update_fields=['date_format'])
        self.client.cookies['django_language'] = 'pt-br'
        response = self.client.get(path)
        self.assertEqual(response.context['signals'][0]['key'], key)
        self.assertContains(response, first.date.strftime('%m/%d/%Y'))
        editor = reverse('transactions:update', args=[first.pk])
        href = next(unescape(value) for value in re.findall(r'href="([^"]+)"', response.content.decode())
                    if value.startswith(editor + '?'))
        self.assertEqual(parse_qs(urlsplit(href).query), {'next': [path]})
        self.assertEqual(response.context['signals'][0]['sources'][0]['date'], first.date)

    def test_standalone_reservation_identifies_its_goal_and_retains_bound_amount(self):
        goal = self.goal('A named target', target_amount='2000')
        path = reverse('planning:allocation_create', args=[goal.pk])
        response = self.client.post(path, {'source': f'account:{self.account.pk}', 'amount': '1000.01'})
        self.assertContains(response, 'A named target')
        self.assertContains(response, 'value="1000.01"')
        self.assertContains(response, 'role="alert"')
        self.assertFalse(goal.allocations.exists())
