from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from ingestion.parsers import inspect_csv, parse_csv, parse_ofx


class StatementParserTests(SimpleTestCase):
    def test_explicit_brazilian_conventions_and_original_text(self):
        blob = 'Data;Texto;Valor;Id\n12/10/2026;=literal;"-1.234,56";abc\n'.encode()
        rows = parse_csv(blob, date_column='Data', description_column='Texto', amount_column='Valor', id_column='Id', date_format='%d/%m/%Y', decimal_mark=',')
        self.assertEqual(rows[0]['date'], '2026-10-12')
        self.assertEqual(rows[0]['amount'], '-1234.56')
        self.assertEqual(rows[0]['description'], '=literal')
        self.assertEqual(rows[0]['raw']['Valor'], '-1.234,56')

    def test_reject_ambiguous_report_duplicates_and_rounding(self):
        for blob in [b'billed_month,total_amount,payment_channel\n2026-10,100,CREDIT_CARD\n', b'Date,Date,Amount\nx,y,1\n']:
            with self.assertRaises(ValidationError):
                inspect_csv(blob)
        with self.assertRaises(ValidationError):
            parse_csv(b'Date,Text,Amount\n2026-10-12,X,1.234\n', date_column='Date', description_column='Text', amount_column='Amount')

    def test_ofx_sgml_and_xml_no_entities(self):
        for xml in (False, True):
            field = lambda name, val: f'<{name}>{val}' + (f'</{name}>' if xml else '\n')
            blob = ('<OFX>' + field('CURDEF', 'BRL') + field('ACCTID', '12345678') + '<STMTTRN>' + field('DTPOSTED', '20261012120000[-3:BRT]') + field('TRNAMT', '-25.50') + field('FITID', 'id1') + field('MEMO', 'A &amp; B') + '</STMTTRN><LEDGERBAL>' + field('BALAMT', '974.50') + field('DTASOF', '20261012') + '</LEDGERBAL></OFX>').encode()
            parsed = parse_ofx(blob)
            self.assertEqual(parsed['rows'][0]['description'], 'A & B')
            self.assertEqual(parsed['closing_balance'], '974.50')
            self.assertEqual(parsed['account_hint'], '5678')
        with self.assertRaises(ValidationError):
            parse_ofx(b'<!DOCTYPE OFX SYSTEM "file:///etc/passwd"><OFX></OFX>')
