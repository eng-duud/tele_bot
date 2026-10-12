from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel
from apps.orders.models import Order
from apps.users.models import TelegramProfile

class FulfillmentTask(TimeStampedModel):
    """Background delivery task queue item."""
    STATUS_CHOICES = (
        ('QUEUED', 'في الانتظار ⏳'),
        ('RUNNING', 'جاري التنفيذ ⚙️'),
        ('SUCCESS', 'تم بنجاح ✅'),
        ('FAILED', 'فشل نهائي ❌'),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='fulfillment_tasks', verbose_name=_('الطلب'))
    status = models.CharField(_('حالة المهمة'), max_length=20, choices=STATUS_CHOICES, default='QUEUED', db_index=True)
    attempts = models.PositiveIntegerField(_('عدد المحاولات'), default=0)
    last_error = models.TextField(_('آخر خطأ مسجل'), blank=True)
    provider_idempotency_key = models.CharField(
        _('مفتاح منع تكرار المزود'),
        max_length=255,
        blank=True,
        null=True,
        default=''
    )

    class Meta:
        verbose_name = _('مهمة تسليم')
        verbose_name_plural = _('مهام التسليم')
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['order'], name='unique_fulfillment_task_per_order'),
        ]

    def __str__(self):
        return f"Fulfillment for {self.order.order_number} [{self.get_status_display()}] (Attempt: {self.attempts}/3)"


class OrderIssue(TimeStampedModel):
    """Fulfillment failure or customer exception requiring administrative attention."""
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='issue', verbose_name=_('الطلب'))
    issue_type = models.CharField(_('نوع المشكلة'), max_length=50, default='API_DELIVERY_FAILURE')
    details = models.TextField(_('تفاصيل المشكلة والخطأ'))
    is_resolved = models.BooleanField(_('تم الحل'), default=False, db_index=True)
    resolved_by = models.ForeignKey(TelegramProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_issues', verbose_name=_('تم الحل بواسطة'))
    resolution_notes = models.TextField(_('ملاحظات الحل'), blank=True)

    class Meta:
        verbose_name = _('مشكلة طلب')
        verbose_name_plural = _('مشاكل الطلبات')
        ordering = ['-created_at']

    def __str__(self):
        status = "محلولة" if self.is_resolved else "غير محلولة"
        return f"Issue: {self.order.order_number} - {self.issue_type} [{status}]"
