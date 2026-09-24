from django.contrib import admin
from apps.services_app.models import DigitalService, ServiceRequest

@admin.register(DigitalService)
class DigitalServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_type', 'price_yer', 'is_active')
    list_filter = ('service_type', 'is_active')

@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'service', 'status', 'quote_amount_yer', 'quote_expires_at', 'created_at')
    list_filter = ('status', 'created_at')
