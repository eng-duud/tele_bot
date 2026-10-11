import secrets
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel
from apps.users.models import TelegramProfile

def generate_ticket_number() -> str:
    """Generate friendly and unique ticket code e.g. TIC-261011-9B3E."""
    today = timezone.now().strftime("%y%m%d")
    entropy = secrets.token_hex(2).upper()
    return f"TIC-{today}-{entropy}"

class SupportTicket(TimeStampedModel):
    """Customer support ticket conversation."""
    STATUS_CHOICES = (
        ('OPEN', 'مفتوحة 🟢'),
        ('ANSWERED', 'تم الرد 💬'),
        ('CLOSED', 'مغلقة 🔒'),
    )

    ticket_number = models.CharField(
        _('رقم التذكرة'), 
        max_length=50, 
        unique=True, 
        default=generate_ticket_number,
        db_index=True
    )
    user = models.ForeignKey(
        TelegramProfile, 
        on_delete=models.CASCADE, 
        related_name='support_tickets', 
        verbose_name=_('العميل')
    )
    subject = models.CharField(_('موضوع التذكرة / المشكلة'), max_length=255, blank=True)
    status = models.CharField(_('حالة التذكرة'), max_length=20, choices=STATUS_CHOICES, default='OPEN', db_index=True)
    admin_message_id = models.BigIntegerField(_('معرف رسالة التذكرة في مجموعة الإدارة'), null=True, blank=True)
    
    last_answered_by = models.ForeignKey(
        TelegramProfile, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='answered_tickets', 
        verbose_name=_('آخر رد بواسطة')
    )
    last_answered_at = models.DateTimeField(_('تاريخ آخر رد'), null=True, blank=True)
    closed_at = models.DateTimeField(_('تاريخ الإغلاق'), null=True, blank=True)

    class Meta:
        verbose_name = _('تذكرة دعم فني')
        verbose_name_plural = _('تذاكر الدعم الفني')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ticket_number} - {self.user.full_name} [{self.get_status_display()}]"


class TicketMessage(TimeStampedModel):
    """Message item inside a support ticket conversation."""
    ticket = models.ForeignKey(
        SupportTicket, 
        on_delete=models.CASCADE, 
        related_name='messages', 
        verbose_name=_('التذكرة')
    )
    sender = models.ForeignKey(
        TelegramProfile, 
        on_delete=models.CASCADE, 
        verbose_name=_('المرسل')
    )
    is_from_admin = models.BooleanField(_('من الإدارة'), default=False)
    text = models.TextField(_('نص الرسالة'))
    photo_file_id = models.CharField(_('معرف الصورة في تليجرام'), max_length=255, blank=True)
    document_file_id = models.CharField(_('معرف الملف في تليجرام'), max_length=255, blank=True)

    class Meta:
        verbose_name = _('رسالة دعم فني')
        verbose_name_plural = _('رسائل الدعم الفني')
        ordering = ['created_at']

    def __str__(self):
        author = "Admin" if self.is_from_admin else "Customer"
        return f"[{author}] {self.ticket.ticket_number}: {self.text[:30]}"
