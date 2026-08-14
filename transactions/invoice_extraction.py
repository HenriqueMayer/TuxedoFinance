import csv
import hashlib
import re
import subprocess
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


CSV_FIELDS = (
    'source_file',
    'source_page',
    'source_row_key',
    'bank',
    'source_card',
    'credit_card',
    'statement_month',
    'statement_due_date',
    'purchase_date',
    'title',
    'amount',
    'currency',
    'transaction_type',
    'payment_channel',
    'installments',
    'source_installment_number',
    'source_installment_total',
    'category',
)

MONTHS = {
    'JAN': 1,
    'FEV': 2,
    'MAR': 3,
    'ABR': 4,
    'MAI': 5,
    'JUN': 6,
    'JUL': 7,
    'AGO': 8,
    'SET': 9,
    'OUT': 10,
    'NOV': 11,
    'DEZ': 12,
}

INTER_DATE_RE = re.compile(
    r'^\s*(\d{2})\s+de\s+([a-zç.]+)\s+(\d{4})\s{2,}(.+?)\s{2,}-\s{2,}([+−-]?\s*R\$\s*[\d.]+,\d{2})\s*$'
)
NUBANK_DATE_RE = re.compile(
    r'^\s*(\d{2})\s+(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\s+(.*?)\s+([−-]?\s*R\$\s*[\d.]+,\d{2})\s*$'
)
INTER_CARD_RE = re.compile(r'CARTÃO\s+([0-9*]+)', re.IGNORECASE)
INSTALLMENT_RE = re.compile(
    r'(?:Parcela\s+)?(\d{1,2})\s*(?:/|de)\s*(\d{1,2})', re.IGNORECASE
)


@dataclass
class InvoiceRow:
    source_file: str
    source_page: int | str
    source_row_key: str
    bank: str
    source_card: str
    credit_card: str
    statement_month: str
    statement_due_date: str
    purchase_date: str
    title: str
    amount: str
    currency: str = 'BRL'
    transaction_type: str = 'EXPENSE'
    payment_channel: str = 'CREDIT_CARD'
    installments: int = 1
    source_installment_number: int | str = ''
    source_installment_total: int | str = ''
    category: str = 'indefinido'


def normalize(value):
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(character for character in value if not unicodedata.combining(character))
    value = re.sub(r'\s+', ' ', value.upper()).strip()
    return value


def parse_brl_amount(value):
    cleaned = value.replace('R$', '').replace('\u2212', '-').replace(' ', '')
    cleaned = cleaned.replace('.', '').replace(',', '.')
    try:
        return Decimal(cleaned)
    except InvalidOperation as error:
        raise ValueError(f'Invalid monetary value: {value}') from error


def filename_statement_month(path):
    match = re.search(r'(20\d{2})-(\d{2})', path.name)
    if not match:
        raise ValueError(f'Cannot determine statement month from {path.name}')
    return date(int(match.group(1)), int(match.group(2)), 1)


def extract_installment(title):
    match = INSTALLMENT_RE.search(title)
    return (int(match.group(1)), int(match.group(2))) if match else ('', '')


def source_key(path, page, card, purchase_date, title, amount, occurrence):
    identity = '|'.join((
        path.name,
        str(page),
        card,
        purchase_date.isoformat(),
        normalize(title),
        f'{amount:.2f}',
        str(occurrence),
    ))
    return hashlib.sha256(identity.encode()).hexdigest()


