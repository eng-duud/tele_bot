from django.core.management.base import BaseCommand
from django.db import transaction
from apps.orders.models import Order, OrderItem
from apps.payments.models import PaymentRequest
from apps.inventory.models import StockItem, RestockSubscription
from apps.fulfillment.models import FulfillmentTask, OrderIssue
from apps.services_app.models import ServiceRequest
from apps.notifications.models import RequiredChannel, BroadcastAnnouncement
from apps.wallet.models import Wallet, WalletTransaction
from apps.core.models import SystemSetting, ExchangeRate
from apps.core.services import SystemSettingService
from apps.notifications.services import ChannelSubscriptionService


class Command(BaseCommand):
    help = 'Clean and reset all database records to a fresh, white-label, client-ready SaaS state'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-products',
            action='store_true',
            help='Keep catalog products and categories intact while clearing orders, channels, and transactions'
        )

    def handle(self, *args, **options):
        keep_products = options.get('keep_products', False)
        self.stdout.write(self.style.WARNING("🧹 جاري تصفير وتنظيف بيانات النظام لتسليمه للعميل كنسخة SaaS نظيفة..."))

        with transaction.atomic():
            # 1. Clear orders & fulfillment
            OrderIssue.objects.all().delete()
            FulfillmentTask.objects.all().delete()
            OrderItem.objects.all().delete()
            Order.objects.all().delete()

            # 2. Clear payments
            PaymentRequest.objects.all().delete()

            # 3. Clear wallet transactions and zero out balances
            WalletTransaction.objects.all().delete()
            Wallet.objects.update(balance_yer=0, is_locked=False)

            # 4. Clear stock items (encrypted inventory cards) and restock waitlists
            StockItem.objects.all().delete()
            RestockSubscription.objects.all().delete()

            # 5. Clear service requests
            ServiceRequest.objects.all().delete()

            # 6. Clear broadcasts
            BroadcastAnnouncement.objects.all().delete()

            # 7. Clear old channels
            RequiredChannel.objects.all().delete()
            ChannelSubscriptionService.clear_cache()

            # 8. Reset SystemSettings to clean SaaS defaults
            clean_settings = {
                'STORE_NAME': 'متجري الرقمي',
                'SUPPORT_USERNAME': '',
                'SUPPORT_ENABLED': 'true',
                'REFERRAL_BONUS_YER': '50',
                'REFERRAL_ENABLED': 'true',
                'WELCOME_MESSAGE': 'أهلاً بك في متجرنا الرقمي 🛍️✨\nتصفح المنتجات والخدمات المميزة واشحن محفظتك بكل سهولة.',
                'BASE_CURRENCY': 'YER',
                'SUCCESS_CHANNEL_ID': '',
                'SUCCESS_CHANNEL_URL': '',
                'SUCCESS_CHANNEL_TITLE': 'قناة التفعيلات المباشرة',
                'SUCCESS_CHANNEL_ENABLED': 'false',
                'MANDATORY_SUBSCRIPTION_ENABLED': 'false',
                'REQUIRED_CHANNEL_ID': '',
                'REQUIRED_CHANNEL_URL': '',
                'REQUIRED_CHANNEL_TITLE': 'قناة المتجر الرسمية',
                'BACKUP_CHANNEL_ID': '',
                'BACKUP_AUTO_ENABLED': 'true',
                'LAST_BACKUP_TIME': '',
            }
            for k, v in clean_settings.items():
                SystemSetting.objects.update_or_create(
                    key=k,
                    defaults={'value': v, 'description': f'إعداد {k} الافتراضي للمتجر'}
                )
            SystemSettingService.clear_cache()

            # 9. Optionally clear products/categories if not requested to keep
            if not keep_products:
                from apps.catalog.models import Product, Category
                from apps.services_app.models import DigitalService
                Product.objects.all().delete()
                Category.objects.all().delete()
                DigitalService.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("✨ تم تصفير وتنظيف جميع البيانات بنجاح!"))
        self.stdout.write(self.style.SUCCESS("🎯 النسخة الآن بيضاء 100% (Clean White-Label SaaS) وجاهزة لتسليمها لأي عميل ليعبئ بياناته وقنواته ومنتجاته بنفسه."))
