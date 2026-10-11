from django.contrib import admin
from apps.users.models import TelegramProfile, AdminPermission, AdminRole, AdminProfile

@admin.register(TelegramProfile)
class TelegramProfileAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'username', 'first_name', 'preferred_currency', 'referred_by', 'referral_bonus_paid', 'is_admin', 'is_banned', 'created_at')
    search_fields = ('telegram_id', 'username', 'first_name')
    list_filter = ('is_admin', 'is_banned', 'referral_bonus_paid', 'preferred_currency')
    raw_id_fields = ('referred_by',)


@admin.register(AdminPermission)
class AdminPermissionAdmin(admin.ModelAdmin):
    list_display = ('codename', 'description')

@admin.register(AdminRole)
class AdminRoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    filter_horizontal = ('permissions',)

@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ('profile', 'role', 'is_super_admin', 'is_active')
    list_filter = ('is_super_admin', 'is_active')
