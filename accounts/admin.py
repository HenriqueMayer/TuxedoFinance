from django.contrib import admin

from accounts.models import UserPreference


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'base_currency', 'date_format')
    list_filter = ('base_currency', 'date_format')
