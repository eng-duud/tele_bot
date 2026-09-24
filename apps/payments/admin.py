from django.contrib import admin
from apps.payments.models import PaymentMethod, PaymentRequest

@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'account_number', 'is_active', 'display_order')
    list_editable = ('is_active', 'display_order')

@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'payment_method', 'amount_yer', 'tx_number', 'status', 'reviewed_by', 'created_at')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('user__telegram_id', 'user__username', 'tx_number')
