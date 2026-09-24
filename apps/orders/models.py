import random
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel
from apps.users.models import TelegramProfile
from apps.catalog.models import Product

def generate_order_number() -> str:
    """Generate a clean human-readable order number e.g. ORD-847291."""
    return f"ORD-{random.randint(100000, 999999)}"

class Order(TimeStampedModel):
    """Customer purchase order with immutable pricing and full state machine."""
    STATUS_CHOICES = (
        ('PENDING', 'قيد الانتظار ⏳'),
        ('PROCESSING', 'جاري المعالجة والتسليم ⚙️'),
        ('COMPLETED', 'مكتمل بنجاح ✅'),
        ('FAILED', 'فشل التنفيذ ⚠️'),
        ('CANCELLED', 'ملغي 🚫'),
        ('REFUNDED', 'مسترجع بالكامل 🔄'),
    )

    order_number = models.CharField(_('رقم الطلب'), max_length=50, unique=True, default=generate_order_number, db_index=True)
    user = models.ForeignKey(TelegramProfile, on_delete=models.CASCADE, related_name='orders', verbose_name=_('العميل'))
    total_amount_yer = models.DecimalField(_('المبلغ الإجمالي (YER)'), max_digits=14, decimal_places=2)
    currency_used = models.CharField(_('العملة المستخدمة'), max_length=10, default='YER')
    status = models.CharField(_('حالة الطلب'), max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    customer_input_data = models.TextField(_('بيانات مدخلة من العميل (ID/حساب)'), blank=True)
    delivered_data = models.TextField(_('البيانات المسلمة للعميل'), blank=True)
    failure_reason = models.TextField(_('سبب الفشل إن وجد'), blank=True)

    class Meta:
        verbose_name = _('طلب شراء')
        verbose_name_plural = _('طلبات الشراء')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_number} - {self.user} - {self.total_amount_yer:,.0f} YER [{self.get_status_display()}]"


class OrderItem(TimeStampedModel):
    """Snapshot item linking product details at the exact moment of checkout."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name=_('الطلب'))
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name='order_items', verbose_name=_('المنتج'))
    product_name_snapshot = models.CharField(_('اسم المنتج وقت الشراء'), max_length=255)
    unit_price_snapshot_yer = models.DecimalField(_('سعر الوحدة وقت الشراء (YER)'), max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(_('الكمية'), default=1)
    total_price_yer = models.DecimalField(_('الإجمالي بالريال اليمني'), max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = _('عنصر طلب')
        verbose_name_plural = _('عناصر الطلبات')

    def __str__(self):
        return f"{self.quantity}x {self.product_name_snapshot} ({self.total_price_yer:,.0f} YER)"


class OrderStatusHistory(TimeStampedModel):
    """Audit trail of order state machine transitions."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='history', verbose_name=_('الطلب'))
    from_status = models.CharField(_('الحالة السابقة'), max_length=20)
    to_status = models.CharField(_('الحالة الجديدة'), max_length=20)
    notes = models.TextField(_('ملاحظات التغيير'), blank=True)

    class Meta:
        verbose_name = _('تاريخ حالة الطلب')
        verbose_name_plural = _('سجل حالات الطلب')
        ordering = ['created_at']
