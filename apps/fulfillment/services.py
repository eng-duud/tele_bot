import logging
from apps.orders.models import Order
from apps.fulfillment.tasks import execute_order_fulfillment

logger = logging.getLogger(__name__)

class FulfillmentService:
    """Service to enqueue and dispatch fulfillment tasks safely."""

    @staticmethod
    def queue_fulfillment(order: Order):
        """Enqueue fulfillment task in Celery; never call a provider inline."""
        try:
            execute_order_fulfillment.delay(str(order.id))
        except Exception as exc:
            logger.error(
                "Could not queue fulfillment for order %s: %s. "
                "The order remains PROCESSING for reconciliation.", order.order_number, exc
            )
            return False
        return True
