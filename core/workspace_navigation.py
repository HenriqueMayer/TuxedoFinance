# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Shared workspace destinations, independent of financial records."""

from django.urls import reverse
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from core.features import feature_available


AREAS = (
    ('home', _('Home'), 'dashboard:index', ('dashboard',)),
    ('transactions', _('Transactions'), 'transactions:list', ('transactions', 'categories', 'ingestion')),
    ('accounts', _('Accounts'), 'banking:list', ('banking',)),
    ('investments', _('Investments'), 'investments:list', ('investments',)),
    ('plan', _('Plan'), 'planning:index', ('planning', 'sandbox')),
    ('analytics', _('Analytics'), 'analytics:index', ('analytics',)),
)

# Compact visible labels keep all six direct destinations readable on phones;
# accessible names and desktop labels retain the full workspace identity.
MOBILE_LABELS = {'transactions': pgettext_lazy('compact workspace navigation', 'Entries'),
                 'investments': _('Invest')}


def workspace_navigation(request):
    """Keep desktop, mobile and nested editors in the same six workspaces."""
    if not request.user.is_authenticated:
        return {}
    match = request.resolver_match
    namespace = match.namespace if match else ''
    url_name = match.url_name if match else ''
    active = next((key for key, _, _, namespaces in AREAS if namespace in namespaces), None)
    navigation = [
        {'key': key, 'label': label, 'mobile_label': MOBILE_LABELS.get(key, label),
         'url': reverse(route), 'active': key == active}
        for key, label, route, _ in AREAS
    ]
    sections = []
    section_label = ''
    if active == 'home':
        section_label = _('Home sections')
        sections = [
            (_('Dashboard'), 'dashboard:index', url_name == 'index'),
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
        invoice = url_name.startswith(('invoice_', 'invoices')) or url_name == 'card_invoices'
        exchange = url_name.startswith('exchange_rate')
        loyalty = url_name.startswith(('program', 'entry', 'redemption'))
        sections = [
            (_('Accounts'), 'banking:list', not invoice and not exchange and not loyalty),
            (_('Invoices'), 'banking:invoices', invoice),
            (_('Loyalty'), 'banking:programs', loyalty),
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
