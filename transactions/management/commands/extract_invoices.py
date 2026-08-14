from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from transactions.invoice_extraction import extract_invoices, write_invoice_csv


DEFAULT_INPUT = Path('/home/hmayer/Documents/Datas/Faturas')
DEFAULT_CATEGORIES = settings.BASE_DIR / 'docs/CategoriesCollection/categories_ptbr.csv'
DEFAULT_RULES = settings.BASE_DIR / 'docs/CategoriesCollection/invoice_category_rules_ptbr.csv'


class Command(BaseCommand):
    help = 'Extract Nubank and Banco Inter statement expenses to a reviewable CSV.'

    def add_arguments(self, parser):
        parser.add_argument('input_dir', nargs='?', type=Path, default=DEFAULT_INPUT)
        parser.add_argument('--output', type=Path)
        parser.add_argument('--categories', type=Path, default=DEFAULT_CATEGORIES)
        parser.add_argument('--rules', type=Path, default=DEFAULT_RULES)

    def handle(self, *args, **options):
        input_dir = options['input_dir'].expanduser().resolve()
        output = (options['output'] or input_dir / 'faturas_extraidas.csv').expanduser().resolve()
        categories = options['categories'].expanduser().resolve()
        rules = options['rules'].expanduser().resolve()
        if not input_dir.is_dir():
            raise CommandError(f'Input directory not found: {input_dir}')
        if not categories.is_file():
            raise CommandError(f'Category dictionary not found: {categories}')
        try:
            rows, excluded = extract_invoices(input_dir, categories, rules)
            write_invoice_csv(output, rows)
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error

        undefined = sum(row.category == 'indefinido' for row in rows)
        excluded_total = sum(excluded.values())
        self.stdout.write(self.style.SUCCESS(f'Extracted {len(rows)} expenses to {output}'))
        self.stdout.write(f'Categories requiring review: {undefined}')
        self.stdout.write(f'Payments/refunds excluded: {excluded_total}')
