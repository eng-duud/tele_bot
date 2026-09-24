from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel
from apps.users.models import TelegramProfile

class PaymentMethod(TimeStampedModel):
    """Dynamically manageable deposit methods (e.g. Kuraimi, Jeeb, Cash networks)."""
    name = models.CharField(_('اسم طريقة الدفع'), max_length=150)
    icon = models.CharField(_('أيقونة الطريقة'), max_length=20, default='💳')
    account_number = models.CharField(_('رقم الحساب أو النقطة'), max_length=100)
    account_name = models.CharField(_('اسم صاحب الحساب'), max_length=150, blank=True)
    instructions = models.TextField(_('تعليمات التحويل للعميل'))
    requires_proof_image = models.BooleanField(_('تتطلب صورة إشعار التحويل'), default=True)
    requires_tx_number = models.BooleanField(_('تتطلب رقم الحوالة / السند'), default=True)
    min_deposit_yer = models.DecimalField(_('الحد الأدنى (YER)'), max_digits=12, decimal_places=2, default=Decimal('1000'))
    max_deposit_yer = models.DecimalField(_('الحد الأقصى (YER)'), max_digits=12, decimal_places=2, default=Decimal('500000'))
    is_active = models.BooleanField(_('مفعلة'), default=True)
    display_order = models.PositiveIntegerField(_('ترتيب العرض'), default=0)

    class Meta:
        verbose_name = _('طريقة دفع')
        verbose_name_plural = _('طرق الدفع')
        ordering = ['display_order', '-created_at']

    def __str__(self):
        return f"{self.icon} {self.name} ({self.account_number})"


class PaymentRequest(TimeStampedModel):
    """Customer wallet top-up request submitted for administrative verification."""
    STATUS_CHOICES = (
        ('PENDING', 'قيد المراجعة ⏳'),
        ('APPROVED', 'تم القبول والاعتماد ✅'),
        ('REJECTED', 'تم الرفض ❌'),
    )

    user = models.ForeignKey(
        TelegramProfile, 
        on_delete=models.CASCADE, 
        related_name='payment_requests', 
        verbose_name=_('العميل')
    )
    payment_method = models.ForeignKey(
        PaymentMethod, 
        on_delete=models.PROTECT, 
        related_name='requests', 
        verbose_name=_('طريقة الدفع')
    )
    amount_yer = models.DecimalField(_('المبلغ المحول (YER)'), max_digits=14, decimal_places=2)
    tx_number = models.CharField(_('رقم الحوالة / العملية'), max_length=150, blank=True)
    proof_image_file_id = models.CharField(_('معرف صورة الإشعار في تليجرام'), max_length=255, blank=True)
    proof_image_url = models.URLField(_('رابط صورة الإشعار'), blank=True)
    status = models.CharField(_('حالة الطلب'), max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    
    reviewed_by = models.ForeignKey(
        TelegramProfile, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='reviewed_payments',
        verbose_name=_('تمت المراجعة بواسطة')
    )
    reviewed_at = models.DateTimeField(_('تاريخ المراجعة'), null=True, blank=True)
    rejection_reason = models.TextField(_('سبب الرفض'), blank=True)
    admin_message_id = models.BigIntegerField(_('معرف رسالة مجموعة الإدارة'), null=True, blank=True)

    class Meta:
        verbose_name = _('طلب شحن رصيد')
        verbose_name_plural = _('طلبات شحن الرصيد')
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment #{str(self.id)[:8]} - {self.user} - {self.amount_yer:,.0f} YER [{self.get_status_display()}]"