def read_pdf_pages(path):
    completed = subprocess.run(
        ['pdftotext', '-layout', str(path), '-'],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.split('\f')


def parse_inter_date(day, month_name, year):
    month_key = normalize(month_name).replace('.', '')[:3]
    return date(int(year), MONTHS[month_key], int(day))


def parse_nubank_pdf(path):
    pages = read_pdf_pages(path)
    statement_month = filename_statement_month(path)
    due_date = ''
    header_match = re.search(
        r'FATURA\s+(\d{2})\s+(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\s+(20\d{2})',
        '\n'.join(pages[:2]),
    )
    if header_match:
        due_date = date(
            int(header_match.group(3)),
            MONTHS[header_match.group(2)],
            int(header_match.group(1)),
        ).isoformat()

    parsed = []
    excluded = Counter()
    occurrences = Counter()
    in_transactions = False
    for page_number, page in enumerate(pages, start=1):
        if 'TRANSAÇÕES' in page:
            in_transactions = True
        if not in_transactions:
            continue
        for line in page.splitlines():
            match = NUBANK_DATE_RE.match(line)
            if not match:
                continue
            purchase_date = date(
                statement_month.year,
                MONTHS[match.group(2)],
                int(match.group(1)),
            )
            if purchase_date > statement_month:
                purchase_date = purchase_date.replace(year=purchase_date.year - 1)
            raw_title = match.group(3).strip()
            card_match = re.match(r'[•*]{4}\s*(\d{4})\s+(.*)', raw_title)
            source_card = card_match.group(1) if card_match else ''
            title = card_match.group(2).strip() if card_match else raw_title
            amount = parse_brl_amount(match.group(4))
            title_key = normalize(title)
            if amount <= 0 or title_key.startswith(('PAGAMENTO ', 'ESTORNO ')):
                excluded['payment_or_refund'] += 1
                continue
            installment_number, installment_total = extract_installment(title)
            identity = (page_number, source_card, purchase_date, title_key, amount)
            occurrence = occurrences[identity]
            occurrences[identity] += 1
            parsed.append(InvoiceRow(
                source_file=path.name,
                source_page=page_number,
                source_row_key=source_key(
                    path, page_number, source_card, purchase_date, title, amount, occurrence
                ),
                bank='NuBank',
                source_card=source_card,
                credit_card='Roxinho',
                statement_month=statement_month.isoformat(),
                statement_due_date=due_date,
                purchase_date=purchase_date.isoformat(),
                title=title,
                amount=f'{amount:.2f}',
                source_installment_number=installment_number,
                source_installment_total=installment_total,
            ))
    return parsed, excluded


def parse_nubank_csv(path):
    statement_month = filename_statement_month(path)
    due_date_match = re.search(r'(20\d{2}-\d{2}-\d{2})', path.name)
    due_date = due_date_match.group(1) if due_date_match else ''
    parsed = []
    excluded = Counter()
    occurrences = Counter()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['date', 'title', 'amount']:
            raise ValueError(f'Unexpected Nubank CSV header in {path.name}')
        for line_number, row in enumerate(reader, start=2):
            purchase_date = date.fromisoformat(row['date'])
            title = row['title'].strip()
            amount = parse_brl_amount(row['amount'])
            title_key = normalize(title)
            if amount <= 0 or title_key.startswith(('PAGAMENTO ', 'ESTORNO ')):
                excluded['payment_or_refund'] += 1
                continue
            installment_number, installment_total = extract_installment(title)
            identity = (line_number, purchase_date, title_key, amount)
            occurrence = occurrences[identity]
            occurrences[identity] += 1
            parsed.append(InvoiceRow(
                source_file=path.name,
                source_page='',
                source_row_key=source_key(
                    path, line_number, '', purchase_date, title, amount, occurrence
                ),
                bank='NuBank',
                source_card='',
                credit_card='Roxinho',
                statement_month=statement_month.isoformat(),
                statement_due_date=due_date,
                purchase_date=purchase_date.isoformat(),
                title=title,
                amount=f'{amount:.2f}',
                source_installment_number=installment_number,
                source_installment_total=installment_total,
            ))
    return parsed, excluded


def parse_inter_pdf(path):
    pages = read_pdf_pages(path)
    statement_month = filename_statement_month(path)
    due_date = ''
    due_match = re.search(
        r'Data de Vencimento.*?(\d{2}/\d{2}/20\d{2})', pages[0], re.DOTALL
    )
    if due_match:
        due_date = date.fromisoformat('-'.join(reversed(due_match.group(1).split('/')))).isoformat()

    parsed = []
    excluded = Counter()
    occurrences = Counter()
    for page_number, page in enumerate(pages, start=1):
        if 'Despesas da fatura' not in page:
            continue
        card_match = INTER_CARD_RE.search(page)
        source_card = card_match.group(1) if card_match else ''
        for line in page.splitlines():
            match = INTER_DATE_RE.match(line)
            if not match:
                continue
            purchase_date = parse_inter_date(match.group(1), match.group(2), match.group(3))
            title = match.group(4).strip()
            raw_amount = match.group(5)
            amount = parse_brl_amount(raw_amount)
            if raw_amount.lstrip().startswith('+') or amount <= 0:
                excluded['payment_or_refund'] += 1
                continue
            installment_number, installment_total = extract_installment(title)
            identity = (page_number, source_card, purchase_date, normalize(title), amount)
            occurrence = occurrences[identity]
            occurrences[identity] += 1
            parsed.append(InvoiceRow(
                source_file=path.name,
                source_page=page_number,
                source_row_key=source_key(
                    path, page_number, source_card, purchase_date, title, amount, occurrence
                ),
                bank='Banco Inter',
                source_card=source_card,
                credit_card='InterBlack',
                statement_month=statement_month.isoformat(),
                statement_due_date=due_date,
                purchase_date=purchase_date.isoformat(),
                title=title,
                amount=f'{amount:.2f}',
                source_installment_number=installment_number,
                source_installment_total=installment_total,
            ))
    return parsed, excluded


def load_categories(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return {row['name'] for row in csv.DictReader(stream)}


def load_category_rules(path, categories):
    if not path.exists():
        return []
    rules = []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['pattern', 'category']:
            raise ValueError('Category rules header must be: pattern,category')
        for row in reader:
            pattern = normalize(row['pattern'])
            category = row['category'].strip()
            if pattern and category not in categories:
                raise ValueError(f'Unknown category in rules: {category}')
            if pattern:
                rules.append((pattern, category))
    return rules


def assign_categories(rows, rules):
    for row in rows:
        normalized_title = normalize(row.title)
        matches = {category for pattern, category in rules if pattern in normalized_title}
        row.category = matches.pop() if len(matches) == 1 else 'indefinido'


def extract_invoices(input_dir, categories_path, rules_path):
    rows = []
    excluded = Counter()
    for path in sorted(input_dir.iterdir()):
        if path.name in {'faturas_extraidas.csv', 'category_rules.csv'}:
            continue
        if path.suffix.lower() == '.csv' and path.name.startswith('Nubank_'):
            file_rows, file_excluded = parse_nubank_csv(path)
        elif path.suffix.lower() == '.pdf' and path.name.startswith('Nubank_'):
            file_rows, file_excluded = parse_nubank_pdf(path)
        elif path.suffix.lower() == '.pdf' and path.name.startswith('fatura-inter-'):
            file_rows, file_excluded = parse_inter_pdf(path)
        else:
            continue
        rows.extend(file_rows)
        excluded.update(file_excluded)

    categories = load_categories(categories_path)
    rules = load_category_rules(rules_path, categories)
    assign_categories(rows, rules)
    rows.sort(key=lambda row: (row.statement_month, row.purchase_date, row.bank, row.title))
    return rows, excluded


def write_invoice_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
