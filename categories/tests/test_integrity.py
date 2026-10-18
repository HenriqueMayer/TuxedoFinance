# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import csv
import io
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from categories.forms import CategoryForm
from categories.models import Category
from categories.importing import CATEGORY_CSV_MAX_BYTES, CATEGORY_CSV_MAX_ROWS, _read_category_csv


HEADER = 'name,transaction_type,parent_category\n'


class CategoryHierarchyIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('category-integrity', password='test')
        cls.other = get_user_model().objects.create_user('category-integrity-private', password='test')
        Category.objects.filter(user__in=[cls.user, cls.other]).delete()
        cls.root = Category.objects.create(user=cls.user, name='Root')
        cls.child = Category.objects.create(user=cls.user, name='Child', parent_category=cls.root)
        cls.leaf = Category.objects.create(user=cls.user, name='Leaf', parent_category=cls.child)
        cls.independent = Category.objects.create(user=cls.user, name='Independent')
        cls.foreign = Category.objects.create(user=cls.other, name='Private')

    def test_model_rejects_self_and_descendants_as_parents(self):
        for parent in [self.root, self.child, self.leaf]:
            with self.subTest(parent=parent.pk):
                self.root.parent_category = parent
                with self.assertRaises(ValidationError) as result:
                    self.root.full_clean()
                self.assertIn('parent_category', result.exception.message_dict)
        self.root.refresh_from_db()
        self.assertIsNone(self.root.parent_category)

    def test_model_rejects_foreign_parent_and_foreign_ancestor(self):
        self.root.parent_category = self.foreign
        with self.assertRaisesMessage(ValidationError, 'must belong to you'):
            self.root.full_clean()
        Category.objects.filter(pk=self.independent.pk).update(parent_category=self.foreign)
        self.root.parent_category = self.independent
        with self.assertRaisesMessage(ValidationError, 'must belong to you'):
            self.root.full_clean()

    def test_model_rejects_attaching_a_new_category_to_a_legacy_cycle(self):
        Category.objects.filter(pk=self.root.pk).update(parent_category=self.leaf)
        new = Category(user=self.user, name='New', parent_category=self.child)
        with self.assertRaisesMessage(ValidationError, 'circular hierarchy'):
            new.full_clean()

    def test_parent_picker_excludes_all_descendants_and_foreign_categories(self):
        form = CategoryForm(instance=self.root, user=self.user)
        self.assertEqual(list(form.fields['parent_category'].queryset), [self.independent])
        # Traversal must also terminate when an older graph already has a cycle.
        Category.objects.filter(pk=self.root.pk).update(parent_category=self.leaf)
        form = CategoryForm(instance=self.root, user=self.user)
        self.assertEqual(list(form.fields['parent_category'].queryset), [self.independent])

    def test_direct_invalid_post_keeps_data_for_recovery_without_changing_graph(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('categories:update', args=[self.root.pk]), {
            'name': 'Changed root', 'transaction_type': '', 'parent_category': self.leaf.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'parent_category',
                             'Select a valid choice. That choice is not one of the available choices.')
        self.assertEqual(response.context['form']['name'].value(), 'Changed root')
        self.root.refresh_from_db()
        self.assertEqual(self.root.name, 'Root')
        self.assertIsNone(self.root.parent_category)

    def test_model_validation_is_used_when_form_selects_a_legacy_cycle(self):
        Category.objects.filter(pk=self.root.pk).update(parent_category=self.leaf)
        form = CategoryForm({'name': 'New', 'parent_category': self.child.pk}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('circular hierarchy', str(form.errors['parent_category']))

    def test_save_rechecks_a_parent_moved_after_form_validation(self):
        self.client.force_login(self.user)
        validate = CategoryForm.is_valid

        def move_after_validation(form):
            valid = validate(form)
            if valid:
                Category.objects.filter(pk=self.independent.pk).update(parent_category=self.leaf)
            return valid

        with patch.object(CategoryForm, 'is_valid', move_after_validation):
            response = self.client.post(reverse('categories:update', args=[self.root.pk]), {
                'name': 'Changed root', 'parent_category': self.independent.pk,
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn('circular hierarchy', str(response.context['form'].errors['parent_category']))
        self.root.refresh_from_db()
        self.assertEqual(self.root.name, 'Root')
        self.assertIsNone(self.root.parent_category_id)

    def test_valid_reparent_and_detach_preserve_descendant_links(self):
        self.client.force_login(self.user)
        for parent in [self.independent.pk, '']:
            response = self.client.post(reverse('categories:update', args=[self.root.pk]), {
                'name': 'Root', 'transaction_type': '', 'parent_category': parent,
            })
            self.assertRedirects(response, reverse('categories:list'))
            self.root.refresh_from_db()
            self.assertEqual(self.root.parent_category_id, parent or None)
            self.child.refresh_from_db()
            self.assertEqual(self.child.parent_category_id, self.root.pk)


class CategoryCsvIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('bounded-category-csv', password='test')
        cls.other = get_user_model().objects.create_user('bounded-category-csv-other', password='test')
        Category.objects.filter(user__in=[cls.user, cls.other]).delete()

    def setUp(self):
        self.client.force_login(self.user)

    def upload(self, content):
        blob = content.encode('utf-8') if isinstance(content, str) else content
        return self.client.post(reverse('categories:import'), {
            'file': SimpleUploadedFile('categories.csv', blob, 'text/csv'),
        })

    def assert_rejected(self, content, message):
        before = list(Category.objects.filter(user=self.user).values())
        response = self.upload(content)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, message)
        self.assertEqual(list(Category.objects.filter(user=self.user).values()), before)
        return response

    def test_missing_and_extra_cells_are_rejected_before_any_import(self):
        for row in ['Missing,EXPENSE\n', 'Extra,EXPENSE,,unexpected\n', 'OnlyName\n']:
            with self.subTest(row=row):
                self.assert_rejected(HEADER + 'Valid,EXPENSE,\n' + row, 'exactly three columns')

    def test_malformed_quoting_and_csv_field_limit_have_controlled_errors(self):
        for row in ['"Unclosed,EXPENSE,\n', '"Quoted"suffix,EXPENSE,\n', 'X' * (128 * 1024 + 1) + ',EXPENSE,\n']:
            with self.subTest(prefix=row[:20]):
                self.assert_rejected(HEADER + 'Valid,EXPENSE,\n' + row, 'CSV is malformed')

    def test_invalid_utf8_and_header_are_rejected_without_writes(self):
        self.assert_rejected(HEADER.encode() + b'\xff,EXPENSE,\n', 'must use UTF-8')
        self.assert_rejected('name,transaction_type,parent_category,extra\nValid,EXPENSE,,\n', 'CSV header must be')

    def test_byte_limit_is_checked_before_import_and_reader_never_reads_unbounded(self):
        blob = HEADER.encode() + b'x' * CATEGORY_CSV_MAX_BYTES
        self.assert_rejected(blob, 'must be no larger than 2 MiB')
        uploaded = Mock(wraps=SimpleUploadedFile('categories.csv', blob, 'text/csv'))
        with self.assertRaisesMessage(ValueError, 'must be no larger than 2 MiB'):
            _read_category_csv(uploaded)
        uploaded.read.assert_called_once_with(CATEGORY_CSV_MAX_BYTES + 1)

    def test_row_limit_accepts_boundary_and_rejects_one_more_without_writes(self):
        content = HEADER + ''.join(f'Category {number},EXPENSE,\n' for number in range(CATEGORY_CSV_MAX_ROWS))
        self.assert_rejected(content + 'One more,EXPENSE,\n', 'at most 500 category rows')
        response = self.upload(content)
        self.assertRedirects(response, reverse('categories:list'))
        self.assertEqual(Category.objects.filter(user=self.user).count(), CATEGORY_CSV_MAX_ROWS)

    def test_blank_rows_cannot_bypass_row_limit(self):
        self.assert_rejected(HEADER + '\n' * CATEGORY_CSV_MAX_ROWS + 'Late,EXPENSE,\n', 'at most 500 category rows')

    def test_csv_rejects_self_and_indirect_cycles_before_any_import(self):
        for rows in ['Self,EXPENSE,Self\n', 'A,EXPENSE,B\nB,EXPENSE,A\n',
                     'A,EXPENSE,B\nB,EXPENSE,C\nC,EXPENSE,A\n']:
            with self.subTest(rows=rows):
                self.assert_rejected(HEADER + 'Valid,EXPENSE,\n' + rows, 'circular hierarchy')

    def test_new_csv_branch_cannot_attach_to_a_legacy_cycle_or_foreign_parent(self):
        first = Category.objects.create(user=self.user, name='First')
        second = Category.objects.create(user=self.user, name='Second', parent_category=first)
        Category.objects.filter(pk=first.pk).update(parent_category=second)
        self.assert_rejected(HEADER + 'Valid,EXPENSE,\nNew,EXPENSE,First\n', 'circular hierarchy')
        private = Category.objects.create(user=self.other, name='Private')
        self.assert_rejected(HEADER + 'New,EXPENSE,Private\n', 'Parent category not found')
        Category.objects.filter(pk=second.pk).update(parent_category=private)
        self.assert_rejected(HEADER + 'New,EXPENSE,First\n', 'must belong to you')

    def test_skipped_existing_names_keep_their_real_relationships(self):
        existing = Category.objects.create(user=self.user, name='Existing')
        response = self.upload(HEADER + 'Existing,INCOME,New\nNew,EXPENSE,Existing\n')
        self.assertRedirects(response, reverse('categories:list'))
        existing.refresh_from_db()
        self.assertIsNone(existing.parent_category_id)
        self.assertIsNone(existing.transaction_type)
        self.assertEqual(Category.objects.get(user=self.user, name='New').parent_category_id, existing.pk)

    def test_valid_bom_quoted_multiline_csv_roundtrips_hierarchy_and_owner(self):
        parent = Category.objects.create(user=self.user, name='Meals, cafés', transaction_type='EXPENSE')
        child_name = 'Lunch "special"\nweekend'
        Category.objects.create(user=self.user, name=child_name, parent_category=parent)
        exported = self.client.get(reverse('categories:export')).content
        self.assertTrue(exported.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(len(list(csv.reader(io.StringIO(exported.decode('utf-8-sig'))))), 3)
        self.client.force_login(self.other)
        response = self.upload(exported)
        self.assertRedirects(response, reverse('categories:list'))
        imported_parent = Category.objects.get(user=self.other, name=parent.name)
        imported_child = Category.objects.get(user=self.other, name=child_name)
        self.assertEqual(imported_child.parent_category_id, imported_parent.pk)
        self.assertNotEqual(imported_parent.pk, parent.pk)
        self.assertEqual(Category.objects.filter(user=self.user).count(), 2)

    def test_late_database_failure_rolls_back_all_new_categories(self):
        save = Category.save

        def fail_second(category, *args, **kwargs):
            if category.name == 'Second' and kwargs.get('update_fields'):
                raise ValidationError('The hierarchy changed during import.')
            return save(category, *args, **kwargs)

        with patch.object(Category, 'save', fail_second):
            self.assert_rejected(HEADER + 'First,EXPENSE,\nSecond,EXPENSE,First\n', 'hierarchy changed during import')
