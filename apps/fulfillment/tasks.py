import logging
from celery import shared_task
from django.db import transaction
from apps.orders.models import Order
from apps.orders.services import OrderService
from apps.fulfillment.models import FulfillmentTask, OrderIssue
from apps.providers.services import ProviderDispatcherService

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3

@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def execute_order_fulfillment(self, order_id: str):
    """
    Asynchronous fulfillment worker.
    Crucial Rule: External API communications happen strictly here, 
    completely OUTSIDE of the core checkout database transaction.
    """
    order = Order.objects.filter(id=order_id).first()
    if not order:
        logger.error(f"Fulfillment task: Order {order_id} not found.")
        return

    # Fetch primary item
    order_item = order.items.first()
    if not order_item or not order_item.product:
        logger.error(f"Order {order.order_number} has no valid product to fulfill.")
        return

    product = order_item.product

    # Claim the single task row atomically. A duplicate Celery delivery must
    # not call the external provider while another worker owns the order.
    with transaction.atomic():
        task, _ = FulfillmentTask.objects.get_or_create(
            order=order,
            defaults={
                'status': 'QUEUED',
                'attempts': 0,
                'provider_idempotency_key': f"fulfill-{order.order_number}"
            }
        )
        task = FulfillmentTask.objects.select_for_update().get(pk=task.pk)
        if task.status in ('SUCCESS', 'FAILED', 'RUNNING'):
            return f"Order {order.order_number} fulfillment is already {task.status.lower()}."
        task.attempts += 1
        task.status = 'RUNNING'
        task.save(update_fields=['attempts', 'status', 'updated_at'])

    try:
        # Call external provider through abstraction layer
        result = ProviderDispatcherService.execute_provider_order(
            product=product,
            quantity=order_item.quantity,
            customer_input=order.customer_input_data,
            idempotency_key=task.provider_idempotency_key
        )

        if result.success:
            # Order succeeded
            order.status = 'COMPLETED'
            order.delivered_data = result.delivered_payload
            order.save(update_fields=['status', 'delivered_data', 'updated_at'])

            task.status = 'SUCCESS'
            task.save(update_fields=['status', 'updated_at'])

            # Send Telegram alerts (safe import)
            try:
                from apps.notifications.services import SuccessChannelService, CustomerNotifierService
                CustomerNotifierService.send_order_delivered(order)
                SuccessChannelService.broadcast_order(order)
            except Exception as notify_err:
                logger.warning(f"Notification error on order {order.order_number}: {notify_err}")

            return f"Order {order.order_number} fulfilled successfully."

        else:
            raise Exception(result.error_message or "فشل غير معروف من المزود الخارجي.")

    except Exception as exc:
        task.last_error = str(exc)
        logger.warning(f"Fulfillment attempt {task.attempts} failed for {order.order_number}: {exc}")

        if task.attempts < MAX_ATTEMPTS:
            # Exponential backoff retry: 15s, 45s, 135s...
            retry_delay = 15 * (3 ** (task.attempts - 1))
            task.status = 'QUEUED'
            task.save(update_fields=['last_error', 'status', 'updated_at'])
            raise self.retry(exc=exc, countdown=retry_delay)
        else:
            # Max attempts exhausted: Perform automated idempotent refund
            task.status = 'FAILED'
            task.save(update_fields=['status', 'last_error', 'updated_at'])

            # Refund wallet
            OrderService.refund_order(order, reason=f"فشل التسليم التلقائي: {str(exc)}")

            # Create OrderIssue for Admins
            OrderIssue.objects.update_or_create(
                order=order,
                defaults={
                    'issue_type': 'API_DELIVERY_FAILURE',
                    'details': f"تكرر الفشل {task.attempts} مرات. الخطأ: {str(exc)}. تم استرجاع الرصيد للمحفظة تلقائياً."
                }
            )

            # Alert customer and admin group
            try:
                from apps.notifications.services import CustomerNotifierService, AdminGroupNotifierService
                CustomerNotifierService.send_order_failed_refunded(order, str(exc))
                AdminGroupNotifierService.send_order_issue_alert(order, str(exc))
            except Exception as alert_err:
                logger.warning(f"Alert error on failed order {order.order_number}: {alert_err}")

            return f"Order {order.order_number} failed and refunded."
