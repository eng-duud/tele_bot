from django.contrib import admin
from apps.inventory.models import StockItem, RestockSubscription

@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'item_identifier', 'status', 'order_id', 'sold_at', 'created_at')
    list_filter = ('status', 'product')
    search_fields = ('product__name', 'item_identifier', 'order_id')
    readonly_fields = ('encrypted_data',)

@admin.register(RestockSubscription)
class RestockSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'is_notified', 'created_at')
    list_filter = ('is_notified', 'product')
