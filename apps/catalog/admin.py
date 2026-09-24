from django.contrib import admin
from apps.catalog.models import Category, Product, ProductImage

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'parent', 'is_active', 'display_order')
    list_filter = ('is_active', 'parent')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'base_currency', 'stock_type', 'fulfillment_type', 'is_active')
    list_filter = ('stock_type', 'fulfillment_type', 'is_active', 'categories')
    search_fields = ('name', 'description')

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'image_url', 'is_primary')
