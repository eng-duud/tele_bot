from decimal import Decimal
from typing import Tuple, Optional
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from apps.users.models import TelegramProfile
from apps.payments.models import PaymentMethod, PaymentRequest
from apps.wallet.services import WalletService

class PaymentService:
    """Service handling customer top-up submissions and idempotent admin approvals."""

    @staticmethod
    def get_top_up_block_reason(user: TelegramProfile) -> str:
        """Return a user-facing reason when a new top-up should be delayed."""
        now = timezone.now()
        if PaymentRequest.objects.filter(user=user, status='PENDING').exists():
            return "لديك طلب شحن قيد المراجعة بالفعل. انتظر نتيجته قبل إرسال طلب جديد."

        recent_count = PaymentRequest.objects.filter(
            user=user,
            created_at__gte=now - timedelta(minutes=10),
        ).exclude(status='REJECTED').count()
        if recent_count >= 3:
            return "تم الوصول إلى حد طلبات الشحن المؤقت (3 طلبات خلال 10 دقائق). حاول لاحقاً."
        return ""

    @staticmethod
    def create_payment_request(
        user: TelegramProfile,
        payment_method: PaymentMethod,
        amount_yer: Decimal,
        tx_number: str = "",
        proof_image_file_id: str = "",
        proof_image_url: str = ""
    ) -> PaymentRequest:
        """Create a new pending deposit request."""
        amount_yer = Decimal(str(amount_yer))
        if amount_yer < payment_method.min_deposit_yer:
            raise ValueError(f"المبلغ أقل من الحد الأدنى المسموح ({payment_method.min_deposit_yer:,.0f} YER).")
        if amount_yer > payment_method.max_deposit_yer:
            raise ValueError(f"المبلغ يتجاوز الحد الأقصى المسموح ({payment_method.max_deposit_yer:,.0f} YER).")

        # Lock the profile so two rapid submissions cannot both pass the
        # pending/rate-limit checks in separate bot updates.
        from apps.users.models import TelegramProfile as Profile
        with transaction.atomic():
            locked_user = Profile.objects.select_for_update().get(id=user.id)
            block_reason = PaymentService.get_top_up_block_reason(locked_user)
            if block_reason:
                raise ValueError(block_reason)
            return PaymentRequest.objects.create(
                user=locked_user,
                payment_method=payment_method,
                amount_yer=amount_yer,
                tx_number=tx_number.strip(),
                proof_image_file_id=proof_image_file_id,
                proof_image_url=proof_image_url,
                status='PENDING'
            )

    @classmethod
    def approve_payment(
        cls, 
        payment_request_id: str, 
        admin_profile: TelegramProfile
    ) -> Tuple[bool, str, Optional[PaymentRequest]]:
        """
        Approve top-up request, credit customer wallet, and enforce idempotency.
        """
        with transaction.atomic():
            req = PaymentRequest.objects.select_for_update().select_related('user', 'payment_method').filter(id=payment_request_id).first()
            if not req:
                return False, "طلب الدفع غير موجود.", None

            # Enforce idempotency: If already approved, do nothing and return success
            if req.status == 'APPROVED':
                return True, "تم قبول هذا الطلب واعتماده مسبقاً.", req

            if req.status == 'REJECTED':
                return False, "لا يمكن قبول طلب تم رفضه بالفعل.", req

            # Deposit into wallet atomically
            wallet = WalletService.get_or_create_wallet(req.user)
            idempotency_key = f"payreq-approve-{req.id}"
            
            tx, created = WalletService.deposit(
                wallet=wallet,
                amount=req.amount_yer,
                reference_id=f"PAY-{str(req.id)[:8]}",
                description=f"شحن رصيد معتمد عبر {req.payment_method.name} (حوالة #{req.tx_number})",
                idempotency_key=idempotency_key
            )

            # Update request status
            req.status = 'APPROVED'
            req.reviewed_by = admin_profile
            req.reviewed_at = timezone.now()
            req.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])

            return True, f"تم قبول الشحن وإيداع {req.amount_yer:,.0f} YER بنجاح في محفظة العميل.", req

    @classmethod
    def reject_payment(
        cls, 
        payment_request_id: str, 
        admin_profile: TelegramProfile, 
        reason: str = ""
    ) -> Tuple[bool, str, Optional[PaymentRequest]]:
        """
        Reject top-up request with explanation.
        """
        with transaction.atomic():
            req = PaymentRequest.objects.select_for_update().select_related('user', 'payment_method').filter(id=payment_request_id).first()
            if not req:
                return False, "طلب الدفع غير موجود.", None

            if req.status == 'APPROVED':
                return False, "لا يمكن رفض طلب تم اعتماده وشحن رصيده بالفعل.", req

            if req.status == 'REJECTED':
                return True, "هذا الطلب مرفوض مسبقاً.", req

            req.status = 'REJECTED'
            req.reviewed_by = admin_profile
            req.reviewed_at = timezone.now()
            req.rejection_reason = reason or "لم يتم توضيح السبب"
            req.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'updated_at'])

            return True, "تم رفض طلب الشحن بنجاح.", req
