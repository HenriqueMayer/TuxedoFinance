from django.contrib import admin

from categories.models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent_category', 'user', 'created_at')
    list_filter = ('user',)
    search_fields = ('name',)
