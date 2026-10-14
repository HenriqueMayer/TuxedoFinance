# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount
from ingestion.models import ImportBatch
from transactions.models import Transaction


class ReviewGateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('roadmap-owner')
        self.other = get_user_model().objects.create_user('roadmap-other')
        self.bank = Bank.objects.create(user=self.user, name='Bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Cash', currency='BRL')
        self.batch = ImportBatch.objects.create(user=self.user, account=self.account, file_name='confirmed.csv',
            file_hash='a' * 64, file_format='CSV', raw_text='', status='CONFIRMED')
        self.client.force_login(self.user)

    def test_paused_gets_and_old_posts_redirect_without_financial_changes(self):
        for name in ['index', 'mapping', 'review', 'confirmation', 'undo']:
            url = reverse('ingestion:' + name, args=[] if name == 'index' else [self.batch.pk])
            for method in [self.client.get, self.client.post]:
                self.assertRedirects(method(url, {'action': 'CREATE'}), reverse('pages:roadmap') + '#imports')
        self.assertRedirects(self.client.get(reverse('dashboard:wealth')), reverse('pages:roadmap') + '#wealth')
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, 'CONFIRMED')
        self.assertEqual(ImportBatch.objects.count(), 1)
        self.assertFalse(Transaction.objects.exists())

    def test_owned_posted_history_remains_read_only_searchable_and_private(self):
        foreign = ImportBatch.objects.create(user=self.other, account=self.account, file_name='private.csv',
            file_hash='b' * 64, file_format='CSV', raw_text='', status='CONFIRMED')
        ImportBatch.objects.create(user=self.user, account=self.account, file_name='pending.csv',
            file_hash='c' * 64, file_format='CSV', raw_text='', status='READY')
        history = reverse('ingestion:history')
        response = self.client.get(history)
        self.assertContains(response, 'confirmed.csv')
        self.assertNotContains(response, 'private.csv')
        self.assertNotContains(response, 'pending.csv')
        self.assertNotContains(self.client.get(history, {'q': 'missing'}), 'confirmed.csv')
        self.assertIn('no-store', response.headers['Cache-Control'])
        detail = self.client.get(reverse('ingestion:detail', args=[self.batch.pk]))
        self.assertContains(detail, 'a' * 64)
        self.assertNotContains(detail, 'Review undo')
        self.assertNotContains(detail, 'Only unchanged records')
        self.assertEqual(self.client.post(history).status_code, 405)
        self.assertEqual(self.client.get(reverse('ingestion:detail', args=[foreign.pk])).status_code, 404)

    def test_navigation_explains_the_pause_and_roadmap_requires_login(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertContains(response, 'aria-disabled="true"')
        self.assertContains(response, reverse('pages:roadmap') + '#wealth')
        self.client.logout()
        self.assertEqual(self.client.get(reverse('pages:roadmap')).status_code, 302)
