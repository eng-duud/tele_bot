from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel
from apps.core.encryption import encrypt_data, decrypt_data
from apps.catalog.models import Product

class ApiProvider(TimeStampedModel):
    """External API Provider configuration with encrypted secrets."""
    PROVIDER_TYPE_CHOICES = (
        ('MOCK', 'مزود تجريبي ومحاكي (Mock / Simulator)'),
        ('CUSTOM_HTTP', 'مزود API خارجي حقيقي'),
    )

    name = models.CharField(_('اسم المزود'), max_length=150)
    provider_code = models.CharField(_('رمز المزود التعريفي'), max_length=50, unique=True)
    provider_type = models.CharField(_('نوع المزود'), max_length=20, choices=PROVIDER_TYPE_CHOICES, default='MOCK')
    base_url = models.URLField(_('رابط الـ API الأساسي'), blank=True)
    api_key_encrypted = models.TextField(_('مفتاح الـ API المشفر'), blank=True)
    api_secret_encrypted = models.TextField(_('كلمة السر أو Secret المشفرة'), blank=True)
    is_active = models.BooleanField(_('نشط'), default=True)

    class Meta:
        verbose_name = _('مزود خارجي')
        verbose_name_plural = _('المزودون الخارجيون')

    def __str__(self):
        return f"{self.name} [{self.provider_code}]"

    def set_api_key(self, raw_key: str):
        self.api_key_encrypted = encrypt_data(raw_key)

    def get_api_key(self) -> str:
        return decrypt_data(self.api_key_encrypted)

    def set_api_secret(self, raw_secret: str):
        self.api_secret_encrypted = encrypt_data(raw_secret)

    def get_api_secret(self) -> str:
        return decrypt_data(self.api_secret_encrypted)


class ProviderProductMapping(TimeStampedModel):
    """Mapping between local Catalog Product and External Provider Service."""
    product = models.OneToOneField(
        Product, 
        on_delete=models.CASCADE, 
        related_name='provider_mapping', 
        verbose_name=_('المنتج المحلي')
    )
    provider = models.ForeignKey(
        ApiProvider, 
        on_delete=models.CASCADE, 
        related_name='product_mappings', 
        verbose_name=_('المزود الخارجي')
    )
    external_service_id = models.CharField(_('معرف الخدمة لدى المزود'), max_length=150)
    custom_parameters = models.JSONField(_('معاملات إضافية (JSON)'), default=dict, blank=True)

    class Meta:
        verbose_name = _('ربط منتج بمزود')
        verbose_name_plural = _('روابط المنتجات بالمزودين')

    def __str__(self):
        return f"{self.product.name} ➡️ {self.provider.name} (ID: {self.external_service_id})"
