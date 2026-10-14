# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Shared workspace destinations, independent of financial records."""

from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from core.features import feature_available


AREAS = (
    ('home', _('Home'), 'dashboard:index', ('dashboard',)),
    ('transactions', _('Transactions'), 'transactions:list', ('transactions', 'categories', 'ingestion')),
    ('accounts', _('Accounts'), 'banking:list', ('banking',)),
    ('investments', _('Investments'), 'investments:list', ('investments',)),
    ('plan', _('Plan'), 'planning:index', ('planning', 'sandbox')),
)


def workspace_navigation(request):
    """Keep desktop, mobile and nested editors in the same five workspaces."""
    if not request.user.is_authenticated:
        return {}
    match = request.resolver_match
    namespace = match.namespace if match else ''
    url_name = match.url_name if match else ''
    active = next((key for key, _, _, namespaces in AREAS if namespace in namespaces), None)
    navigation = [
        {'key': key, 'label': label, 'url': reverse(route), 'active': key == active}
        for key, label, route, _ in AREAS
    ]
    sections = []
    section_label = ''
    if active == 'home':
        section_label = _('Home sections')
        sections = [
            (_('Dashboard'), 'dashboard:index', url_name == 'index'),
            (_('Reports'), 'dashboard:reports', url_name == 'reports'),
            (_('Net worth'), 'dashboard:wealth', url_name == 'wealth'),
        ]
    elif active == 'transactions':
        section_label = _('Transaction sections')
        sections = [
            (_('Transactions'), 'transactions:list', namespace == 'transactions'),
            (_('Categories'), 'categories:list', namespace == 'categories'),
            (_('Import statements'), 'ingestion:index', namespace == 'ingestion'),
        ]
    elif active == 'accounts':
        section_label = _('Account sections')
        invoice = url_name.startswith(('invoice_', 'invoices'))
        exchange = url_name.startswith('exchange_rate')
        sections = [
            (_('Accounts'), 'banking:list', not invoice and not exchange),
            (_('Invoices'), 'banking:invoices', invoice),
            (_('Exchange rates'), 'banking:exchange_rates', exchange),
        ]
    return {
        'APP_NAVIGATION': navigation,
        'APP_AREA_LABEL': next((item['label'] for item in navigation if item['active']), _('Settings') if namespace == 'accounts' else 'Tuxedo Finance'),
        'APP_SECTION_LABEL': section_label,
        'APP_SECTIONS': [
            {'label': label, 'url': reverse(route), 'active': selected}
            for label, route, selected in sections
            if route not in ('dashboard:wealth', 'ingestion:index') or feature_available('wealth' if route == 'dashboard:wealth' else 'imports')
        ],
    }
