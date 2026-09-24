from django.contrib import admin
from apps.audit.models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'admin', 'resource_type', 'resource_id', 'created_at')
    list_filter = ('action', 'resource_type', 'created_at')
    search_fields = ('resource_id', 'action', 'admin__telegram_id', 'admin__username')
    readonly_fields = ('admin', 'action', 'resource_type', 'resource_id', 'before_state', 'after_state', 'notes', 'created_at')
