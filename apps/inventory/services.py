from typing import List, Tuple
from django.db import transaction
from django.utils import timezone
from apps.catalog.models import Product
from apps.inventory.models import StockItem, RestockSubscription
from apps.users.models import TelegramProfile

class OutOfStockError(Exception):
    """Raised when inventory is depleted during checkout."""
    pass


class InventoryService:
    """Service managing inventory allocation, concurrency locking, and restock notifications."""

    @classmethod
    def bulk_add_individual_items(cls, product: Product, raw_items: List[str]) -> int:
        """Encrypt and insert multiple items into inventory."""
        created_count = 0
        with transaction.atomic():
            for idx, text in enumerate(raw_items, start=1):
                clean_text = text.strip()
                if not clean_text:
                    continue
                item = StockItem(
                    product=product,
                    item_identifier=f"Item-{idx}",
                    status='AVAILABLE'
                )
                item.set_secret(clean_text)
                item.save()
                created_count += 1
        return created_count

    @classmethod
    def allocate_inventory(cls, product: Product, quantity: int = 1, order_id: str = "") -> List[str]:
        """
        Atomic allocation with row-locking to strictly prevent double-selling.
        Returns list of delivered secrets (or empty list if quantity/api based).
        """
        delivered_secrets: List[str] = []

        with transaction.atomic():
            if product.stock_type == 'UNLIMITED' or product.stock_type == 'API_CAPACITY':
                return delivered_secrets

            if product.stock_type == 'QUANTITY':
                # Lock product row
                locked_product = Product.objects.select_for_update().get(id=product.id)
                if locked_product.stock_quantity < quantity:
                    raise OutOfStockError(f"الكمية المطلوبة غير متوفرة حالياً في المخزون للمنتج {product.name}.")
                
                locked_product.stock_quantity -= quantity
                locked_product.save(update_fields=['stock_quantity', 'updated_at'])
                return delivered_secrets

            if product.stock_type == 'INDIVIDUAL_ITEMS':
                # Lock specific stock rows
                available_items = list(
                    StockItem.objects.select_for_update()
                    .filter(product=product, status='AVAILABLE')[:quantity]
                )

                if len(available_items) < quantity:
                    raise OutOfStockError(f"عفواً، الكمية المطلوبة من {product.name} غير متوفرة في المخزون.")

                now = timezone.now()
                for item in available_items:
                    secret_payload = item.get_secret()
                    delivered_secrets.append(secret_payload)
                    item.status = 'SOLD'
                    item.order_id = order_id
                    item.sold_at = now
                    item.save(update_fields=['status', 'order_id', 'sold_at', 'updated_at'])

                return delivered_secrets

        return delivered_secrets

    @staticmethod
    def subscribe_to_restock(product: Product, user: TelegramProfile) -> Tuple[RestockSubscription, bool]:
        """Register a user to be alerted when out-of-stock product is replenished."""
        sub, created = RestockSubscription.objects.get_or_create(
            product=product,
            user=user,
            defaults={'is_notified': False}
        )
        if not created and sub.is_notified:
            sub.is_notified = False
            sub.save(update_fields=['is_notified', 'updated_at'])
            return sub, True
        return sub, created

    @staticmethod
    def get_pending_restock_subscribers(product: Product) -> List[TelegramProfile]:
        """Retrieve users waiting for product restock notification."""
        subs = RestockSubscription.objects.filter(product=product, is_notified=False).select_related('user')
        users = [s.user for s in subs]
        subs.update(is_notified=True)
        return users
