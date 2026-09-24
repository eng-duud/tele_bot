from django.contrib import admin
from apps.core.models import ExchangeRate, SystemSetting

@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('source_currency', 'target_currency', 'rate', 'is_active', 'updated_at')
    list_editable = ('rate', 'is_active')

@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'description')
