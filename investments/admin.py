from django.contrib import admin

from investments.models import ExchangeRate, Investment


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = (
        'date',
        'title',
        'kind',
        'amount',
        'currency',
        'user',
        'created_at',
    )
    list_filter = ('user', 'kind', 'currency')
    search_fields = ('title', 'reason', 'notes')
    date_hierarchy = 'date'


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = (
        'from_currency',
        'to_currency',
        'rate',
        'effective_date',
        'user',
        'created_at',
    )
    list_filter = ('user', 'from_currency', 'to_currency')
    search_fields = ('notes',)
    date_hierarchy = 'effective_date'
