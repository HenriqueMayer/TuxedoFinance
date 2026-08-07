from django.contrib import admin

from investments.models import Asset, ExchangeRate, Institution, Investment, InvestmentProduct


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at')
    list_filter = ('user',)
    search_fields = ('name',)


@admin.register(InvestmentProduct)
class InvestmentProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'institution', 'yield_mode', 'user', 'created_at')
    list_filter = ('user', 'yield_mode')
    search_fields = ('name', 'institution__name')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'currency', 'user', 'created_at')
    list_filter = ('user', 'currency')
    search_fields = ('name', 'code')


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
    list_filter = ('user', 'kind', 'product', 'asset')
    search_fields = ('title', 'reason', 'notes', 'product__name', 'asset__name')
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
