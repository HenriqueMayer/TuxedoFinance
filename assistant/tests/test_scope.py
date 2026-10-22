# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.test import RequestFactory, TestCase
from django.urls import reverse

from assistant.context import SCOPE_MAX_AGE, ScopeError, normalize_location, read_scope, sign_scope
from assistant.context_processors import assistant_shell
from assistant.tests.support import make_finances, make_owner
from ingestion.models import ImportBatch


class AssistantScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_owner('scope-owner')
        cls.other = make_owner('scope-other')
        cls.bank, cls.account, cls.category, cls.item = make_finances(cls.user)
        cls.foreign_bank, cls.foreign_account, cls.foreign_category, cls.foreign_item = make_finances(cls.other, 'Foreign')

    def test_signature_owner_expiry_and_deleted_record_are_rechecked(self):
        with patch('django.core.signing.time.time', return_value=1000):
            token = sign_scope(self.user, reverse('transactions:update', args=[self.item.pk]))
        with patch('django.core.signing.time.time', return_value=1000 + SCOPE_MAX_AGE):
            self.assertEqual(read_scope(self.user, token)['kwargs']['pk'], self.item.pk)
            for user, value in [(self.other, token), (self.user, token + 'x')]:
                with self.subTest(user=user.pk, token=value):
                    with self.assertRaises(ScopeError):
                        read_scope(user, value)
            self.item.delete()
            with self.assertRaises(ScopeError):
                read_scope(self.user, token)
        with patch('django.core.signing.time.time', return_value=1001 + SCOPE_MAX_AGE):
            with self.assertRaises(ScopeError):
                read_scope(self.user, token)

    def test_current_location_refresh_requires_valid_owner_token(self):
        token = sign_scope(self.user, '/dashboard/')
        current = f'/transactions/?type=EXPENSE&month=2026-10&category={self.category.pk}'
        scope = read_scope(self.user, token, location=current)
        self.assertEqual(scope['route'], 'transactions:list')
        self.assertEqual(scope['filters']['month'], '2026-10')
        self.assertEqual(scope['location'], f'/transactions/?category={self.category.pk}&month=2026-10&type=EXPENSE')
        with self.assertRaises(ScopeError):
            read_scope(self.user, '', location=current)
        with self.assertRaises(ScopeError):
            read_scope(self.other, token, location='/dashboard/')

    def test_rejects_external_public_paused_mutating_and_unowned_origins(self):
        rejected = ['https://example.com/transactions/', '//example.com/transactions/',
                    '/transactions/#private', '/transactions/\\evil', '/transactions/\x7f',
                    '/', '/accounts/login/', '/admin/', '/assistant/', '/imports/upload/',
                    '/transactions/export/', f'/transactions/{self.item.pk}/delete/',
                    f'/transactions/{self.foreign_item.pk}/edit/',
                    f'/banking/{self.foreign_bank.pk}/',
                    f'/transactions/?category={self.foreign_category.pk}',
                    f'/banking/?account={self.foreign_account.pk}',
                    '/transactions/?user_id=1', '/transactions/?month=2026-13',
                    '/transactions/?date=2026-02-31', '/transactions/?sort=arbitrary',
                    '/transactions/?recurrence=arbitrary', '/banking/invoices/?status=OPEN',
                    '/transactions/?q=&q=other', '/transactions/?q=%0A',
                    '/transactions/?next=https%3A%2F%2Fexample.com',
                    '/transactions/?page=0', '/transactions/?page=10001',
                    '/transactions/?category=9223372036854775808',
                    '/banking/?from_currency=INVALID', '/transactions/?q=' + ('x' * 161)]
        for location in rejected:
            with self.subTest(location=repr(location)):
                with self.assertRaises((ScopeError, ValueError)):
                    normalize_location(self.user, location)
        with self.assertRaises(ScopeError):
            normalize_location(AnonymousUser(), '/transactions/')
        with self.assertRaises(ScopeError):
            normalize_location(self.user, '/transactions/?q=' + 'x' * 2048)

    def test_owned_filters_are_normalized_and_navigation_origin_is_not_context(self):
        scope = normalize_location(self.user, f'/transactions/?category={self.category.pk}&sort=oldest&next=%2Fdashboard%2F')
        self.assertEqual(scope['filters'], {'category': str(self.category.pk), 'sort': 'oldest'})
        self.assertNotIn('next', scope['location'])
        for value in ['SCHEDULED', 'PARTIAL', 'PAID', 'OVERDUE']:
            self.assertEqual(normalize_location(self.user, f'/banking/invoices/?status={value}')['filters']['status'], value)

    def test_reviewed_ingestion_sources_remain_read_only_and_pending_sources_hidden(self):
        batch = ImportBatch.objects.create(user=self.user, account=self.account, file_name='synthetic.csv',
                                            file_hash='1' * 64, file_format='CSV', raw_text='PRIVATE CSV', status='CONFIRMED')
        location = reverse('ingestion:detail', args=[batch.pk])
        self.assertEqual(normalize_location(self.user, location)['route'], 'ingestion:detail')
        batch.status = 'READY'
        batch.save(update_fields=['status'])
        with self.assertRaises(ScopeError):
            normalize_location(self.user, location)

    def test_shell_only_signs_available_authenticated_page_without_collecting_finances(self):
        factory = RequestFactory()
        for path, available in [('/dashboard/', True), ('/transactions/?sort=oldest', True),
                                ('/assistant/', False), ('/', False), ('/admin/', False),
                                ('/accounts/login/', False), ('/imports/upload/', False)]:
            with self.subTest(path=path):
                request = factory.get(path)
                request.user = self.user
                with patch('assistant.context.collect_context', side_effect=AssertionError('No financial collection in shell')):
                    values = assistant_shell(request)
                self.assertEqual(values['assistant_available'], available)
                if available:
                    self.assertEqual(read_scope(self.user, values['assistant_scope'])['location'], path)
                else:
                    self.assertEqual(values['assistant_scope'], '')
        request.user = AnonymousUser()
        self.assertFalse(assistant_shell(request)['assistant_available'])

    def test_payload_cannot_add_an_authoritative_model_or_owner(self):
        token = signing.dumps({'v': 1, 'user': self.other.pk, 'location': '/transactions/'}, salt='assistant.page-scope.v1')
        with self.assertRaises(ScopeError):
            read_scope(self.user, token)
