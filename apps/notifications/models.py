from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel

class RequiredChannel(TimeStampedModel):
    """Mandatory subscription channels required before bot usage."""
    channel_id = models.CharField(_('معرف القناة أو اليوزر (مثال: @Channel أو -100...)'), max_length=120, unique=True)
    channel_title = models.CharField(_('اسم القناة'), max_length=150)
    invite_link = models.URLField(_('رابط الدعوة للقناة'))
    is_mandatory = models.BooleanField(_('إجباري للدخول'), default=True)
    is_active = models.BooleanField(_('مفعلة'), default=True)
    display_order = models.PositiveIntegerField(_('الترتيب'), default=0)

    class Meta:
        verbose_name = _('قناة اشتراك إجباري')
        verbose_name_plural = _('قنوات الاشتراك الإجباري')
        ordering = ['display_order', '-created_at']

    def __str__(self):
        return f"{self.channel_title} ({self.channel_id})"


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
