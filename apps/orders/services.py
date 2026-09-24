from decimal import Decimal
from typing import Tuple, List, Optional
from django.db import transaction
from apps.users.models import TelegramProfile
from apps.catalog.models import Product
from apps.catalog.services import CatalogService
from apps.inventory.services import InventoryService
from apps.wallet.services import WalletService, InsufficientBalanceError
from apps.orders.models import Order, OrderItem, OrderStatusHistory

class OrderService:
    """Central order processing, state machine enforcement, and atomic purchasing."""

    @classmethod
    def process_purchase(
        cls,
        user: TelegramProfile,
        product: Product,
        quantity: int = 1,
        customer_input_data: str = ""
    ) -> Tuple[Order, List[str]]:
        """
        Execute atomic checkout:
        1. Lock wallet row (select_for_update)
        2. Recalculate price independently on the server (never trust client)
        3. Lock and allocate inventory
        4. Debit wallet
        5. Create immutable Order & OrderItem snapshots
        6. Commit and return (Order, delivered_secrets)
        """
        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون 1 على الأقل.")

        unit_price_yer = CatalogService.get_price_in_yer(product)
        total_price_yer = unit_price_yer * Decimal(str(quantity))

        with transaction.atomic():
            # 1. Lock customer wallet
            wallet = WalletService.get_or_create_wallet(user)
            
            # Check availability before debiting
            if not CatalogService.is_in_stock(product):
                raise ValueError("عذراً، هذا المنتج غير متوفر في المخزون حالياً.")

            # 2. Debit wallet atomically
            tx, _ = WalletService.debit(
                wallet=wallet,
                amount=total_price_yer,
                reference_id="PENDING-ORDER",
                description=f"شراء: {quantity}x {product.name}",
                idempotency_key=None
            )

            # 3. Create the Order
            order = Order.objects.create(
                user=user,
                total_amount_yer=total_price_yer,
                currency_used='YER',
                status='PENDING',
                customer_input_data=customer_input_data.strip()
            )

            # Update tx reference with actual order number
            tx.reference_id = order.order_number
            tx.save(update_fields=['reference_id'])

            # 4. Create snapshot OrderItem
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name_snapshot=product.name,
                unit_price_snapshot_yer=unit_price_yer,
                quantity=quantity,
                total_price_yer=total_price_yer
            )

            # 5. Handle fulfillment allocation
            delivered_secrets: List[str] = []

            if product.fulfillment_type == 'INVENTORY':
                # Instant delivery from internal inventory
                delivered_secrets = InventoryService.allocate_inventory(
                    product=product, 
                    quantity=quantity, 
                    order_id=order.order_number
                )
                order.status = 'COMPLETED'
                order.delivered_data = "\n".join(delivered_secrets)
                order.save(update_fields=['status', 'delivered_data', 'updated_at'])

                OrderStatusHistory.objects.create(
                    order=order,
                    from_status='PENDING',
                    to_status='COMPLETED',
                    notes="تم التسليم الفوري من المخزون بنجاح."
                )

            elif product.fulfillment_type == 'API':
                # Marked for background worker execution
                order.status = 'PROCESSING'
                order.save(update_fields=['status', 'updated_at'])

                OrderStatusHistory.objects.create(
                    order=order,
                    from_status='PENDING',
                    to_status='PROCESSING',
                    notes="تم تحويل الطلب لمعالجة المزود الخارجي."
                )
                # Publish only after checkout commits. A fast worker must not
                # process an order that later rolls back.
                from apps.fulfillment.services import FulfillmentService
                transaction.on_commit(
                    lambda order=order: FulfillmentService.queue_fulfillment(order)
                )

            elif product.fulfillment_type == 'MANUAL':
                order.status = 'PROCESSING'
                order.save(update_fields=['status', 'updated_at'])

                OrderStatusHistory.objects.create(
                    order=order,
                    from_status='PENDING',
                    to_status='PROCESSING',
                    notes="الطلب بانتظار التنفيذ اليدوي من الإدارة."
                )
            else:
                # FILE is declared in the choices but has no implementation.
                # Never debit a customer for an order that cannot progress.
                raise ValueError(
                    f"نوع التسليم '{product.fulfillment_type}' غير مدعوم حالياً."
                )

            return order, delivered_secrets

    @classmethod
    def refund_order(cls, order: Order, reason: str = "") -> bool:
        """
        Atomically refund customer wallet and mark order as REFUNDED.
        Enforces strict idempotency.
        """
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(id=order.id)
            if locked_order.status == 'REFUNDED':
                return True

            wallet = WalletService.get_or_create_wallet(locked_order.user)
            idempotency_key = f"refund-order-{locked_order.order_number}"

            WalletService.refund(
                wallet=wallet,
                amount=locked_order.total_amount_yer,
                reference_id=locked_order.order_number,
                description=f"استرجاع قيمة الطلب {locked_order.order_number}: {reason or 'فشل التسليم'}",
                idempotency_key=idempotency_key
            )

            old_status = locked_order.status
            locked_order.status = 'REFUNDED'
            locked_order.failure_reason = reason
            locked_order.save(update_fields=['status', 'failure_reason', 'updated_at'])

            OrderStatusHistory.objects.create(
                order=locked_order,
                from_status=old_status,
                to_status='REFUNDED',
                notes=f"تم استرجاع المبلغ لمحفظة العميل: {reason}"
            )

            return True
