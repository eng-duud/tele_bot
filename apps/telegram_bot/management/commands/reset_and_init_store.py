import logging
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import SystemSetting, ExchangeRate
from apps.core.services import SystemSettingService
from apps.users.models import TelegramProfile
from apps.wallet.models import Wallet, WalletTransaction
from apps.orders.models import Order, OrderItem
from apps.fulfillment.models import OrderIssue, FulfillmentTask
from apps.payments.models import PaymentRequest, PaymentMethod
from apps.support.models import SupportTicket, TicketMessage
from apps.notifications.models import RequiredChannel, BroadcastAnnouncement
from apps.notifications.services import ChannelSubscriptionService
from apps.catalog.models import Category, Product
from apps.inventory.models import StockItem
from apps.services_app.models import DigitalService, ServiceRequest
from apps.audit.models import AuditLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clears all old operational data and initializes a clean, production-ready store.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-catalog',
            action='store_true',
            help='Preserve existing products and categories while clearing orders and users',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("⚠️ Starting comprehensive store reset and initialization..."))

        keep_catalog = options.get('keep_catalog', False)

        with transaction.atomic():
            # 1. Clear operational transaction and user data
            self.stdout.write("🧹 1/5 Clearing old orders, payments, and tickets...")
            FulfillmentTask.objects.all().delete()
            OrderIssue.objects.all().delete()
            OrderItem.objects.all().delete()
            Order.objects.all().delete()
            PaymentRequest.objects.all().delete()
            TicketMessage.objects.all().delete()
            SupportTicket.objects.all().delete()
            ServiceRequest.objects.all().delete()
            BroadcastAnnouncement.objects.all().delete()
            AuditLog.objects.all().delete()
            WalletTransaction.objects.all().delete()

            # 2. Reset channels
            self.stdout.write("🧹 2/5 Resetting channels table...")
            RequiredChannel.objects.all().delete()
            ChannelSubscriptionService.clear_cache()

            # 3. Clean catalog if requested
            if not keep_catalog:
                self.stdout.write("🧹 3/5 Resetting test inventory, products and categories...")
                StockItem.objects.all().delete()
                Product.objects.all().delete()
                Category.objects.all().delete()
                DigitalService.objects.all().delete()
                PaymentMethod.objects.all().delete()

            # 4. Clean user profiles (preserve Super Admin)
            self.stdout.write("🧹 4/5 Resetting test user profiles...")
            super_admin_id = getattr(settings, 'SUPER_ADMIN_TELEGRAM_ID', 0)
            if super_admin_id:
                TelegramProfile.objects.exclude(telegram_id=super_admin_id).delete()
                admin_profile, created = TelegramProfile.objects.get_or_create(
                    telegram_id=super_admin_id,
                    defaults={
                        'first_name': 'المدير العام',
                        'is_admin': True,
                        'preferred_currency': 'YER'
                    }
                )
                admin_profile.is_admin = True
                admin_profile.save()
                admin_wallet, _ = Wallet.objects.get_or_create(profile=admin_profile)
                self.stdout.write(self.style.SUCCESS(f"👑 Super Admin profile ready: {super_admin_id}"))
            else:
                TelegramProfile.objects.all().delete()

            # 5. Initialize clean SaaS SystemSettings
            self.stdout.write("⚙️ 5/5 Initializing clean SaaS system settings...")
            SystemSetting.objects.all().delete()
            SystemSettingService.clear_cache()

            defaults = {
                'STORE_NAME': 'متجري الرقمي',
                'BASE_CURRENCY': 'YER',
                'WELCOME_MESSAGE': 'أهلاً بك في متجرنا الرقمي 🛍️✨\nتصفح المنتجات والخدمات المميزة واشحن محفظتك بكل سهولة.',
                'OFFICIAL_CHANNEL_ID': '',
                'OFFICIAL_CHANNEL_TITLE': 'قناة البوت الرسمية',
                'OFFICIAL_CHANNEL_URL': '',
                'OFFICIAL_CHANNEL_MANDATORY': 'true',
                'SUCCESS_CHANNEL_ID': '',
                'SUCCESS_CHANNEL_TITLE': 'قناة التفعيلات المباشرة',
                'SUCCESS_CHANNEL_URL': '',
                'SUCCESS_CHANNEL_ENABLED': 'true',
                'SUCCESS_CHANNEL_MANDATORY': 'true',
                'SUPPORT_CHANNEL_ID': '',
                'SUPPORT_CHANNEL_TITLE': 'قناة / قروب الدعم الفني',
                'ADMIN_CHANNEL_ID': '',
                'ADMIN_CHANNEL_TITLE': 'قروب إشعارات الإدارة',
                'MANDATORY_SUBSCRIPTION_ENABLED': 'true',
                'REFERRAL_BONUS_YER': '50',
                'REFERRAL_ENABLED': 'true',
                'SUPPORT_ENABLED': 'true',
                'BACKUP_AUTO_ENABLED': 'true',
            }

            for k, v in defaults.items():
                SystemSettingService.set_setting(k, str(v), f"إعداد {k} التلقائي")

            # Exchange rate
            ExchangeRate.objects.update_or_create(
                source_currency='USD',
                target_currency='YER',
                defaults={'rate': Decimal('550.00'), 'is_active': True}
            )

            # Starter payment methods
            if not keep_catalog:
                starter_methods = [
                    {
                        'name': 'الكريمي - حاسب / مميز',
                        'icon': '🏦',
                        'account_number': '12345678',
                        'account_name': 'المتجر الرقمي',
                        'instructions': 'أرسل الحوالة عبر تطبيق الكريمي جوال لحسابنا الموضح أعلاه، ثم أرسل صورة السند ورقم الحوالة.',
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
                for pm_data in starter_methods:
                    PaymentMethod.objects.create(**pm_data)

                # Starter categories
                cat_gaming = Category.objects.create(name='🎮 الألعاب وبطاقات الشحن', slug='gaming', icon='🎮', display_order=1)
                Category.objects.create(name='📺 اشتراكات وترفيه', slug='subscriptions', icon='📺', display_order=2)
                Category.objects.create(name='Steam Cards', slug='steam', icon='🔥', parent=cat_gaming, display_order=1)

        self.stdout.write(self.style.SUCCESS("\n✨ تم مسح كافة البيانات السابقة بنجاح وتهيئة المتجر للإنتاج 100%!"))
        self.stdout.write(self.style.SUCCESS("جاهز الآن لتشغيل البوت وإضافة قنواتك مباشرة من بوت الأدمن."))
