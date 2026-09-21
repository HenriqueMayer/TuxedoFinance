# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit spreadsheet-oriented CSV; ordinary exports remain lossless."""


def spreadsheet_cell(value):
    """Neutralize formula-like text without converting numeric cells to text.

    This is deliberately not an interchange encoding: spreadsheet applications
    differ, and importers must not strip the added apostrophe automatically.
    """
    if isinstance(value, str) and (
        value.startswith(('\t', '\r', '\n'))
        or value.lstrip().startswith(('=', '+', '-', '@'))
    ):
        return "'" + value
    return value


def export_row(values, spreadsheet=False):
    return [spreadsheet_cell(value) for value in values] if spreadsheet else values
