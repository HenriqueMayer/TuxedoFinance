# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import csv
from decimal import Decimal
import io

from django.contrib.auth.models import User
from django.test import TestCase, SimpleTestCase
from django.urls import reverse

from categories.models import Category
from core.csv import export_row, spreadsheet_cell


class SpreadsheetCellTests(SimpleTestCase):
    def test_only_explicit_spreadsheet_text_is_neutralized(self):
        for value in ('=1+1', '+SUM(A1)', '-1', '@SUM(A1)', '\tformula', '\ntext', '  =1+1'):
            self.assertEqual(spreadsheet_cell(value), "'" + value)
            self.assertEqual(export_row([value]), [value])
        for value in ('ordinary', "'literal", 'A,B', 'line\nline', 'João', Decimal('-12.30'), 0):
            self.assertEqual(spreadsheet_cell(value), value)


class CategoryExportSafetyTests(TestCase):
    def test_raw_roundtrip_and_explicit_spreadsheet_variant_have_distinct_contracts(self):
        user = User.objects.create_user('csv-policy')
        self.client.force_login(user)
        parent = Category.objects.create(user=user, name='=1+1')
        Category.objects.create(user=user, name="'literal", parent_category=parent)
        url = reverse('categories:export')
        raw = self.client.get(url)
        safe = self.client.get(url, {'format': 'spreadsheet'})
        rows = list(csv.DictReader(io.StringIO(raw.content.decode('utf-8-sig'))))
        safe_rows = list(csv.DictReader(io.StringIO(safe.content.decode('utf-8-sig'))))
        self.assertIn('=1+1', [row['name'] for row in rows])
        self.assertIn("'=1+1", [row['name'] for row in safe_rows])
        self.assertEqual(next(row for row in rows if row['name'] == "'literal")['parent_category'], '=1+1')
        self.assertEqual(next(row for row in safe_rows if row['name'] == "'literal")['parent_category'], "'=1+1")
        self.assertIn('categories-spreadsheet.csv', safe['Content-Disposition'])
