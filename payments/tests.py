from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from payments.models import PaymentMethod

User = get_user_model()


class PaymentMethodListFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('payments', password='test')
        cls.other_user = User.objects.create_user('other-payments', password='test')

        cls.credit = PaymentMethod.objects.create(
            user=cls.user,
            name='Visa Platinum',
            method_type=PaymentMethod.MethodType.CREDIT_CARD,
        )
        cls.debit = PaymentMethod.objects.create(
            user=cls.user,
            name='Everyday Debit',
            method_type=PaymentMethod.MethodType.DEBIT_CARD,
        )
        cls.pix = PaymentMethod.objects.create(
            user=cls.user,
            name='Personal PIX',
            method_type=PaymentMethod.MethodType.PIX,
        )
        PaymentMethod.objects.create(
            user=cls.other_user,
            name='Private Visa',
            method_type=PaymentMethod.MethodType.CREDIT_CARD,
        )

    def setUp(self):
        self.client.force_login(self.user)

    @staticmethod
    def response_names(response):
        return [method.name for method in response.context['payment_methods']]

    def test_search_is_partial_case_insensitive_trimmed_and_user_scoped(self):
        response = self.client.get(reverse('payments:list'), {'q': ' VISA '})

        self.assertEqual(self.response_names(response), ['Visa Platinum'])
        self.assertEqual(response.context['search_query'], 'VISA')

    def test_method_type_filters_and_combines_with_search(self):
        response = self.client.get(
            reverse('payments:list'),
            {'q': 'visa', 'type': PaymentMethod.MethodType.CREDIT_CARD},
        )

        self.assertEqual(self.response_names(response), ['Visa Platinum'])
        self.assertEqual(
            response.context['selected_type'],
            PaymentMethod.MethodType.CREDIT_CARD,
        )

    def test_each_method_type_can_be_selected(self):
        debit_response = self.client.get(
            reverse('payments:list'),
            {'type': PaymentMethod.MethodType.DEBIT_CARD},
        )
        pix_response = self.client.get(
            reverse('payments:list'),
            {'type': PaymentMethod.MethodType.PIX},
        )

        self.assertEqual(self.response_names(debit_response), ['Everyday Debit'])
        self.assertEqual(self.response_names(pix_response), ['Personal PIX'])

    def test_invalid_method_type_is_ignored(self):
        response = self.client.get(reverse('payments:list'), {'type': 'CASH'})

        self.assertEqual(
            self.response_names(response),
            ['Everyday Debit', 'Personal PIX', 'Visa Platinum'],
        )
        self.assertEqual(response.context['selected_type'], '')

    def test_filtered_empty_state_and_controls_are_rendered(self):
        response = self.client.get(
            reverse('payments:list'),
            {'q': 'missing', 'type': PaymentMethod.MethodType.CHECKING_ACCOUNT},
        )

        self.assertContains(response, 'No matching payment methods')
        self.assertContains(response, 'Clear filters')
        self.assertContains(response, 'value="missing"')
        self.assertContains(response, 'value="CHECKING_ACCOUNT" selected')
