from django.contrib import admin

from payments.models import PaymentMethod


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'method_type', 'user', 'created_at')
    list_filter = ('user', 'method_type')
    search_fields = ('name',)
