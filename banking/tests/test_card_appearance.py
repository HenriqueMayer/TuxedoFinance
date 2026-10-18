"""Persisted card appearance never changes its financial configuration."""
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from banking.forms import CreditCardForm, DebitCardForm
from banking.models import Bank, BankAccount, CreditCard, DebitCard


class InputAttributes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'input' and attributes.get('name'):
            self.inputs[attributes['name']] = attributes


class CardAppearanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('card-appearance', password='test')
        self.other = get_user_model().objects.create_user('card-other', password='test')
        bank = Bank.objects.create(user=self.user, name='Example Bank')
        self.account = BankAccount.objects.create(
            user=self.user, bank=bank, name='Checking', currency='BRL',
        )
        other_bank = Bank.objects.create(user=self.other, name='Private Bank')
        self.other_account = BankAccount.objects.create(
            user=self.other, bank=other_bank, name='Private account', currency='BRL',
        )

    def card_types(self):
        return ((DebitCard, DebitCardForm, {}), (CreditCard, CreditCardForm, {
            'closing_day': 24, 'due_day': 10, 'card_type': CreditCard.CardType.VIRTUAL,
        }))

    def test_existing_and_new_cards_have_safe_default_appearance(self):
        for model, _, extra in self.card_types():
            with self.subTest(model=model.__name__):
                card = model.objects.create(user=self.user, account=self.account, name='Daily', **extra)
                self.assertEqual((card.color, card.gradient_end, card.gradient_angle), ('#253330', '', 135))
                card.full_clean()

    def test_model_rejects_invalid_colors_and_gradient_angles(self):
        for model, _, extra in self.card_types():
            for field, value in (('color', 'red'), ('color', '#FFF'),
                                 ('gradient_end', '#12345Z'), ('gradient_angle', -1),
                                 ('gradient_angle', 360)):
                with self.subTest(model=model.__name__, field=field, value=value):
                    card = model(user=self.user, account=self.account, name='Invalid', **extra)
                    setattr(card, field, value)
                    with self.assertRaises(ValidationError) as error:
                        card.full_clean()
                    self.assertIn(field, error.exception.message_dict)

    def test_database_rejects_out_of_range_gradient_angles(self):
        for model, _, extra in self.card_types():
            with self.subTest(model=model.__name__), self.assertRaises(IntegrityError), transaction.atomic():
                model.objects.create(user=self.user, account=self.account, name='Invalid', gradient_angle=360, **extra)

    def test_creation_preserves_original_posts_and_offers_the_four_base_presets(self):
        for _, form_type, extra in self.card_types():
            initial = form_type(user=self.user)
            self.assertFalse(initial['use_gradient'].value())
            self.assertEqual(initial['gradient_end'].value(), '#253330')
            self.assertEqual(initial['gradient_angle'].value(), 135)
            for preset in (None, '#253330', '#5B3E7C', '#C6A173', '#315D50'):
                with self.subTest(form=form_type.__name__, preset=preset):
                    data = {'account': self.account.pk, 'name': f'Daily {preset}', **extra}
                    if preset:
                        data['color'] = preset
                    form = form_type(data, user=self.user)
                    self.assertTrue(form.is_valid(), form.errors)
                    card = form.save()
                    self.assertEqual(card.color, preset or '#253330')
                    self.assertEqual(card.gradient_end, '')
                    self.assertIn('use_gradient', form.fields)
                    self.assertIn('gradient_end', form.fields)
            forged = form_type({'account': self.account.pk, 'name': 'Custom create', 'color': '#FFFFFF', **extra}, user=self.user)
            self.assertFalse(forged.is_valid())
            self.assertIn('color', forged.errors)

    def test_creation_can_persist_a_gradient_without_changing_financial_fields(self):
        for _, form_type, extra in self.card_types():
            with self.subTest(form=form_type.__name__):
                form = form_type({'account': self.account.pk, 'name': 'Created gradient',
                                  'color': '#5B3E7C', 'use_gradient': 'on',
                                  'gradient_end': '#c6a173', 'gradient_angle': '359',
                                  **extra}, user=self.user)
                self.assertTrue(form.is_valid(), form.errors)
                card = form.save()
                self.assertEqual((card.color, card.gradient_end, card.gradient_angle),
                                 ('#5B3E7C', '#C6A173', 359))
                self.assertEqual((card.account_id, card.user_id), (self.account.pk, self.user.pk))
                if isinstance(card, CreditCard):
                    self.assertEqual((card.closing_day, card.due_day, card.card_type), (24, 10, 'VIRTUAL'))

    def test_gradient_creation_and_editing_reject_out_of_range_and_missing_values(self):
        for model, form_type, extra in self.card_types():
            for editing in (False, True):
                for field, value in (('gradient_angle', '-1'), ('gradient_angle', '360'),
                                     ('gradient_end', ''), ('gradient_end', 'red')):
                    with self.subTest(model=model.__name__, editing=editing, field=field, value=value):
                        instance = model.objects.create(user=self.user, account=self.account,
                                                        name='Existing', **extra) if editing else None
                        data = {'account': self.account.pk, 'name': 'Invalid gradient',
                                'color': '#315D50', 'use_gradient': 'on',
                                'gradient_end': '#C6A173', 'gradient_angle': '135', **extra}
                        data[field] = value
                        form = form_type(data, user=self.user, instance=instance)
                        self.assertFalse(form.is_valid())
                        self.assertIn(field, form.errors)
                        if instance:
                            instance.delete()

    def test_inactive_creation_gradient_does_not_validate_or_persist_stale_fields(self):
        for _, form_type, extra in self.card_types():
            with self.subTest(form=form_type.__name__):
                form = form_type({'account': self.account.pk, 'name': 'Plain create',
                                  'color': '#315D50', 'gradient_end': 'inactive',
                                  'gradient_angle': 'inactive', **extra}, user=self.user)
                self.assertTrue(form.is_valid(), form.errors)
                card = form.save()
                self.assertEqual((card.color, card.gradient_end, card.gradient_angle),
                                 ('#315D50', '', 135))

    def test_edit_persists_custom_gradient_and_old_posts_preserve_it(self):
        for model, form_type, extra in self.card_types():
            with self.subTest(model=model.__name__):
                card = model.objects.create(user=self.user, account=self.account, name='Daily', **extra)
                original = {'account': self.account.pk, 'name': 'Travel', **extra}
                form = form_type({**original, 'color': '#aabbcc', 'use_gradient': 'on',
                                  'gradient_end': '#112233', 'gradient_angle': '270'},
                                 user=self.user, instance=card)
                self.assertTrue(form.is_valid(), form.errors)
                card = form.save()
                self.assertEqual((card.color, card.gradient_end, card.gradient_angle), ('#AABBCC', '#112233', 270))
                legacy = form_type(original, user=self.user, instance=card)
                self.assertTrue(legacy.is_valid(), legacy.errors)
                card = legacy.save()
                self.assertEqual((card.color, card.gradient_end, card.gradient_angle), ('#AABBCC', '#112233', 270))
                if isinstance(card, CreditCard):
                    self.assertEqual((card.closing_day, card.due_day, card.card_type), (24, 10, 'VIRTUAL'))

    def test_disabling_gradient_ignores_inactive_values(self):
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Daily',
                                         closing_day=24, due_day=10, gradient_end='#FFFFFF')
        form = CreditCardForm({'account': self.account.pk, 'name': 'Daily', 'card_type': 'PHYSICAL',
                               'closing_day': 24, 'due_day': 10, 'color': '#315D50',
                               'gradient_end': 'inactive', 'gradient_angle': 'inactive'},
                              user=self.user, instance=card)
        self.assertTrue(form.is_valid(), form.errors)
        card = form.save()
        self.assertEqual(card.gradient_end, '')
        self.assertEqual(card.color, '#315D50')

    def test_appearance_does_not_bypass_account_ownership(self):
        for _, form_type, extra in self.card_types():
            with self.subTest(form=form_type.__name__):
                form = form_type({'account': self.other_account.pk, 'name': 'Forged',
                                  'color': '#5B3E7C', **extra}, user=self.user)
                self.assertFalse(form.is_valid())
                self.assertIn('account', form.errors)

    def test_invalid_edit_keeps_native_gradient_controls_available(self):
        card = DebitCard.objects.create(user=self.user, account=self.account, name='Daily')
        self.client.force_login(self.user)
        response = self.client.post(reverse('banking:debit_card_update', args=[card.pk]), {
            'account': self.account.pk, 'name': '', 'color': '#315D50',
            'gradient_end': '#315D50', 'gradient_angle': '135',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-card-appearance-form')
        controls = InputAttributes()
        controls.feed(response.content.decode())
        for name in ('use_gradient', 'gradient_end', 'gradient_angle'):
            self.assertIn(name, controls.inputs)
            self.assertNotIn('disabled', controls.inputs[name])
        card.refresh_from_db()
        self.assertEqual((card.color, card.gradient_end), ('#253330', ''))

    def test_invalid_creation_keeps_native_angle_and_server_error_for_recovery(self):
        self.client.force_login(self.user)
        for route, extra in (('banking:debit_card_create', {}),
                             ('banking:credit_card_create', {'card_type': 'PHYSICAL',
                              'closing_day': '24', 'due_day': '10'})):
            with self.subTest(route=route):
                response = self.client.post(reverse(route), {
                    'account': self.account.pk, 'name': 'Invalid angle', 'color': '#315D50',
                    'use_gradient': 'on', 'gradient_end': '#C6A173', 'gradient_angle': '400', **extra,
                })
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id_gradient_angle-error-1')
                controls = InputAttributes()
                controls.feed(response.content.decode())
                angle = controls.inputs['gradient_angle']
                self.assertEqual(angle['type'], 'number')
                self.assertEqual(angle['value'], '400')
                self.assertEqual((angle['min'], angle['max']), ('0', '359'))
                self.assertEqual(angle['aria-invalid'], 'true')
                self.assertNotIn('disabled', angle)
                self.assertNotIn('hidden', angle)
