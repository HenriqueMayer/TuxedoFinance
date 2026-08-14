import csv
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from transactions.invoice_extraction import (
    assign_categories,
    extract_installment,
    parse_inter_pdf,
    parse_nubank_csv,
    parse_nubank_pdf,
    source_key,
)


class InvoiceExtractionTests(SimpleTestCase):
    def test_nubank_csv_excludes_payments_and_refunds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Nubank_2026-03-02.csv'
            path.write_text(
                'date,title,amount\n'
                '2026-02-22,Purchase - Parcela 1/3,"10,50"\n'
                '2026-02-21,Pagamento recebido,"- 20,00"\n'
                '2026-02-20,"Estorno de ""Purchase""","- 10,50"\n',
                encoding='utf-8',
            )

            rows, excluded = parse_nubank_csv(path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].statement_month, '2026-03-01')
        self.assertEqual(rows[0].statement_due_date, '2026-03-02')
        self.assertEqual(rows[0].source_installment_number, 1)
        self.assertEqual(rows[0].source_installment_total, 3)
        self.assertEqual(excluded['payment_or_refund'], 2)

    @patch('transactions.invoice_extraction.read_pdf_pages')
    def test_nubank_pdf_extracts_transaction_section_and_card(self, read_pages):
        read_pages.return_value = [
            'FATURA 04 MAI 2026',
            'TRANSAÇÕES\n 26 MAR   •••• 3416    Store - Parcela 3/12   R$ 66,65\n'
            ' 31 MAR   Pagamento em 31 MAR   −R$ 280,17',
        ]
        path = Path('/tmp/Nubank_2026-05-02.pdf')

        rows, excluded = parse_nubank_pdf(path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].purchase_date, '2026-03-26')
        self.assertEqual(rows[0].statement_due_date, '2026-05-04')
        self.assertEqual(rows[0].source_card, '3416')
        self.assertEqual(excluded['payment_or_refund'], 1)

    @patch('transactions.invoice_extraction.read_pdf_pages')
    def test_inter_pdf_handles_multiple_pages_cards_and_credits(self, read_pages):
        read_pages.return_value = [
            'Data de Vencimento\n text 01/06/2026',
            'Despesas da fatura\nCARTÃO 5364****2727\n'
            ' 23 de abr. 2026   CLAUDE.AI SUBSCRIPTION   -   R$ 110,00\n'
            ' 30 de abr. 2026   PAGAMENTO ON LINE       -   + R$ 110,00',
            'Despesas da fatura\nCARTÃO 5364****7956\n'
            ' 04 de mai. 2026   RESTAURANTE TESTE       -   R$ 40,00',
        ]
        path = Path('/tmp/fatura-inter-2026-05.pdf')

        rows, excluded = parse_inter_pdf(path)

        self.assertEqual(len(rows), 2)
        self.assertEqual({row.source_card for row in rows}, {'5364****2727', '5364****7956'})
        self.assertTrue(all(row.statement_month == '2026-05-01' for row in rows))
        self.assertTrue(all(row.statement_due_date == '2026-06-01' for row in rows))
        self.assertEqual(excluded['payment_or_refund'], 1)

    def test_category_requires_one_unambiguous_rule(self):
        row = type('Row', (), {'title': 'P K DOCERIA E CAFETERIA', 'category': ''})()
        assign_categories([row], [('DOCERIA', 'Doces'), ('CAFETERIA', 'Cafeterias')])
        self.assertEqual(row.category, 'indefinido')

        row.title = 'DL*UberRides'
        assign_categories([row], [('UBER', 'Aplicativo')])
        self.assertEqual(row.category, 'Aplicativo')

    def test_source_key_is_stable_and_installment_parser_accepts_both_banks(self):
        path = Path('/tmp/source.pdf')
        arguments = (path, 2, '1234', date(2026, 1, 3), 'Store', __import__('decimal').Decimal('10.00'), 0)
        self.assertEqual(source_key(*arguments), source_key(*arguments))
        self.assertEqual(extract_installment('Store - Parcela 2/12'), (2, 12))
        self.assertEqual(extract_installment('Store (Parcela 02 de 03)'), (2, 3))
