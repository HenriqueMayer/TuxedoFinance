# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Public banking views; implementations live in responsibility-specific modules."""

from .base import (
    OwnedFormMixin,
    RelatedFormMixin,
    OwnedDeleteView,
    OperationFormMixin,
)
from .workspace import (
    account_planning,
    position_planning,
    BankListView,
    BankDetailView,
)
from .accounts import (
    BankCreateView,
    BankUpdateView,
    BankColorUpdateView,
    BankAccountCreateView,
    BankAccountUpdateView,
    BankDeleteView,
    BankAccountDeleteView,
)
from .cards import (
    DebitCardCreateView,
    DebitCardUpdateView,
    CreditCardCreateView,
    CreditCardUpdateView,
    DebitCardDeleteView,
    CreditCardDeleteView,
)
from .invoices import (
    InvoiceListView,
    InvoiceCardListView,
    invoice_detail,
    invoice_payment_edit,
    invoice_payment_delete,
)
from .loyalty import (
    LoyaltyProgramCreateView,
    LoyaltyProgramUpdateView,
    LoyaltyProgramDeleteView,
    LoyaltyEntryCreateView,
    LoyaltyEntryUpdateView,
    LoyaltyEntryDeleteView,
    RewardRedemptionCreateView,
    RewardRedemptionUpdateView,
)
from .transfers import BankTransferCreateView
from .exchange_rates import (
    ExchangeRateListView,
    ExchangeRateFormMixin,
    ExchangeRateCreateView,
    ExchangeRateUpdateView,
    ExchangeRateDeleteView,
)

__all__ = [
    'BankAccountCreateView',
    'BankAccountDeleteView',
    'BankAccountUpdateView',
    'BankColorUpdateView',
    'BankCreateView',
    'BankDeleteView',
    'BankDetailView',
    'BankListView',
    'BankTransferCreateView',
    'BankUpdateView',
    'CreditCardCreateView',
    'CreditCardDeleteView',
    'CreditCardUpdateView',
    'DebitCardCreateView',
    'DebitCardDeleteView',
    'DebitCardUpdateView',
    'ExchangeRateCreateView',
    'ExchangeRateDeleteView',
    'ExchangeRateFormMixin',
    'ExchangeRateListView',
    'ExchangeRateUpdateView',
    'InvoiceCardListView',
    'InvoiceListView',
    'LoyaltyEntryCreateView',
    'LoyaltyEntryDeleteView',
    'LoyaltyEntryUpdateView',
    'LoyaltyProgramCreateView',
    'LoyaltyProgramDeleteView',
    'LoyaltyProgramUpdateView',
    'OperationFormMixin',
    'OwnedDeleteView',
    'OwnedFormMixin',
    'RelatedFormMixin',
    'RewardRedemptionCreateView',
    'RewardRedemptionUpdateView',
    'account_planning',
    'invoice_detail',
    'invoice_payment_delete',
    'invoice_payment_edit',
    'position_planning',
]
