from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel

class Category(TimeStampedModel):
    """Hierarchical catalog categories and subcategories."""
    parent = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='subcategories',
        verbose_name=_('التصنيف الأب')
    )
    name = models.CharField(_('اسم التصنيف'), max_length=150)
    slug = models.SlugField(_('الاسم اللطيف (Slug)'), max_length=150, unique=True, allow_unicode=True)
    icon = models.CharField(_('أيقونة التصنيف'), max_length=20, default='📁')
    description = models.TextField(_('الوصف'), blank=True)
    is_active = models.BooleanField(_('نشط'), default=True)
    display_order = models.PositiveIntegerField(_('ترتيب العرض'), default=0)

    class Meta:
        verbose_name = _('تصنيف')
        verbose_name_plural = _('التصنيفات')
        ordering = ['display_order', 'name']

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} ⬅️ {self.name}"
        return f"{self.icon} {self.name}"


class Product(TimeStampedModel):
    """Digital product or subscription."""
    STOCK_TYPE_CHOICES = (
        ('QUANTITY', 'كمية عددية (Numeric Stock)'),
        ('INDIVIDUAL_ITEMS', 'عناصر وحسابات فردية مستقلة'),
        ('API_CAPACITY', 'مرتبط بمزود خارجي (External API)'),
        ('UNLIMITED', 'غير محدود (Unlimited)'),
    )

    FULFILLMENT_TYPE_CHOICES = (
        ('INVENTORY', 'تسليم فوري من المخزون الداخلي'),
        ('API', 'شراء تلقائي عبر API المزود الخارجي'),
        ('FILE', 'تسليم ملف رقمي'),
        ('MANUAL', 'تنفيذ يدوي من قبل الإدارة'),
    )

    CURRENCY_CHOICES = (
        ('YER', 'ريال يمني (YER)'),
        ('USD', 'دولار أمريكي (USD)'),
    )

    categories = models.ManyToManyField(Category, related_name='products', verbose_name=_('التصنيفات'))
    name = models.CharField(_('اسم المنتج'), max_length=255)
    description = models.TextField(_('وصف المنتج'), blank=True)
    
    base_currency = models.CharField(_('عملة التسعير الأساسية'), max_length=10, choices=CURRENCY_CHOICES, default='YER')
    price = models.DecimalField(_('السعر الأساسي'), max_digits=12, decimal_places=2)
    
    stock_type = models.CharField(_('نوع المخزون'), max_length=20, choices=STOCK_TYPE_CHOICES, default='QUANTITY')
    fulfillment_type = models.CharField(_('نوع التسليم'), max_length=20, choices=FULFILLMENT_TYPE_CHOICES, default='INVENTORY')
    
    stock_quantity = models.PositiveIntegerField(_('الكمية المتاحة (للمخزون العددي)'), default=0)
    low_stock_threshold = models.PositiveIntegerField(_('حد تنبيه نفاد المخزون'), default=5)
    
    requires_customer_input = models.BooleanField(_('يتطلب بيانات إضافية من العميل (مثل ID اللاعب أو الإيميل)'), default=False)
    customer_input_label = models.CharField(_('عنوان الحقل المطلوب من العميل'), max_length=150, blank=True)
    
    image_url = models.URLField(_('رابط الصورة (Cloudinary)'), blank=True)
    image_public_id = models.CharField(_('معرف Cloudinary للصورة'), max_length=150, blank=True)
    
    is_active = models.BooleanField(_('مفعل للبيع'), default=True)
    display_order = models.PositiveIntegerField(_('ترتيب العرض'), default=0)

    class Meta:
        verbose_name = _('منتج رقمي')
        verbose_name_plural = _('المنتجات الرقمية')
        ordering = ['display_order', '-created_at']

    def __str__(self):
        return f"{self.name} ({self.price:,.0f} {self.base_currency})"


class ProductImage(TimeStampedModel):
    """Multiple images for a product stored in Cloudinary."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='gallery_images', verbose_name=_('المنتج'))
    image_url = models.URLField(_('رابط الصورة'))
    public_id = models.CharField(_('معرف الصورة'), max_length=150)
    is_primary = models.BooleanField(_('صورة رئيسية'), default=False)

    class Meta:
        verbose_name = _('صورة منتج')
        verbose_name_plural = _('صور المنتجات')
