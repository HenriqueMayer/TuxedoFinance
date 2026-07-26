from django.contrib import admin

from transactions.models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'transaction_type',
        'amount',
        'transaction_date',
        'is_fixed',
        'fixed_until',
        'installments',
        'category',
        'payment_method',
        'user',
    )
    list_filter = (
        'user',
        'transaction_type',
        'is_fixed',
        'installments',
        'category',
        'payment_method',
    )
    search_fields = ('title', 'notes')
    date_hierarchy = 'transaction_date'
