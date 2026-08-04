from django.contrib import admin

from investments.models import Investment


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = (
        'date',
        'title',
        'kind',
        'amount',
        'user',
        'created_at',
    )
    list_filter = ('user', 'kind')
    search_fields = ('title', 'reason', 'notes')
    date_hierarchy = 'date'
    autocomplete_fields = ()
