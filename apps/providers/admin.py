from django.contrib import admin
from apps.providers.models import ApiProvider, ProviderProductMapping

@admin.register(ApiProvider)
class ApiProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider_code', 'provider_type', 'is_active')
    list_filter = ('provider_type', 'is_active')

@admin.register(ProviderProductMapping)
class ProviderProductMappingAdmin(admin.ModelAdmin):
    list_display = ('product', 'provider', 'external_service_id')
