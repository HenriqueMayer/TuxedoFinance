# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement
from categories.models import Category
from core.navigation import with_return_url
from ingestion.models import ImportBatch
from ingestion.services import confirm_batch, decision_digest, map_csv_batch, save_review, stage_statement, undo_batch
from ingestion.tests import MAPPING
from transactions.models import Transaction


class ImportWorkspaceUXTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('compact-import-owner')
        self.other = get_user_model().objects.create_user('compact-import-private')
        self.bank = Bank.objects.create(user=self.user, name='Local bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Local account', currency='BRL', opening_balance='1000', opening_date=date(2020, 1, 1))
        self.private_bank = Bank.objects.create(user=self.other, name='Private bank')
        self.private_account = BankAccount.objects.create(user=self.other, bank=self.private_bank, name='Private account', currency='BRL')
        self.category = Category.objects.create(user=self.user, name='Local expense', transaction_type='EXPENSE')
        self.client.force_login(self.user)

    def batch(self, lines, *, mapped=True, account=None, user=None):
        batch, _ = stage_statement(user or self.user, (account or self.account).pk,
            ('Date,Text,Amount,Id\n' + lines).encode(), 'local.csv', 'CSV')
        if mapped:
            map_csv_batch(user or self.user, batch.pk, MAPPING)
            batch.refresh_from_db()
        return batch

    def decision(self, action='SKIP', category=None):
        return dict(action=action, category_id=category, matched_movement_id=None, invoice_id=None, counterparty_account_id=None, counterparty_amount=None)

    def test_upload_shortcut_and_origin_survive_mapping_review_and_confirmation(self):
        origin = reverse('banking:detail', args=[self.bank.pk]) + f'#account-{self.account.pk}'
        response = self.client.get(reverse('ingestion:index'), {'account': self.account.pk, 'next': origin})
        self.assertEqual(response.context['form']['account'].value(), self.account.pk)
        self.assertEqual(response.context['return_url'], origin)
        response = self.client.get(reverse('ingestion:index'), {'account': self.private_account.pk})
        self.assertFalse(response.context['form']['account'].value())
        response = self.client.post(reverse('ingestion:index'), {'account': self.account.pk, 'next': origin,
            'file_format': 'CSV', 'encoding': 'utf-8-sig', 'statement': SimpleUploadedFile('native.csv', b'Date,Text,Amount,Id\n2026-09-01,Native,-25,native\n')})
        batch = ImportBatch.objects.get()
        self.assertRedirects(response, with_return_url(reverse('ingestion:mapping', args=[batch.pk]), origin))
        response = self.client.post(reverse('ingestion:mapping', args=[batch.pk]), {**MAPPING, 'amount_mode': 'signed', 'next': origin})
        self.assertRedirects(response, with_return_url(reverse('ingestion:review', args=[batch.pk]), origin))
        row = batch.rows.get()
        response = self.client.post(reverse('ingestion:review', args=[batch.pk]), {'next': origin, f'row-{row.pk}-action': 'CREATE', f'row-{row.pk}-category': self.category.pk})
        self.assertRedirects(response, with_return_url(reverse('ingestion:confirmation', args=[batch.pk]), origin))
        batch.refresh_from_db()
        response = self.client.post(reverse('ingestion:confirmation', args=[batch.pk]), {'next': origin, 'digest': decision_digest(batch), 'reviewed': 'on'})
        self.assertRedirects(response, origin)
        self.assertEqual(Transaction.objects.get().amount, Decimal('25'))

    def test_review_pagination_saves_only_current_page_and_keeps_whole_batch_gate(self):
        batch = self.batch(''.join(f'2026-09-01,Entry {number},-1,id-{number}\n' for number in range(26)))
        rows = list(batch.rows.all())
        response = self.client.get(reverse('ingestion:review', args=[batch.pk]))
        self.assertEqual(len(response.context['entries']), 25)
        self.assertEqual(response.context['pending_count'], 26)
        self.assertNotContains(response, f'name="row-{rows[-1].pk}-action"')
        response = self.client.post(reverse('ingestion:review', args=[batch.pk]), {f'row-{row.pk}-action': 'SKIP' for row in rows[:25]})
        self.assertEqual(batch.rows.filter(action='SKIP').count(), 25)
        self.assertIn('?page=2', response.url)
        self.assertEqual(batch.rows.get(pk=rows[-1].pk).action, '')
        with self.assertRaises(ValidationError):
            confirm_batch(self.user, batch.pk, decision_digest(batch))
        self.assertEqual((Transaction.objects.count(), BankMovement.objects.count()), (0, 0))
        response = self.client.post(reverse('ingestion:review', args=[batch.pk]), {'page': '2', f'row-{rows[-1].pk}-action': 'SKIP'})
        self.assertRedirects(response, reverse('ingestion:confirmation', args=[batch.pk]))
        self.assertEqual(batch.rows.filter(action='SKIP').count(), 26)

    def test_partial_review_rejects_foreign_rows_and_rolls_back_invalid_subset(self):
        batch = self.batch('2026-09-01,First,-1,first\n2026-09-01,Second,-1,second\n')
        private = self.batch('2026-09-01,Private,-1,private\n', user=self.other, account=self.private_account)
        first, second = batch.rows.all()
        with self.assertRaises(ValidationError):
            save_review(self.user, batch.pk, {first.pk: self.decision(), private.rows.get().pk: self.decision()}, partial=True)
        with self.assertRaises(ValidationError):
            save_review(self.user, batch.pk, {first.pk: self.decision(), second.pk: self.decision('CREATE')}, partial=True)
        self.assertEqual(batch.rows.filter(action='').count(), 2)
        response = self.client.post(reverse('ingestion:review', args=[batch.pk]), {f'row-{first.pk}-action': 'SKIP', f'row-{second.pk}-action': 'SKIP', f'row-{private.rows.get().pk}-action': 'SKIP'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review only the entries shown on this page.')
        self.assertEqual(batch.rows.filter(action='').count(), 2)

    def test_remap_after_review_commit_redirects_to_current_pending_row(self):
        batch = self.batch('2026-09-01,Reviewed cash,-25,reviewed\n')
        original_row = batch.rows.get()
        original_save = save_review
        evidence = (batch.file_hash, batch.raw_text, original_row.raw)

        def remap_after_save(*args, **kwargs):
            saved = original_save(*args, **kwargs)
            map_csv_batch(self.user, batch.pk, MAPPING)
            return saved

        with patch('ingestion.views.save_review', side_effect=remap_after_save):
            response = self.client.post(reverse('ingestion:review', args=[batch.pk]), {f'row-{original_row.pk}-action': 'SKIP'})
        current = batch.rows.get()
        self.assertNotEqual(current.pk, original_row.pk)
        self.assertRedirects(response, reverse('ingestion:review', args=[batch.pk]) + f'?page=1#entry-{current.pk}')
        self.assertEqual(current.action, '')
        batch.refresh_from_db()
        self.assertEqual((batch.file_hash, batch.raw_text, current.raw), evidence)
        self.assertEqual(batch.status, 'READY')
        self.assertEqual((Transaction.objects.count(), BankMovement.objects.count()), (0, 0))

    def test_enormous_or_noncanonical_post_row_identifiers_are_rejected_without_saving(self):
        batch = self.batch('2026-09-01,First,-1,first\n2026-09-01,Second,-1,second\n')
        rows = list(batch.rows.all())
        original_rows = list(batch.rows.values())
        original_batch = ImportBatch.objects.filter(pk=batch.pk).values().get()
        for identifier in ['9' * 5000, f'0{rows[0].pk}', str(rows[0].pk).translate(str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩'))]:
            payload = {f'row-{row.pk}-action': 'SKIP' for row in rows}
            payload[f'row-{identifier}-action'] = 'SKIP'
            with self.subTest(identifier_length=len(identifier)), patch('ingestion.views.save_review') as save:
                # URL-encoded POSTs reach the handler with long names;
                # multipart parsing has a separate header-size limit.
                response = self.client.post(reverse('ingestion:review', args=[batch.pk]),
                    urlencode(payload), content_type='application/x-www-form-urlencoded')
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Review only the entries shown on this page.')
                save.assert_not_called()
                self.assertEqual(list(batch.rows.values()), original_rows)
                self.assertEqual(ImportBatch.objects.filter(pk=batch.pk).values().get(), original_batch)
                self.assertEqual((Transaction.objects.count(), BankMovement.objects.count()), (0, 0))

    def test_bulk_skip_uses_strong_identifiers_preserves_valid_choices_and_ignores_weak_matches(self):
        original = self.batch('2026-09-01,Coffee,-25,confirmed\n')
        save_review(self.user, original.pk, {original.rows.get().pk: self.decision('CREATE', self.category.pk)})
        confirm_batch(self.user, original.pk, decision_digest(original))
        batch = self.batch('2026-09-01,Coffee,-25,confirmed\n2026-09-01,Coffee,-25,\n2026-09-02,Other,-5,new\n')
        rows = list(batch.rows.all())
        evidence = (batch.raw_text, batch.file_hash, list(batch.rows.values_list('raw', flat=True)))
        payload = {'bulk_action': 'skip_confirmed', f'row-{rows[2].pk}-action': 'CREATE'}
        response = self.client.post(reverse('ingestion:review', args=[batch.pk]), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose an owned category')
        self.assertEqual(batch.rows.filter(action='').count(), 3)
        payload[f'row-{rows[2].pk}-category'] = self.category.pk
        response = self.client.post(reverse('ingestion:review', args=[batch.pk]), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(batch.rows.values_list('action', flat=True)), ['SKIP', '', 'CREATE'])
        batch.refresh_from_db()
        self.assertEqual(evidence, (batch.raw_text, batch.file_hash, list(batch.rows.values_list('raw', flat=True))))
        self.assertEqual((Transaction.objects.count(), BankMovement.objects.count()), (1, 1))

    def test_mapping_reuse_is_deliberate_owned_compatible_and_does_not_parse(self):
        original = self.batch('2026-09-01,Original,-25,original\n')
        save_review(self.user, original.pk, {original.rows.get().pk: self.decision('CREATE', self.category.pk)})
        confirm_batch(self.user, original.pk, decision_digest(original))
        pending = self.batch('2026-09-02,New,-5,new\n', mapped=False)
        mapping_url = reverse('ingestion:mapping', args=[pending.pk])
        response = self.client.get(mapping_url)
        self.assertContains(response, 'Reuse last confirmed column mapping')
        self.assertFalse(response.context['form']['date_column'].value())
        response = self.client.get(mapping_url, {'reuse': '1'})
        self.assertEqual(response.context['form']['date_column'].value(), 'Date')
        pending.refresh_from_db()
        self.assertEqual((pending.status, pending.mapping, pending.rows.count()), ('STAGED', {}, 0))
        private = self.batch('2026-09-03,Private,-5,private\n', mapped=False, user=self.other, account=self.private_account)
        self.client.force_login(self.other)
        response = self.client.get(reverse('ingestion:mapping', args=[private.pk]), {'reuse': '1'})
        self.assertFalse(response.context['previous_mapping'])
        self.assertFalse(response.context['form']['date_column'].value())

    def test_bulk_rechecks_confirmation_and_new_decisions_after_suggestions_are_loaded(self):
        original = self.batch('2026-09-01,Coffee,-25,confirmed\n')
        save_review(self.user, original.pk, {original.rows.get().pk: self.decision('CREATE', self.category.pk)})
        confirm_batch(self.user, original.pk, decision_digest(original))
        batch = self.batch('2026-09-01,Coffee,-25,confirmed\n2026-09-02,Other,-5,new\n')
        first, second = batch.rows.all()
        original_save = save_review

        def undo_before_lock(*args, **kwargs):
            undo_batch(self.user, original.pk)
            return original_save(*args, **kwargs)

        payload = {'bulk_action': 'skip_confirmed', f'row-{second.pk}-action': 'CREATE', f'row-{second.pk}-category': self.category.pk}
        with patch('ingestion.views.save_review', side_effect=undo_before_lock):
            response = self.client.post(reverse('ingestion:review', args=[batch.pk]), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The review changed.')
        self.assertEqual(batch.rows.filter(action='').count(), 2)
        self.assertFalse(Transaction.objects.exists())

        # A fresh confirmed original restores the strong-ID suggestion.
        replacement = self.batch('2026-09-01,Coffee,-25,confirmed\n2026-09-02,Unused,-1,unused\n')
        save_review(self.user, replacement.pk, {row.pk: self.decision('CREATE', self.category.pk) for row in replacement.rows.all()})
        confirm_batch(self.user, replacement.pk, decision_digest(replacement))

        def choose_before_lock(*args, **kwargs):
            original_save(self.user, batch.pk, {first.pk: self.decision('SKIP')}, partial=True)
            return original_save(*args, **kwargs)

        with patch('ingestion.views.save_review', side_effect=choose_before_lock):
            response = self.client.post(reverse('ingestion:review', args=[batch.pk]), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The review changed.')
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.action, second.action), ('SKIP', ''))
        self.assertEqual(Transaction.objects.count(), 2)

    def test_unsafe_return_and_invalid_account_shortcuts_remain_local(self):
        for account in ['invalid', str(self.private_account.pk), '999999999999999999999']:
            response = self.client.get(reverse('ingestion:index'), {'account': account, 'next': '//external.example'})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context['form']['account'].value())
            self.assertEqual(response.context['return_url'], '')
