"""Seeding coverage for categories."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import translation
from categories.models import Category


User = get_user_model()


class DefaultCategorySeedingTests(TestCase):
    def test_new_user_receives_only_the_approved_default_categories(self):
        expected_names = [
            'Groceries',
            'Food & Dining',
            'Subscriptions',
            'Education',
            'Fitness',
            'Transportation',
            'Pets',
            'Hobbies & Entertainment',
            'Services',
        ]
        user = User.objects.create_user('new-account', password='test')

        categories = Category.objects.filter(user=user).order_by('pk')

        self.assertEqual(
            list(categories.values_list('name', flat=True)),
            expected_names,
        )
        self.assertFalse(categories.exclude(parent_category=None).exists())

    def test_new_portuguese_user_receives_localized_default_categories(self):
        with translation.override('pt-br'):
            user = User.objects.create_user('nova-conta', password='test')

        self.assertEqual(
            list(Category.objects.filter(user=user).order_by('pk').values_list('name', flat=True)),
            [
                'Mercado',
                'Alimentação',
                'Assinaturas',
                'Educação',
                'Academia',
                'Transporte',
                'Animais de estimação',
                'Hobbies e entretenimento',
                'Serviços',
            ],
        )
