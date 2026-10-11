from django.contrib import admin
from apps.support.models import SupportTicket, TicketMessage

class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ('sender', 'is_from_admin', 'text', 'photo_file_id', 'created_at')

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'user', 'subject', 'status', 'last_answered_by', 'last_answered_at', 'created_at')
    search_fields = ('ticket_number', 'user__telegram_id', 'user__username', 'subject')
    list_filter = ('status', 'created_at')
    inlines = [TicketMessageInline]

@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'sender', 'is_from_admin', 'created_at')
    search_fields = ('ticket__ticket_number', 'text')
    list_filter = ('is_from_admin', 'created_at')
