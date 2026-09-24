from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel

class TelegramProfile(TimeStampedModel):
    """Profile representing a Telegram customer or admin."""
    CURRENCY_CHOICES = (
        ('YER', 'ريال يمني (YER)'),
        ('USD', 'دولار أمريكي (USD)'),
    )

    telegram_id = models.BigIntegerField(_('معرف التليجرام'), unique=True, db_index=True)
    username = models.CharField(_('اسم المستخدم'), max_length=255, blank=True, null=True)
    first_name = models.CharField(_('الاسم الأول'), max_length=255, blank=True)
    last_name = models.CharField(_('الاسم الأخير'), max_length=255, blank=True)
    preferred_currency = models.CharField(_('العملة المفضلة'), max_length=10, choices=CURRENCY_CHOICES, default='YER')
    is_banned = models.BooleanField(_('محظور'), default=False)
    is_admin = models.BooleanField(_('مشرف'), default=False)

    class Meta:
        verbose_name = _('مستخدم تليجرام')
        verbose_name_plural = _('مستخدمو تليجرام')

    def __str__(self):
        name = self.first_name or self.username or str(self.telegram_id)
        return f"{name} ({self.telegram_id})"

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.last_name]
        return " ".join([p for p in parts if p]).strip() or f"User-{self.telegram_id}"


class AdminPermission(TimeStampedModel):
    """Granular permissions for RBAC."""
    PERMISSION_CHOICES = (
        ('MANAGE_PRODUCTS', 'إدارة المنتجات'),
        ('MANAGE_CATEGORIES', 'إدارة التصنيفات'),
        ('MANAGE_INVENTORY', 'إدارة المخزون'),
        ('MANAGE_ORDERS', 'إدارة الطلبات'),
        ('MANAGE_PAYMENTS', 'إدارة ومراجعة المدفوعات'),
        ('MANAGE_USERS', 'إدارة المستخدمين'),
        ('MANAGE_SERVICES', 'إدارة الخدمات الرقمية'),
        ('MANAGE_PROVIDERS', 'إدارة المزودين'),
        ('MANAGE_ADMINS', 'إدارة المشرفين'),
        ('MANAGE_SETTINGS', 'إدارة الإعدادات والعملات'),
        ('VIEW_AUDIT_LOGS', 'عرض سجلات التدقيق'),
    )

    codename = models.CharField(_('كود الصلاحية'), max_length=50, unique=True, choices=PERMISSION_CHOICES)
    description = models.CharField(_('وصف الصلاحية'), max_length=255, blank=True)

    class Meta:
        verbose_name = _('صلاحية إدارية')
        verbose_name_plural = _('الصلاحيات الإدارية')

    def __str__(self):
        return f"{self.get_codename_display()} ({self.codename})"


class AdminRole(TimeStampedModel):
    """Role grouping multiple permissions."""
    name = models.CharField(_('اسم الدور'), max_length=100, unique=True)
    description = models.TextField(_('الوصف'), blank=True)
    permissions = models.ManyToManyField(AdminPermission, verbose_name=_('الصلاحيات'), blank=True)

    class Meta:
        verbose_name = _('دور إداري')
        verbose_name_plural = _('الأدوار الإدارية')

    def __str__(self):
        return self.name


class AdminProfile(TimeStampedModel):
    """Admin configuration mapped to a Telegram user."""
    profile = models.OneToOneField(TelegramProfile, on_delete=models.CASCADE, related_name='admin_details', verbose_name=_('الملف الشخصي'))
    role = models.ForeignKey(AdminRole, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_('الدور'))
    custom_permissions = models.ManyToManyField(AdminPermission, blank=True, verbose_name=_('صلاحيات إضافية'))
    is_super_admin = models.BooleanField(_('مشرف عام'), default=False)
    is_active = models.BooleanField(_('نشط'), default=True)

    class Meta:
        verbose_name = _('مشرف نظام')
        verbose_name_plural = _('مشرفو النظام')

    def __str__(self):
        return f"Admin: {self.profile} [{'Super' if self.is_super_admin else 'Staff'}]"

    def has_permission(self, permission_codename: str) -> bool:
        """Check if admin possesses a specific permission."""
        if not self.is_active:
            return False
        if self.is_super_admin:
            return True
        if self.role and self.role.permissions.filter(codename=permission_codename).exists():
            return True
        return self.custom_permissions.filter(codename=permission_codename).exists()
