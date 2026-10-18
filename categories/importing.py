# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bounded CSV parsing and atomic, owner-scoped category imports."""

import csv
import io

from django.db import transaction
from django.utils.translation import gettext as _

from categories.models import Category, validate_parent_hierarchy

CATEGORY_CSV_MAX_BYTES = 2 * 1024 * 1024
CATEGORY_CSV_MAX_ROWS = 500


def _read_category_csv(uploaded_file):
    try:
        content = uploaded_file.read(CATEGORY_CSV_MAX_BYTES + 1)
        if len(content) > CATEGORY_CSV_MAX_BYTES:
            raise ValueError(_('The category CSV must be no larger than 2 MiB.'))
        content = content.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError(_('The CSV file must use UTF-8 encoding.')) from error

    reader = csv.reader(io.StringIO(content, newline=''), strict=True)
    expected_columns = ['name', 'transaction_type', 'parent_category']
    if next(reader, None) != expected_columns:
        raise ValueError(
            _('The CSV header must be: name,transaction_type,parent_category.')
        )

    rows = []
    names = set()
    valid_types = {choice for choice, _label in Category.TransactionType.choices}
    for line_number, row in enumerate(reader, start=2):
        if line_number > CATEGORY_CSV_MAX_ROWS + 1:
            raise ValueError(_('Import at most 500 category rows per CSV file.'))
        # Entirely empty physical lines are harmless, but still count toward
        # the bounded record budget. Every actual record needs three cells.
        if not row:
            continue
        if len(row) != len(expected_columns):
            raise ValueError(_('Line %(line)s must contain exactly three columns.') % {'line': line_number})
        name, category_type, parent_name = (value.strip() for value in row)
        category_type = category_type.upper()
        if not name and not category_type and not parent_name:
            continue
        if not name:
            raise ValueError(_('Line %(line)s has no category name.') % {'line': line_number})
        if len(name) > 100 or len(parent_name) > 100:
            raise ValueError(_('Line %(line)s contains a name longer than 100 characters.') % {'line': line_number})
        if category_type and category_type not in valid_types:
            raise ValueError(
                _('Line %(line)s has an invalid transaction type.') % {'line': line_number}
            )
        if name in names:
            raise ValueError(_('The category "%(name)s" appears more than once.') % {'name': name})
        names.add(name)
        rows.append((name, category_type, parent_name))
    return rows


def import_category_rows(user, rows):
    """Validate the complete parent graph before inserting any owned categories."""
    created = 0
    with transaction.atomic():
        existing = {
            category.name: category
            for category in Category.objects.filter(user=user)
        }
        available_names = set(existing) | {name for name, _type, _parent in rows}
        missing_parents = sorted({
            parent_name for _name, _type, parent_name in rows
            if parent_name and parent_name not in available_names
        })
        if missing_parents:
            raise ValueError(_('Parent category not found: %(name)s.') % {'name': missing_parents[0]})
        owned_names = {category.pk: category.name for category in existing.values()}
        parent_by_name = {
            name: owned_names.get(category.parent_category_id, category.parent_category_id)
            for name, category in existing.items()
        }
        # Existing names are skipped, so validate their real parents,
        # not hypothetical replacements supplied in the imported rows.
        parent_by_name.update({name: parent or None for name, _type, parent in rows if name not in existing})
        for name, _type, parent_name in rows:
            if name not in existing:
                validate_parent_hierarchy(name, parent_name or None, parent_by_name)
        categories = dict(existing)
        for name, category_type, _parent_name in rows:
            if name not in categories:
                categories[name] = Category.objects.create(
                    user=user,
                    name=name,
                    transaction_type=category_type or None,
                )
                created += 1
        for name, _category_type, parent_name in rows:
            category = categories[name]
            if name in existing or not parent_name:
                continue
            category.parent_category = categories[parent_name]
            category.save(update_fields=['parent_category', 'updated_at'])
    return created
