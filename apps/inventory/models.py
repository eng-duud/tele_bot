from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel
from apps.core.encryption import encrypt_data, decrypt_data
from apps.catalog.models import Product
from apps.users.models import TelegramProfile

class StockItem(TimeStampedModel):
    """
    Individual digital asset (account credentials, license key, gift card code).
    All secret payloads are symmetrically encrypted in the DB using Fernet.
    """
    STATUS_CHOICES = (
        ('AVAILABLE', 'متاح للبيع'),
        ('RESERVED', 'محجوز لطلب قيد المعالجة'),
        ('SOLD', 'تم بيعه وتسليمه'),
        ('DISABLED', 'معطل / غير صالح'),
    )

    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name='stock_items', 
        verbose_name=_('المنتج')
    )
    encrypted_data = models.TextField(_('البيانات المشفرة (حساب/كود/مفتاح)'))
    item_identifier = models.CharField(_('معرف أو رقم العنصر'), max_length=100, blank=True)
    status = models.CharField(_('حالة العنصر'), max_length=20, choices=STATUS_CHOICES, default='AVAILABLE', db_index=True)
    order_id = models.CharField(_('معرف الطلب المرتبط'), max_length=100, blank=True, db_index=True)
    sold_at = models.DateTimeField(_('تاريخ البيع'), null=True, blank=True)

    class Meta:
        verbose_name = _('عنصر مخزون رقمي')
        verbose_name_plural = _('عناصر المخزون الرقمي')
        ordering = ['created_at']

    def __str__(self):
        return f"{self.product.name} - #{self.item_identifier or str(self.id)[:6]} [{self.get_status_display()}]"

    def set_secret(self, plain_text: str):
        """Encrypt and store plaintext payload."""
        self.encrypted_data = encrypt_data(plain_text)

    def get_secret(self) -> str:
        """Decrypt and return plaintext payload."""
        return decrypt_data(self.encrypted_data)


class RestockSubscription(TimeStampedModel):
    """Waitlist subscription to alert users when out-of-stock products are replenished."""
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name='restock_subscribers', 
        verbose_name=_('المنتج')
    )
    user = models.ForeignKey(
        TelegramProfile, 
        on_delete=models.CASCADE, 
        related_name='restock_alerts', 
        verbose_name=_('المستخدم')
    )
    is_notified = models.BooleanField(_('تم إرسال الإشعار'), default=False)

    class Meta:
        verbose_name = _('اشتراك إشعار توفر المخزون')
        verbose_name_plural = _('اشتراكات إشعارات توفر المخزون')
        unique_together = ('product', 'user')

    def __str__(self):
        return f"{self.user} 🔔 {self.product.name}"
