from pathlib import Path

from django.test import TestCase

from ledger.categories import Category
from ledger.category_importing import import_category_rows, read_category_csv

FILES = Path(__file__).resolve().parents[3] / "docs" / "categories"


class SuggestedCategoriesTests(TestCase):
    """The files that the README offers must import as they are."""

    def test_each_file_imports_and_a_second_import_adds_nothing(self):
        from django.contrib.auth import get_user_model

        for name in ("categories.en.csv", "categories.pt-BR.csv"):
            with self.subTest(name):
                user = get_user_model().objects.create_user(
                    f"u-{name}", f"{name}@example.test", "x" * 16
                )
                with (FILES / name).open("rb") as handle:
                    rows = read_category_csv(handle)
                self.assertGreater(import_category_rows(user, rows), 30)
                self.assertEqual(import_category_rows(user, rows), 0)
                # Income and expense categories are both there, and subcategories have a parent.
                types = set(
                    Category.objects.filter(user=user).values_list("transaction_type", flat=True)
                )
                self.assertTrue({"INCOME", "EXPENSE"} <= types)
                self.assertTrue(
                    Category.objects.filter(user=user, parent_category__isnull=False).exists()
                )
