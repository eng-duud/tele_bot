from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel
from apps.users.models import TelegramProfile
from apps.orders.models import Order

class DigitalService(TimeStampedModel):
    """Digital service (e.g. customized design, software installation, account activation)."""
    SERVICE_TYPE_CHOICES = (
        ('FIXED', 'خدمة بسعر محدد وثابت'),
        ('CUSTOM', 'خدمة مخصصة تتطلب تسعير من الإدارة (Quote)'),
    )

    name = models.CharField(_('اسم الخدمة'), max_length=200)
    description = models.TextField(_('وصف الخدمة وتفاصيلها'))
    service_type = models.CharField(_('نوع الخدمة'), max_length=20, choices=SERVICE_TYPE_CHOICES, default='FIXED')
    price_yer = models.DecimalField(_('السعر الثابت (YER)'), max_digits=12, decimal_places=2, default=Decimal('0.00'))
    instructions = models.TextField(_('البيانات والمرفقات المطلوبة من العميل'), blank=True)
    is_active = models.BooleanField(_('نشطة'), default=True)

    class Meta:
        verbose_name = _('خدمة رقمية')
        verbose_name_plural = _('الخدمات الرقمية')

    def __str__(self):
        return f"{self.name} [{self.get_service_type_display()}]"


class ServiceRequest(TimeStampedModel):
    """Customer custom service order and quotation lifecycle."""
    STATUS_CHOICES = (
        ('PENDING_QUOTE', 'بانتظار تسعير الإدارة ⏳'),
        ('QUOTE_PROVIDED', 'تم تقديم عرض السعر للعميل 💼'),
        ('ACCEPTED', 'تم قبول العرض والخصم بنجاح ✅'),
        ('REJECTED', 'تم رفض العرض أو إلغاء الطلب ❌'),
        ('COMPLETED', 'تم إنجاز وتسليم الخدمة 🎯'),
    )

    user = models.ForeignKey(TelegramProfile, on_delete=models.CASCADE, related_name='service_requests', verbose_name=_('العميل'))
    service = models.ForeignKey(DigitalService, on_delete=models.CASCADE, related_name='requests', verbose_name=_('الخدمة'))
    customer_notes = models.TextField(_('ملاحظات وتفاصيل طلب العميل'))
    attachment_file_id = models.CharField(_('معرف المرفق في تليجرام'), max_length=255, blank=True)
    attachment_url = models.URLField(_('رابط المرفق السحابي'), blank=True)
    
    status = models.CharField(_('حالة الطلب'), max_length=20, choices=STATUS_CHOICES, default='PENDING_QUOTE', db_index=True)
    quote_amount_yer = models.DecimalField(_('سعر العرض المقدم (YER)'), max_digits=14, decimal_places=2, null=True, blank=True)
    quote_expires_at = models.DateTimeField(_('تاريخ انتهاء صلاحية العرض'), null=True, blank=True)
    admin_notes = models.TextField(_('ملاحظات المشرف'), blank=True)
    
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='service_request_source', verbose_name=_('الطلب المنشأ'))

    class Meta:
        verbose_name = _('طلب خدمة')
        verbose_name_plural = _('طلبات الخدمات')
        ordering = ['-created_at']

    def __str__(self):
        return f"Service #{str(self.id)[:6]} - {self.service.name} ({self.user}) [{self.get_status_display()}]"
