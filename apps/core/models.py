import uuid
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _

class TimeStampedModel(models.Model):
    """Abstract base model with auto-managed timestamps and UUID identifier."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']

class ExchangeRate(TimeStampedModel):
    """Dynamic exchange rates between currencies (e.g. 1 USD = 550 YER)."""
    source_currency = models.CharField(_('العملة المصدر'), max_length=10, default='USD')
    target_currency = models.CharField(_('العملة الهدف'), max_length=10, default='YER')
    rate = models.DecimalField(_('سعر الصرف'), max_digits=12, decimal_places=4, default=Decimal('550.0000'))
    is_active = models.BooleanField(_('نشط'), default=True)

    _cached_usd_to_yer: Decimal = Decimal('550.0000')

    class Meta:
        verbose_name = _('سعر صرف')
        verbose_name_plural = _('أسعار الصرف')
        unique_together = ('source_currency', 'target_currency')

    def __str__(self):
        return f"1 {self.source_currency} = {self.rate} {self.target_currency}"

    @classmethod
    def get_usd_to_yer_rate(cls) -> Decimal:
        """Helper to get current active USD to YER rate."""
        # Detect if we are inside an active asyncio event loop thread
        try:
            import asyncio
            asyncio.get_running_loop()
            in_async = True
        except RuntimeError:
            in_async = False

        if in_async:
            return cls._cached_usd_to_yer

        try:
            obj = cls.objects.filter(source_currency='USD', target_currency='YER', is_active=True).first()
            if obj:
                cls._cached_usd_to_yer = obj.rate
                return obj.rate
        except Exception:
            pass
        return cls._cached_usd_to_yer

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.source_currency == 'USD' and self.target_currency == 'YER' and self.is_active:
            ExchangeRate._cached_usd_to_yer = self.rate

class SystemSetting(TimeStampedModel):
    """Key-value dynamic system configuration."""
    key = models.CharField(_('مفتاح الإعداد'), max_length=100, unique=True)
    value = models.TextField(_('القيمة'))
    description = models.CharField(_('الوصف'), max_length=255, blank=True)

    class Meta:
        verbose_name = _('إعداد نظام')
        verbose_name_plural = _('إعدادات النظام')

    def __str__(self):
        return f"{self.key}: {self.value}"
