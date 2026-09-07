from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


class LandingBrandTests(TestCase):
    def test_landing_has_factual_content_and_cat_portrait(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<title>Tuxedo Finance</title>', html=True)
        self.assertContains(response, 'brand/tuxedo-hero.jpg')
        self.assertContains(response, 'A black-and-white cat wearing a bow tie at a desk.')
        self.assertContains(response, 'A local application to record income and expenses')
        for label in ('Transactions and categories', 'Accounts and cards',
                      'Recurrences and installments', 'Investments', 'Reports', 'Salary sandbox'):
            self.assertContains(response, label)
        for removed in ('Sample dashboard preview', 'Understand your cash flow',
                        'Clear money, elegantly presented.', 'Ready to see your cash flow clearly?',
                        'Your money, in black and white.', 'in under 30 seconds'):
            self.assertNotContains(response, removed)

    @override_settings(LANGUAGE_CODE='pt-br')
    def test_landing_translates_primary_copy_to_brazilian_portuguese(self):
        response = self.client.get('/', HTTP_ACCEPT_LANGUAGE='pt-br')
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Language'], 'pt-br')
        self.assertContains(response, 'Aplicação local para registrar receitas e despesas')
        self.assertContains(response, 'Transações e categorias')
        self.assertContains(response, 'Funcionalidades')
        self.assertContains(response, 'Simulação salarial')
        self.assertContains(response, 'Criar conta')
        self.assertNotIn('A local application', content)

    @override_settings(ALLOW_SIGNUPS=True)
    def test_visitor_can_login_or_create_account(self):
        response = self.client.get('/')
        self.assertContains(response, f'href="{reverse("accounts:login")}"')
        self.assertContains(response, f'href="{reverse("accounts:signup")}"')
        self.assertNotContains(response, 'Open dashboard')

    @override_settings(ALLOW_SIGNUPS=False)
    def test_closed_registration_keeps_login(self):
        response = self.client.get('/')
        self.assertContains(response, f'href="{reverse("accounts:login")}"')
        self.assertNotContains(response, reverse('accounts:signup'))

    def test_authenticated_homepage_links_to_dashboard(self):
        user = get_user_model().objects.create_user(username='landing-user')
        self.client.force_login(user)
        response = self.client.get('/')
        self.assertContains(response, 'Open dashboard')
        self.assertNotContains(response, reverse('accounts:signup'))
        self.assertNotContains(response, reverse('accounts:login'))

    def test_shared_shell_exposes_wordmark_and_favicon(self):
        response = self.client.get('/')

        self.assertContains(response, 'brand/favicon.ico')
        self.assertContains(response, 'brand/apple-touch-icon.png')
        self.assertContains(
            response,
            'brand/tuxedo-mark-256.png',
        )
        self.assertContains(
            response,
            '<span class="block text-sm tracking-[0.2em] uppercase font-medium">Tuxedo</span>',
            html=True,
        )
        self.assertContains(
            response,
            '<span class="block text-xs tracking-[0.15em] uppercase text-caramel-ink dark:text-caramel-light mt-0.5">Finance</span>',
            html=True,
        )


class SharedFormContractTests(TestCase):
    def test_record_fields_automatically_use_shared_picker_and_keep_prefixed_ids(self):
        from django import forms
        from django.template import Context, Template
        from categories.models import Category

        class ExampleForm(forms.Form):
            category = forms.ModelChoiceField(queryset=Category.objects.none(), help_text='Choose one')
            cards = forms.ModelMultipleChoiceField(queryset=Category.objects.none(), required=False)
            kind = forms.ChoiceField(choices=[('', 'Choose'), ('A', 'A')])

        form = ExampleForm({'left-category': '999', 'left-kind': 'A'}, prefix='left')
        html = Template("{% include 'partials/form_field.html' with field=form.category %}").render(Context({'form': form}))
        self.assertIn('data-search-select', html)
        self.assertIn('id="id_left-category"', html)
        self.assertNotIn('data-search-id="category-search"', html)
        self.assertIn('id_left-category-error-1', html)
        self.assertIn('aria-invalid="true"', html)
        self.assertIn('id_left-category-help', html)
        multiple = Template("{% include 'partials/form_field.html' with field=form.cards %}").render(Context({'form': form}))
        self.assertIn('data-search-select', multiple)
        self.assertIn('multiple', multiple)
        short = Template("{% include 'partials/form_field.html' with field=form.kind %}").render(Context({'form': form}))
        self.assertNotIn('data-search-select', short)

    def test_new_asset_and_yield_modes_wait_for_explicit_selection(self):
        from investments.forms import AssetForm, InvestmentForm
        from investments.models import Asset

        user = get_user_model().objects.create_user('form-contract')
        self.assertEqual(AssetForm(user=user)['valuation_mode'].value(), '')
        self.assertIsNone(InvestmentForm(user=user)['yield_input_mode'].value())
        contextual = AssetForm(user=user, initial={'valuation_mode': Asset.ValuationMode.MONETARY})
        self.assertEqual(contextual['valuation_mode'].value(), Asset.ValuationMode.MONETARY)
        invalid = AssetForm(user=user, data={'valuation_mode': Asset.ValuationMode.UNITS})
        self.assertFalse(invalid.is_valid())
        self.assertEqual(invalid['valuation_mode'].value(), Asset.ValuationMode.UNITS)

    def test_missing_yield_mode_reports_the_choice_and_keeps_nested_error_groups(self):
        from banking.models import Bank
        from investments.models import Asset, InvestmentProduct

        user = get_user_model().objects.create_user('mode-validation')
        bank = Bank.objects.create(user=user, name='Bank')
        product = InvestmentProduct.objects.create(user=user, bank=bank, name='Savings')
        asset = Asset.objects.create(user=user, name='Cash', code='CASH',
                                     asset_class='LIQUIDITY', currency='BRL', valuation_mode='MONETARY')
        self.client.force_login(user)
        response = self.client.post(reverse('investments:create'), {
            'product': product.pk, 'asset': asset.pk, 'kind': 'YIELD',
            'amount': '10', 'fees': '0', 'date': '2026-09-07',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('yield_input_mode', response.context['form'].errors)
        self.assertContains(response, 'Choose how to enter the yield.')
        self.assertContains(response, 'id="money-fields" data-has-errors="true"')
        self.assertContains(response, 'id="monetary-yield-fields"\n                     data-has-errors="true"')
