from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel

class RequiredChannel(TimeStampedModel):
    """Dynamic channels manager for subscriptions, success broadcasts, and backups."""
    CHANNEL_TYPE_CHOICES = (
        ('OFFICIAL', '📢 قناة البوت الرسمية'),
        ('SUCCESS', '⚡ قناة التفعيلات والعمليات الناجحة'),
        ('SUPPORT', '🎧 قناة / مجموعة الدعم الفني'),
        ('ADMIN', '🛡️ قناة / مجموعة إشعارات الإدارة'),
        ('CUSTOM', '🔒 قناة اشتراك إجباري إضافية'),
        ('SUBSCRIPTION', '🔒 اشتراك إجباري للعملاء'),
        ('BACKUP', '📦 نسخ احتياطي للبيانات'),
        ('ALERTS', '🔔 إشعارات الإدارة والمشرفين'),
    )

    channel_id = models.CharField(_('معرف القناة أو اليوزر (مثال: @Channel أو -100...)'), max_length=120, db_index=True)
    channel_title = models.CharField(_('اسم القناة'), max_length=150)
    channel_type = models.CharField(_('نوع القناة والغرض منها'), max_length=30, choices=CHANNEL_TYPE_CHOICES, default='OFFICIAL', db_index=True)
    invite_link = models.URLField(_('رابط الدعوة للقناة'), blank=True, default='')
    is_mandatory = models.BooleanField(_('إجباري للدخول'), default=True)
    is_active = models.BooleanField(_('مفعلة'), default=True)
    display_order = models.PositiveIntegerField(_('الترتيب'), default=0)

    class Meta:
        verbose_name = _('قناة نظام / متجر')
        verbose_name_plural = _('قنوات النظام والمتجر')
        ordering = ['display_order', '-created_at']

    def __str__(self):
        return f"{self.channel_title} [{self.get_channel_type_display()}] ({self.channel_id})"


class BroadcastAnnouncement(TimeStampedModel):
    """Mass message broadcast to bot subscribers."""
    message_text = models.TextField(_('نص الرسالة'))
    target_count = models.PositiveIntegerField(_('المستهدفون'), default=0)
    sent_count = models.PositiveIntegerField(_('تم الإرسال بنجاح'), default=0)
    failed_count = models.PositiveIntegerField(_('فشل الإرسال'), default=0)
    is_completed = models.BooleanField(_('مكتمل'), default=False)

    class Meta:
        verbose_name = _('رسالة بث جماعي')
        verbose_name_plural = _('رسائل البث الجماعي')
        ordering = ['-created_at']

    def __str__(self):
        return f"Broadcast #{str(self.id)[:6]} - {self.sent_count}/{self.target_count}"
