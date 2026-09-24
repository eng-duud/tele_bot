from django.contrib import admin
from apps.orders.models import Order, OrderItem, OrderStatusHistory

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product_name_snapshot', 'unit_price_snapshot_yer', 'quantity', 'total_price_yer')

class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ('from_status', 'to_status', 'notes', 'created_at')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'user', 'total_amount_yer', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order_number', 'user__telegram_id', 'user__username')
    inlines = [OrderItemInline, OrderStatusHistoryInline]
