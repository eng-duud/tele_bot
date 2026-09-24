from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel
from apps.users.models import TelegramProfile

class Wallet(TimeStampedModel):
    """Customer financial wallet in YER base currency."""
    profile = models.OneToOneField(
        TelegramProfile, 
        on_delete=models.CASCADE, 
        related_name='wallet', 
        verbose_name=_('الملف الشخصي')
    )
    balance_yer = models.DecimalField(
        _('الرصيد بالريال اليمني'), 
        max_digits=14, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    is_locked = models.BooleanField(_('محفظة مقفلة / مجمدة'), default=False)

    class Meta:
        verbose_name = _('محفظة')
        verbose_name_plural = _('المحافظ')

    def __str__(self):
        return f"Wallet ({self.profile}): {self.balance_yer:,.0f} YER"


class WalletTransaction(TimeStampedModel):
    """Immutable ledger record of all wallet balance movements."""
    TX_TYPE_CHOICES = (
        ('DEPOSIT', 'إيداع رصيد'),
        ('PURCHASE', 'شراء منتج أو خدمة'),
        ('REFUND', 'استرجاع مالي'),
        ('ADJUSTMENT', 'تعديل إداري'),
    )

    wallet = models.ForeignKey(
        Wallet, 
        on_delete=models.CASCADE, 
        related_name='transactions', 
        verbose_name=_('المحفظة')
    )
    tx_type = models.CharField(_('نوع العملية'), max_length=20, choices=TX_TYPE_CHOICES, db_index=True)
    amount = models.DecimalField(_('المبلغ'), max_digits=14, decimal_places=2)
    balance_before = models.DecimalField(_('الرصيد قبل'), max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(_('الرصيد بعد'), max_digits=14, decimal_places=2)
    reference_id = models.CharField(_('الرقم المرجعي للعملية'), max_length=120, blank=True, db_index=True)
    idempotency_key = models.CharField(_('مفتاح منع التكرار'), max_length=150, unique=True, null=True, blank=True, db_index=True)
    description = models.TextField(_('وصف العملية'), blank=True)

    class Meta:
        verbose_name = _('حركة مالية')
        verbose_name_plural = _('الحركات المالية')
        ordering = ['-created_at']

    def __str__(self):
        sign = "+" if self.amount > 0 else ""
        return f"[{self.get_tx_type_display()}] {sign}{self.amount:,.0f} YER (Bal: {self.balance_after:,.0f})"
