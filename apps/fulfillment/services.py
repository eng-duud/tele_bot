import logging
from apps.orders.models import Order
from apps.fulfillment.tasks import execute_order_fulfillment

logger = logging.getLogger(__name__)

class FulfillmentService:
    """Service to enqueue and dispatch fulfillment tasks safely."""

    @staticmethod
    def queue_fulfillment(order: Order):
        """Enqueue fulfillment task in Celery worker (or run directly as fallback)."""
        try:
            execute_order_fulfillment.delay(str(order.id))
        except Exception as exc:
            logger.warning(f"Could not queue to Celery broker ({exc}). Executing synchronously.")
            try:
                execute_order_fulfillment(str(order.id))
            except Exception as sync_err:
                logger.error(f"Synchronous fulfillment fallback also failed: {sync_err}")
