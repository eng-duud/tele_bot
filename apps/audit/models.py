from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel
from apps.users.models import TelegramProfile

class AuditLog(TimeStampedModel):
    """Immutable audit trail of administrative actions and sensitive changes."""
    admin = models.ForeignKey(
        TelegramProfile, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='audit_logs',
        verbose_name=_('المشرف المنفذ')
    )
    action = models.CharField(_('العملية'), max_length=100, db_index=True)
    resource_type = models.CharField(_('نوع العنصر'), max_length=50, db_index=True)
    resource_id = models.CharField(_('معرف العنصر'), max_length=100, db_index=True)
    before_state = models.JSONField(_('الحالة قبل التعديل'), default=dict, blank=True)
    after_state = models.JSONField(_('الحالة بعد التعديل'), default=dict, blank=True)
    notes = models.TextField(_('ملاحظات إضافية'), blank=True)

    class Meta:
        verbose_name = _('سجل تدقيق')
        verbose_name_plural = _('سجلات التدقيق')
        ordering = ['-created_at']

    def __str__(self):
        admin_name = self.admin.full_name if self.admin else "System"
        return f"[{self.action}] on {self.resource_type}#{self.resource_id} by {admin_name}"
