"""Charts coverage for investments."""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from investments.forms import InvestmentForm
from investments.models import Asset, Investment, InvestmentProduct
from investments.tests.fixtures import InvestmentFixtureMixin


User = get_user_model()


BASE = 'BRL'


class InvestmentChartsTests(InvestmentFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)
        self.operation().save()  # Portfolio yield: 100 BRL.
        cash = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Cash pot',
            purpose=InvestmentProduct.Purpose.MONTHLY_CASH)
        asset = Asset.objects.create(user=self.user, name='Cash asset', code='CASH',
            asset_class=Asset.AssetClass.LIQUIDITY, currency=BASE,
            valuation_mode=Asset.ValuationMode.MONETARY, opening_product=cash, opening_balance=Decimal('200'))
        self.operation(product=cash, asset=asset, quantity=None, unit_price=None, amount=Decimal('5')).save()

    def test_chart_scope_filters_openings_flows_and_signed_details(self):
        for scope, total, flow in (('', '30500', '10500'), ('portfolio', '10000', '10000'), ('cash', '20500', '500')):
            with self.subTest(scope=scope):
                response = self.client.get(reverse('investments:charts'), {'scope': scope})
                self.assertEqual(response.context['total_selection']['points'][-1]['values'], [total])
                self.assertEqual(response.context['flow_selection']['points'][-1]['values'][2], flow)
                self.assertEqual(response.context['selected_section'], 'charts')
                details_url = response.context['flow_selection']['points'][-1]['details'][2]
                details = self.client.get(details_url)
                self.assertEqual(details.status_code, 200)
                if scope == 'portfolio':
                    self.assertNotContains(details, 'Cash pot')
                else:
                    self.assertContains(details, 'Cash pot')

    def test_empty_user_and_opening_only_positions_have_chart_workspace(self):
        Investment.objects.filter(user=self.user).delete()
        response = self.client.get(reverse('investments:charts'), {'scope': 'cash'})
        self.assertEqual(response.context['total_selection']['points'][-1]['values'], ['20000'])
        other = User.objects.create_user('chart-other')
        self.client.force_login(other)
        response = self.client.get(reverse('investments:charts'))
        self.assertEqual(response.context['total_selection']['points'][-1]['values'], ['0'])
        self.assertNotContains(response, 'Cash pot')

    def test_chart_filter_and_period_navigation_support_htmx(self):
        response = self.client.get(reverse('investments:charts'), {'scope': 'cash', 'total_offset': '-1'},
            HTTP_HX_REQUEST='true', HTTP_HX_TARGET='investments-charts')
        self.assertContains(response, 'id="investment-chart-scope"')
        self.assertContains(response, 'scope=cash')
        self.assertNotContains(response, '<html')

    def test_bound_operation_labels_match_kind_without_javascript(self):
        for kind, label in (('DEPOSIT', 'Deposit amount'), ('WITHDRAWAL', 'Withdrawal amount'), ('YIELD', 'Yield amount')):
            form = InvestmentForm(data={'kind': kind}, user=self.user)
            self.assertEqual(form.fields['amount'].label, label)
