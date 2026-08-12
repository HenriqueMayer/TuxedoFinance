from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from transactions.models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'transaction_type',
        'amount',
        'date',
        'is_fixed',
        'fixed_until',
        'installments',
        'category',
        'payment_channel',
        'payment_label',
        'user',
    )
    list_filter = (
        'user',
        'transaction_type',
        'is_fixed',
        'installments',
        'category',
        'payment_channel',
    )
    search_fields = (
        'title', 'notes', 'bank_account__name', 'debit_card__name',
        'credit_card__name',
    )
    date_hierarchy = 'date'

    @admin.display(description=_('Payment label'))
    def payment_label(self, transaction):
        return transaction.payment_label
