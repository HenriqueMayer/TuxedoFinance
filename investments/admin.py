from django.contrib import admin

from investments.models import Asset, Investment, InvestmentProduct


@admin.register(InvestmentProduct)
class InvestmentProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'bank', 'yield_mode', 'user', 'created_at')
    list_filter = ('user', 'yield_mode', 'bank')
    search_fields = ('name', 'bank__name')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'asset_class', 'currency', 'user')
    list_filter = ('user', 'asset_class', 'currency')
    search_fields = ('name', 'code')


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ('date', 'kind', 'product', 'asset', 'quantity', 'unit_price', 'cash_amount', 'user')
    list_filter = ('user', 'kind', 'product', 'asset')
    search_fields = ('reason', 'notes', 'product__name', 'asset__name', 'asset__code')
    date_hierarchy = 'date'
