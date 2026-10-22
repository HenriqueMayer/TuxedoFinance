# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Shape-only dry-run proposals. There is deliberately no execution function.

These immutable descriptions do not validate ownership or current financial
state. A later reviewed execution boundary must resolve every identifier from
its authenticated user and call the existing canonical financial services.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from core.currencies import CURRENCIES
from core.navigation import safe_local_url


_SCHEMAS = {
    'transaction.create': {'title', 'amount', 'currency', 'date', 'transaction_type', 'account_id', 'category_id'},
    'transaction.categorize': {'transaction_id', 'category_id'},
    'goal.create': {'name', 'target_amount', 'currency', 'target_date'},
    'budget.create': {'category_id', 'month', 'currency', 'amount'},
    'alert.propose': {'kind', 'summary', 'source_url'},
}


@dataclass(frozen=True)
class ActionPreview:
    name: str
    parameters: MappingProxyType
    requires_review: bool = True
    executable: bool = False
    warnings: tuple[str, ...] = ('Ownership, compatibility and current financial state have not been validated.',)


def preview_action(name, parameters):
    """Validate only an allowlisted, bounded proposal; do not resolve or write."""
    if not isinstance(name, str) or name not in _SCHEMAS or not isinstance(parameters, dict):
        raise ValueError('Unsupported assistant action proposal.')
    if set(parameters) != _SCHEMAS[name]:
        raise ValueError('Unsupported assistant action parameters.')
    normalized = dict(parameters)
    for key, value in normalized.items():
        if key.endswith('_id') and (type(value) is not int or not 1 <= value <= 9223372036854775807):
            raise ValueError('Invalid proposal identifier.')
        if key in {'title', 'name', 'summary'}:
            limit = {'title': 150, 'name': 120, 'summary': 500}[key]
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
                raise ValueError('Invalid proposal text.')
        if key == 'currency' and (not isinstance(value, str) or value not in CURRENCIES):
            raise ValueError('Invalid proposal currency.')
        if key in {'amount', 'target_amount'}:
            try:
                amount = Decimal(value) if isinstance(value, str) else None
                if amount is None or not amount.is_finite() or not Decimal('0.01') <= amount < Decimal('100000000000000') or amount.as_tuple().exponent < -2:
                    raise ValueError
            except (InvalidOperation, ValueError):
                raise ValueError('Invalid proposal amount.') from None
            normalized[key] = format(amount, '.2f')
        if key in {'date', 'target_date', 'month'} and not (key == 'target_date' and value is None):
            try:
                parsed = date.fromisoformat(value + '-01' if key == 'month' else value)
                if not 1901 <= parsed.year <= 9988 or (parsed.strftime('%Y-%m') if key == 'month' else parsed.isoformat()) != value:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError('Invalid proposal date.') from None
    if name == 'transaction.create' and (not isinstance(normalized['transaction_type'], str)
                                        or normalized['transaction_type'] not in {'INCOME', 'EXPENSE'}):
        raise ValueError('Invalid proposal transaction type.')
    if name == 'alert.propose':
        if (not isinstance(normalized['kind'], str) or normalized['kind'] not in
                {'possible_duplicate', 'subscription_increase', 'budget_limit', 'cash_shortage'}):
            raise ValueError('Invalid proposal alert kind.')
        if not isinstance(normalized['source_url'], str) or len(normalized['source_url']) > 2048 or not safe_local_url(normalized['source_url']):
            raise ValueError('Invalid proposal source URL.')
    return ActionPreview(name, MappingProxyType(normalized))
