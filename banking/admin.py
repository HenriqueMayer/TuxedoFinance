from django.contrib import admin

from banking.models import (
    Bank,
    BankAccount,
    BankMovement,
    BankTransfer,
    CardInvoice,
    CardInvoiceCredit,
    CreditCard,
    DebitCard,
    ExchangeRate,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)


@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'updated_at')
    search_fields = ('name', 'user__username')


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'bank', 'currency', 'user')
    list_filter = ('currency',)


@admin.register(BankMovement)
class BankMovementAdmin(admin.ModelAdmin):
    list_display = ('effective_date', 'account', 'direction', 'kind', 'amount', 'user')
    list_filter = ('direction', 'kind', 'effective_date')


@admin.register(CardInvoice)
class CardInvoiceAdmin(admin.ModelAdmin):
    list_display = ('card', 'reference_month', 'due_date', 'amount', 'status')
    list_filter = ('status',)


@admin.register(CardInvoiceCredit)
class CardInvoiceCreditAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'reference_month', 'card', 'amount', 'user')
    list_filter = ('reference_month',)
    readonly_fields = ('idempotency_key',)

    def save_model(self, request, obj, form, change):
        from banking.credits import save_invoice_credit

        save_invoice_credit(obj, user=obj.user)

    def delete_model(self, request, obj):
        from banking.credits import delete_invoice_credit

        delete_invoice_credit(obj, user=obj.user)

    def delete_queryset(self, request, queryset):
        from banking.credits import delete_invoice_credit

        for credit in queryset:
            delete_invoice_credit(credit, user=credit.user)


@admin.register(LoyaltyEntry)
class LoyaltyEntryAdmin(admin.ModelAdmin):
    list_display = ('date', 'program', 'direction', 'kind', 'amount', 'user')
    list_filter = ('direction', 'kind')


admin.site.register(DebitCard)
admin.site.register(CreditCard)
admin.site.register(BankTransfer)
admin.site.register(LoyaltyProgram)
admin.site.register(RewardRedemption)
admin.site.register(ExchangeRate)
