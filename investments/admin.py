from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction

from investments.models import Asset, Investment, InvestmentProduct, PriceObservation


@admin.register(InvestmentProduct)
class InvestmentProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'bank', 'purpose', 'yield_mode', 'user', 'created_at')
    list_filter = ('user', 'purpose', 'yield_mode', 'bank')
    search_fields = ('name', 'bank__name')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'asset_class', 'currency', 'is_archived', 'user')
    list_filter = ('user', 'asset_class', 'currency', 'is_archived')
    search_fields = ('name', 'code')

    def get_deleted_objects(self, objs, request):
        deleted, counts, permissions, protected = super().get_deleted_objects(objs, request)
        protected.extend(str(obj) for obj in objs if obj.has_opening_position)
        return deleted, counts, permissions, protected


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ('date', 'kind', 'product', 'asset', 'quantity', 'unit_price', 'cash_amount', 'user')
    list_filter = ('user', 'kind', 'product', 'asset')
    search_fields = ('reason', 'notes', 'product__name', 'asset__name', 'asset__code')
    date_hierarchy = 'date'

    def get_deleted_objects(self, objs, request):
        from investments.positions import validate_position_history
        objects = list(objs)
        deleted, counts, permissions, protected = super().get_deleted_objects(objects, request)
        selected = [obj.pk for obj in objects]
        for obj in objects:
            try:
                validate_position_history(obj.user, [(obj.product_id, obj.asset_id)], exclude_pks=selected)
            except ValidationError as error:
                protected.extend(error.messages)
        return deleted, counts, permissions, protected

    def delete_model(self, request, obj):
        from investments.positions import validate_position_history
        from investments.services import cleanup_investment_ledger
        with transaction.atomic():
            validate_position_history(obj.user, [(obj.product_id, obj.asset_id)], exclude_pk=obj.pk)
            cleanup_investment_ledger(obj)
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        from investments.positions import validate_position_history
        from investments.services import cleanup_investment_ledger
        objects = list(queryset)
        selected = [obj.pk for obj in objects]
        with transaction.atomic():
            for obj in objects:
                validate_position_history(obj.user, [(obj.product_id, obj.asset_id)], exclude_pks=selected)
            for obj in objects:
                cleanup_investment_ledger(obj)
            queryset.delete()


@admin.register(PriceObservation)
class PriceObservationAdmin(admin.ModelAdmin):
    list_display = ('asset', 'date', 'unit_price', 'source', 'user')
    list_filter = ('user', 'asset')
    search_fields = ('source', 'asset__code')
