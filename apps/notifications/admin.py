from django.contrib import admin
from apps.notifications.models import RequiredChannel, BroadcastAnnouncement

@admin.register(RequiredChannel)
class RequiredChannelAdmin(admin.ModelAdmin):
    list_display = ('channel_title', 'channel_id', 'is_mandatory', 'is_active', 'display_order')
    list_editable = ('is_mandatory', 'is_active', 'display_order')

@admin.register(BroadcastAnnouncement)
class BroadcastAnnouncementAdmin(admin.ModelAdmin):
    list_display = ('id', 'sent_count', 'target_count', 'is_completed', 'created_at')
