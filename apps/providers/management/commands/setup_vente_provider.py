import os
from django.core.management.base import BaseCommand
from apps.providers.models import ApiProvider
from apps.providers.vente_provider import VenteBotProvider

class Command(BaseCommand):
    help = 'Setup and test Vente Telegram Bot Railway API Provider'

    def add_arguments(self, parser):
        parser.add_argument('--api-key', type=str, default='', help='Vente API Key (or set VENTE_API_KEY in .env)')
        parser.add_argument('--base-url', type=str, default='', help='Vente Base URL (or set VENTE_BASE_URL in .env)')

    def handle(self, *args, **options):
        base_url = (
            options.get('base_url') or 
            os.getenv("VENTE_BASE_URL") or 
            "https://ventetelegrambotrailway-production.up.railway.app"
        ).rstrip('/')

        # Check existing provider or env for api key
        existing_provider = ApiProvider.objects.filter(provider_code='VENTE_BOT').first()
        api_key = (
            options.get('api_key') or 
            os.getenv("VENTE_API_KEY") or 
            (existing_provider.get_api_key() if existing_provider else "")
        )

        if not api_key:
            self.stdout.write(self.style.ERROR("❌ يرجى تمرير مفتاح الـ API عبر --api-key أو ضبط VENTE_API_KEY في ملف .env"))
            return

        self.stdout.write(self.style.NOTICE("⚙️ إعداد وتفعيل مزود Vente Telegram Bot في النظام..."))

        provider, created = ApiProvider.objects.get_or_create(
            provider_code='VENTE_BOT',
            defaults={
                'name': 'Vente Telegram Bot',
                'provider_type': 'VENTE_BOT',
                'base_url': base_url,
                'is_active': True,
            }
        )
        provider.base_url = base_url
        provider.provider_type = 'VENTE_BOT'
        provider.set_api_key(api_key)
        provider.is_active = True
        provider.save()

        action_msg = "تم إنشاء المزود جديداً" if created else "تم تحديث بيانات المزود"
        self.stdout.write(self.style.SUCCESS(f"✅ {action_msg} بنجاح: {provider.name} (رمز: {provider.provider_code})"))

        # Test Adapter
        self.stdout.write(self.style.NOTICE("🔍 جاري اختبار الاتصال وفحص الرصيد لدى المزود..."))
        adapter = VenteBotProvider(api_key=api_key, base_url=base_url)

        try:
            bal = adapter.get_balance()
            self.stdout.write(self.style.SUCCESS(f"💰 رصيد المحفظة لدى المزود: {bal}"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️ تعذر قراءة الرصيد: {e}"))

        self.stdout.write(self.style.NOTICE("📦 جاري فحص الخدمات المتاحة لدى المزود..."))
        try:
            services = adapter.fetch_available_services()
            if services:
                self.stdout.write(self.style.SUCCESS(f"✅ تم العثور على {len(services)} خدمة/منتج لدى المزود!"))
                for s in services[:10]:
                    s_id = s.get('id') or s.get('service') or s.get('product_id')
                    s_name = s.get('name') or s.get('title') or s.get('service_name')
                    price = s.get('price') or s.get('rate') or s.get('cost')
                    self.stdout.write(f"   🔹 ID: {s_id} | {s_name} | السعر: {price}")
            else:
                self.stdout.write(self.style.WARNING("⚠️ لم يتم استرجاع قائمة الخدمات تلقائياً (قد تتطلب مساراً مخصصاً)."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️ خطأ أثناء جلب الخدمات: {e}"))

        self.stdout.write(self.style.SUCCESS("\n🎉 مزود Vente مربوط وجاهز للعمل مع منتجات الـ API!"))
