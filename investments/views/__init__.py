# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Stable public imports for investment views."""

from .portfolio import (
    position_detail,
    position_update,
    InvestmentListView,
    InvestmentChartsView,
)
from .operations import (
    InvestmentOperationsView,
    InvestmentFormMixin,
    InvestmentCreateView,
    InvestmentUpdateView,
    yield_preview,
    InvestmentDeleteView,
)
from .setup import (
    guided_investment,
    InvestmentSettingsView,
    SetupFormMixin,
    ProductFormMixin,
    InvestmentProductCreateView,
    InvestmentProductUpdateView,
    AssetFormMixin,
    AssetCreateView,
    AssetUpdateView,
    SetupDeleteView,
    InvestmentProductDeleteView,
    AssetDeleteView,
    archive_asset,
    restore_asset,
)
from .prices import (
    PriceObservationListView,
    PriceObservationFormMixin,
    PriceObservationCreateView,
    PriceObservationUpdateView,
    PriceObservationDeleteView,
)

__all__ = [
    'position_detail',
    'position_update',
    'guided_investment',
    'InvestmentListView',
    'InvestmentChartsView',
    'InvestmentOperationsView',
    'InvestmentFormMixin',
    'InvestmentCreateView',
    'InvestmentUpdateView',
    'yield_preview',
    'InvestmentSettingsView',
    'SetupFormMixin',
    'ProductFormMixin',
    'InvestmentProductCreateView',
    'InvestmentProductUpdateView',
    'AssetFormMixin',
    'AssetCreateView',
    'AssetUpdateView',
    'SetupDeleteView',
    'InvestmentProductDeleteView',
    'AssetDeleteView',
    'archive_asset',
    'restore_asset',
    'InvestmentDeleteView',
    'PriceObservationListView',
    'PriceObservationFormMixin',
    'PriceObservationCreateView',
    'PriceObservationUpdateView',
    'PriceObservationDeleteView',
]
