from datetime import timedelta
from decimal import Decimal
from typing import Tuple, Optional
from django.db import transaction
from django.utils import timezone
from apps.users.models import TelegramProfile
from apps.wallet.services import WalletService
from apps.orders.models import Order, OrderItem
from apps.services_app.models import DigitalService, ServiceRequest

class ServiceWorkflowService:
    """Service handling custom quote negotiations, validity windows, and service orders."""

    @staticmethod
    def submit_request(
        user: TelegramProfile, 
        service: DigitalService, 
        customer_notes: str, 
        attachment_file_id: str = "",
        attachment_url: str = ""
    ) -> ServiceRequest:
        """Submit a new service quotation request."""
        return ServiceRequest.objects.create(
            user=user,
            service=service,
            customer_notes=customer_notes.strip(),
            attachment_file_id=attachment_file_id,
            attachment_url=attachment_url,
            status='PENDING_QUOTE'
        )

    @staticmethod
    def set_quote(
        request_id: str, 
        amount_yer: Decimal, 
        valid_hours: int = 24, 
        admin_notes: str = ""
    ) -> Tuple[bool, str, Optional[ServiceRequest]]:
        """Admin sets quotation price and expiration deadline."""
        req = ServiceRequest.objects.filter(id=request_id).first()
        if not req:
            return False, "طلب الخدمة غير موجود.", None

        amount_yer = Decimal(str(amount_yer))
        if amount_yer <= 0:
            return False, "مبلغ التسعير يجب أن يكون أكبر من الصفر.", None

        req.quote_amount_yer = amount_yer
        req.quote_expires_at = timezone.now() + timedelta(hours=valid_hours)
        req.admin_notes = admin_notes
        req.status = 'QUOTE_PROVIDED'
        req.save(update_fields=['quote_amount_yer', 'quote_expires_at', 'admin_notes', 'status', 'updated_at'])

        return True, "تم تقديم عرض السعر للعميل بنجاح.", req

    @classmethod
    def accept_quote_and_pay(cls, request_id: str, user: TelegramProfile) -> Tuple[bool, str, Optional[Order]]:
        """
        Customer accepts quotation: verifies expiration, debits wallet, and creates Order atomically.
        """
        with transaction.atomic():
            req = ServiceRequest.objects.select_for_update().filter(id=request_id, user=user).first()
            if not req:
                return False, "طلب الخدمة غير موجود.", None

            if req.status != 'QUOTE_PROVIDED':
                return False, f"لا يمكن قبول هذا الطلب (حالته: {req.get_status_display()}).", None

            if req.quote_expires_at and timezone.now() > req.quote_expires_at:
                return False, "عفواً، انتهت مدة صلاحية عرض السعر المقدم.", None

            amount = req.quote_amount_yer
            wallet = WalletService.get_or_create_wallet(user)

            # Debit wallet with idempotency
            idempotency_key = f"service-req-pay-{req.id}"
            tx, _ = WalletService.debit(
                wallet=wallet,
                amount=amount,
                reference_id=f"SRV-{str(req.id)[:8]}",
                description=f"دفع قيمة خدمة: {req.service.name}",
                idempotency_key=idempotency_key
            )

            # Create Order
            order = Order.objects.create(
                user=user,
                total_amount_yer=amount,
                currency_used='YER',
                status='PROCESSING',
                customer_input_data=req.customer_notes
            )

            # Create snapshot Item
            OrderItem.objects.create(
                order=order,
                product=None,
                product_name_snapshot=f"خدمة: {req.service.name}",
                unit_price_snapshot_yer=amount,
                quantity=1,
                total_price_yer=amount
            )

            req.status = 'ACCEPTED'
            req.order = order
            req.save(update_fields=['status', 'order', 'updated_at'])

            return True, f"تم قبول العرض وخصم {amount:,.0f} YER بنجاح.", order

    @staticmethod
    def reject_quote(request_id: str, user: TelegramProfile) -> Tuple[bool, str]:
        """Customer declines quotation."""
        req = ServiceRequest.objects.filter(id=request_id, user=user).first()
        if not req:
            return False, "طلب الخدمة غير موجود."
        req.status = 'REJECTED'
        req.save(update_fields=['status', 'updated_at'])
        return True, "تم إلغاء طلب الخدمة."
