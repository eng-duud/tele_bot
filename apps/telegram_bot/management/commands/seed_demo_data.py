from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.core.models import ExchangeRate
from apps.payments.models import PaymentMethod
from apps.catalog.models import Category, Product
from apps.inventory.services import InventoryService
from apps.providers.models import ApiProvider, ProviderProductMapping
from apps.services_app.models import DigitalService

class Command(BaseCommand):
    help = 'Seeds realistic Yemeni store categories, products, encrypted stock, and payment methods'

    def handle(self, *args, **options):
        self.stdout.write("🌱 Seeding realistic demo data...")

        # 1. Exchange Rate
        rate_obj, _ = ExchangeRate.objects.get_or_create(
            source_currency='USD',
            target_currency='YER',
            defaults={'rate': Decimal('550.00'), 'is_active': True}
        )
        self.stdout.write(f"✅ Exchange rate: 1 USD = {rate_obj.rate} YER")

        # 2. Payment Methods
        methods = [
            {
                'name': 'الكريمي - حاسب / مميز',
                'icon': '🏦',
                'account_number': '12345678',
                'account_name': 'المتجر الرقمي للخدمات',
                'instructions': 'أرسل الحوالة عبر تطبيق الكريمي جوال (خدمة حاسب أو حوالة مميزة) للرقم أعلاه، ثم أرسل صورة السند ورقم الحوالة.',
                'requires_proof_image': True,
                'requires_tx_number': True,
                'min_deposit_yer': Decimal('1000'),
                'max_deposit_yer': Decimal('500000'),
                'is_active': True,
                'display_order': 1
            },
            {
                'name': 'محفظة جيب - Jeeb',
                'icon': '📱',
                'account_number': '777000111',
                'account_name': 'وكيل المتجر المعتمد',
                'instructions': 'قم بالتحويل عبر تطبيق محفظة جيب للرقم أعلاه، ثم أرفق لقطة شاشة للإشعار.',
                'requires_proof_image': True,
                'requires_tx_number': False,
                'min_deposit_yer': Decimal('500'),
                'max_deposit_yer': Decimal('300000'),
                'is_active': True,
                'display_order': 2
            },
            {
                'name': 'محفظة ون كاش - OneCash',
                'icon': '💳',
                'account_number': '770000222',
                'account_name': 'المتجر الرقمي',
                'instructions': 'أرسل المبلغ لرقم ون كاش الموضح، ثم اكتب رقم العملية وأرسل الإشعار.',
                'requires_proof_image': True,
                'requires_tx_number': True,
                'min_deposit_yer': Decimal('1000'),
                'max_deposit_yer': Decimal('400000'),
                'is_active': True,
                'display_order': 3
            }
        ]

        for m_data in methods:
            pm, _ = PaymentMethod.objects.update_or_create(
                name=m_data['name'],
                defaults=m_data
            )
            self.stdout.write(f"✅ Payment Method: {pm.name}")

        # 3. Categories
        cat_gaming, _ = Category.objects.get_or_create(
            slug='gaming',
            defaults={'name': '🎮 الألعاب وبطاقات الشحن', 'icon': '🎮', 'display_order': 1}
        )
        cat_steam, _ = Category.objects.get_or_create(
            slug='steam',
            defaults={'name': 'Steam Cards', 'icon': '🔥', 'parent': cat_gaming, 'display_order': 1}
        )
        cat_playstation, _ = Category.objects.get_or_create(
            slug='playstation',
            defaults={'name': 'PlayStation Store', 'icon': '🎯', 'parent': cat_gaming, 'display_order': 2}
        )

        cat_subs, _ = Category.objects.get_or_create(
            slug='subscriptions',
            defaults={'name': '📺 اشتراكات وترفيه', 'icon': '📺', 'display_order': 2}
        )
        self.stdout.write("✅ Categories created.")

        # 4. Products & Encrypted Stock
        # Netflix Product
        p_netflix, _ = Product.objects.update_or_create(
            name='اشتراك Netflix 4K UHD (شهر كامل)',
            defaults={
                'description': 'حساب نتفلكس بريميوم رسمي 4K شاشة خاصة بملف شخصي مضمون لمدة 30 يوماً.',
                'base_currency': 'YER',
                'price': Decimal('5500.00'),
                'stock_type': 'INDIVIDUAL_ITEMS',
                'fulfillment_type': 'INVENTORY',
                'is_active': True
            }
        )
        p_netflix.categories.add(cat_subs)

        # Seed encrypted Netflix stock
        netflix_accounts = [
            "Email: user1_netflix@streamvip.com | Pass: NetVip@2026 | Profile: 1 (PIN: 1122)",
            "Email: user2_netflix@streamvip.com | Pass: NetVip@8899 | Profile: 3 (PIN: 4455)",
            "Email: user3_netflix@streamvip.com | Pass: NetVip@7733 | Profile: 2 (PIN: 9900)"
        ]
        InventoryService.bulk_add_individual_items(p_netflix, netflix_accounts)
        self.stdout.write(f"✅ Product & Encrypted Stock added: {p_netflix.name}")

        # PSN Card Product
        p_psn, _ = Product.objects.update_or_create(
            name='بطاقة بلايستيشن 10$ سعودي (كود فوري)',
            defaults={
                'description': 'كود رقمي أصلي لشحن رصيد ستور بلايستيشن الحساب السعودي بقيمة 10 دولار.',
                'base_currency': 'YER',
                'price': Decimal('5500.00'),
                'stock_type': 'INDIVIDUAL_ITEMS',
                'fulfillment_type': 'INVENTORY',
                'is_active': True
            }
        )
        p_psn.categories.add(cat_playstation)
        psn_codes = [
            "PSN-KSA-9482-1048-5921",
            "PSN-KSA-7741-2950-1094"
        ]
        InventoryService.bulk_add_individual_items(p_psn, psn_codes)
        self.stdout.write(f"✅ Product & Encrypted Stock added: {p_psn.name}")

        # External Provider Product (PUBG Mobile via Mock Provider)
        mock_provider, _ = ApiProvider.objects.get_or_create(
            provider_code='MOCK_PROVIDER',
            defaults={
                'name': 'المزود التجريبي (Mock API)',
                'provider_type': 'MOCK',
                'is_active': True
            }
        )

        p_pubg, _ = Product.objects.update_or_create(
            name='شحن شدات ببجي 60 UC (شحن فوري بالـ ID)',
            defaults={
                'description': 'شحن تلقائي فوري وسريع لشدات ببجي موبايل عن طريق ID الحساب مباشرة.',
                'base_currency': 'YER',
                'price': Decimal('1100.00'),
                'stock_type': 'API_CAPACITY',
                'fulfillment_type': 'API',
                'requires_customer_input': True,
                'customer_input_label': 'معرف اللاعب (Player ID)',
                'is_active': True
            }
        )
        p_pubg.categories.add(cat_gaming)

        ProviderProductMapping.objects.update_or_create(
            product=p_pubg,
            defaults={
                'provider': mock_provider,
                'external_service_id': 'PUBG_60_UC'
            }
        )
        self.stdout.write(f"✅ API Provider Product mapped: {p_pubg.name}")

        # 5. Digital Services
        DigitalService.objects.update_or_create(
            name='تصميم شعار أو بنر إعلاني مخصص',
            defaults={
                'description': 'تصميم هوية بصرية أو بنر إعلاني احترافي لمتجرك أو قناتك وفقاً لطلبك.',
                'service_type': 'CUSTOM',
                'instructions': 'يرجى وصف فكرة التصميم والألوان المفضلة والنصوص المراد كتابتها.',
                'is_active': True
            }
        )

        DigitalService.objects.update_or_create(
            name='تثبيت وإعداد بوت تليجرام على سيرفر VPS',
            defaults={
                'description': 'تثبيت بيئة بايثون وربط قواعد البيانات وتشغيل البوت كخدمة systemd تعمل على مدار 24 ساعة.',
                'service_type': 'FIXED',
                'price_yer': Decimal('16500.00'),
                'instructions': 'يرجى إرسال بيانات السيرفر (IP, Root password).',
                'is_active': True
            }
        )
        self.stdout.write("✅ Digital Services created.")

        self.stdout.write(self.style.SUCCESS("\n🎉 Demo data successfully seeded! The store is ready to serve customers."))
