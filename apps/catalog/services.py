from decimal import Decimal
from typing import List, Optional
from apps.catalog.models import Category, Product
from apps.core.services import CurrencyService

class CatalogService:
    """Business logic for catalog browsing, multi-currency price calculations, and stock checks."""

    @staticmethod
    def get_root_categories() -> List[Category]:
        """Fetch all top-level active categories."""
        return list(Category.objects.filter(parent__isnull=True, is_active=True))

    @staticmethod
    def get_subcategories(parent_id: str) -> List[Category]:
        """Fetch active subcategories under a specific parent category."""
        return list(Category.objects.filter(parent_id=parent_id, is_active=True))

    @staticmethod
    def get_products_by_category(category_id: str) -> List[Product]:
        """Fetch active products belonging to the specified category."""
        return list(Product.objects.filter(categories__id=category_id, is_active=True).distinct())

    @classmethod
    def get_price_in_yer(cls, product: Product) -> Decimal:
        """Calculate canonical product price in YER base currency."""
        if product.base_currency == 'YER':
            return Decimal(str(product.price))
        return CurrencyService.convert(product.price, from_curr='USD', to_curr='YER')

    @classmethod
    def get_price_display(cls, product: Product, preferred_currency: str = 'YER') -> str:
        """Format product price string according to user's currency preference."""
        price_yer = cls.get_price_in_yer(product)
        return CurrencyService.format_dual_price(price_yer, preferred_currency=preferred_currency)

    @staticmethod
    def is_in_stock(product: Product) -> bool:
        """Determine whether the product is currently purchasable."""
        if not product.is_active:
            return False

        if product.stock_type == 'UNLIMITED':
            return True

        if product.stock_type == 'QUANTITY':
            return product.stock_quantity > 0

        if product.stock_type == 'INDIVIDUAL_ITEMS':
            from apps.inventory.models import StockItem
            return StockItem.objects.filter(product=product, status='AVAILABLE').exists()

        if product.stock_type == 'API_CAPACITY':
            return True

        return False
