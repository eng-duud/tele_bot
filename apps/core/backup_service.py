import io
import gzip
import logging
from datetime import datetime
from typing import Tuple, Dict, Any

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from asgiref.sync import sync_to_async

from aiogram.types import BufferedInputFile
from apps.core.services import SystemSettingService
from apps.telegram_bot.common.bot_instances import get_admin_bot

logger = logging.getLogger(__name__)


class DatabaseBackupService:
    """Service to create and dispatch database backups directly to Telegram."""

    @staticmethod
    def collect_system_stats() -> Dict[str, Any]:
        """Collect live database statistics for the backup report."""
        stats = {
            'users_count': 0,
            'orders_count': 0,
            'inventory_count': 0,
            'payment_requests_count': 0,
        }
        try:
            from apps.users.models import TelegramProfile
            stats['users_count'] = TelegramProfile.objects.count()
        except Exception:
            pass

        try:
            from apps.orders.models import Order
            stats['orders_count'] = Order.objects.count()
        except Exception:
            pass

        try:
            from apps.inventory.models import StockItem
            stats['inventory_count'] = StockItem.objects.count()
        except Exception:
            pass

        try:
            from apps.payments.models import PaymentRequest
            stats['payment_requests_count'] = PaymentRequest.objects.count()
        except Exception:
            pass

        return stats

    @classmethod
    def generate_backup_archive(cls) -> Tuple[bytes, str, Dict[str, Any]]:
        """
        Generate a compressed gzipped JSON database dump.
        Portable across SQLite, Neon Cloud, and Local PostgreSQL.
        """
        now_str = timezone.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f"telebot_backup_{now_str}.json.gz"

        buffer = io.StringIO()
        call_command(
            'dumpdata',
            natural_foreign=True,
            natural_primary=True,
            exclude=['contenttypes', 'auth.permission'],
            indent=2,
            stdout=buffer
        )

        raw_data = buffer.getvalue().encode('utf-8')

        # Compress with gzip
        compressed_buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed_buffer, mode='wb', compresslevel=9) as gz:
            gz.write(raw_data)

        compressed_bytes = compressed_buffer.getvalue()
        stats = cls.collect_system_stats()

        return compressed_bytes, filename, stats

    @classmethod
    async def send_backup_to_telegram(cls, target_chat_id: str = None, fallback_chat_id: str = None) -> Tuple[bool, str]:
        """
        Create backup and send it as a document to the designated Telegram backup channel or admin.
        """
        # Resolve destination
        if not target_chat_id:
            def _get_target_backup_channel():
                from apps.notifications.models import RequiredChannel
                ch = RequiredChannel.objects.filter(channel_type='BACKUP', is_active=True).first()
                return ch.channel_id if ch else None
            target_chat_id = await sync_to_async(_get_target_backup_channel)()

        if not target_chat_id:
            target_chat_id = await sync_to_async(SystemSettingService.get_setting)('BACKUP_CHANNEL_ID', '')
        
        if not target_chat_id:
            target_chat_id = await sync_to_async(SystemSettingService.get_setting)('ADMIN_LOG_CHANNEL_ID', '')

        if not target_chat_id and fallback_chat_id:
            target_chat_id = str(fallback_chat_id)

        if not target_chat_id:
            super_admin = getattr(settings, 'SUPER_ADMIN_TELEGRAM_ID', 0)
            if super_admin:
                target_chat_id = str(super_admin)

        if not target_chat_id:
            return False, "لم يتم تحديد معرف قناة النسخ الاحتياطي أو حساب المدير العام."

        bot = get_admin_bot()
        if not bot:
            return False, "تعذر تهيئة بوت الإدارة لإرسال النسخة."

        try:
            # Generate archive in thread
            compressed_bytes, filename, stats = await sync_to_async(cls.generate_backup_archive)()
            size_kb = len(compressed_bytes) / 1024
            time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            caption = (
                f"📦 <b>نسخة احتياطية لقاعدة البيانات (Database Backup)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📅 <b>التاريخ والوقت:</b> <code>{time_now}</code>\n"
                f"💾 <b>حجم الملف:</b> <b>{size_kb:,.1f} KB</b>\n"
                f"📊 <b>إحصائيات النظام المحفوظة:</b>\n"
                f" • 👤 المستخدمين: <b>{stats['users_count']}</b>\n"
                f" • 🛍️ إجمالي الطلبات: <b>{stats['orders_count']}</b>\n"
                f" • 💳 طلبات الشحن: <b>{stats['payment_requests_count']}</b>\n"
                f" • 🔐 بطاقات المخزون: <b>{stats['inventory_count']}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔐 <i>ملاحظة هامة: بيانات المخزون والأكواد مشفرة بمفتاح DATA_ENCRYPTION_KEY المعتمد في السيرفر.</i>"
            )

            input_file = BufferedInputFile(compressed_bytes, filename=filename)

            # Send document
            await bot.send_document(
                chat_id=target_chat_id,
                document=input_file,
                caption=caption,
                parse_mode='HTML'
            )

            # Update last backup timestamp
            await sync_to_async(SystemSettingService.set_setting)(
                'LAST_BACKUP_TIME',
                time_now,
                "تاريخ ووقت آخر عملية نسخ احتياطي ناجحة"
            )

            logger.info(f"✅ Backup successfully created and sent to {target_chat_id} ({size_kb:.1f} KB).")
            return True, f"تم إنشاء وإرسال النسخة الاحتياطية بنجاح إلى: <code>{target_chat_id}</code> بحجم {size_kb:,.1f} KB"

        except Exception as e:
            err_str = str(e)
            if "chat not found" in err_str.lower():
                msg = f"المحادثة أو القناة ({target_chat_id}) غير موجودة أو لم تقم بمراسلة البوت بعد (chat not found). أرسل /start لبوت الإدارة أو اربط القناة أولاً."
            elif "blocked by the user" in err_str.lower():
                msg = f"البوت محظور من قبل المستخدم ({target_chat_id})."
            else:
                msg = f"فشل إرسال النسخة الاحتياطية: {err_str}"
            logger.error(f"❌ Failed to dispatch database backup: {err_str}")
            return False, msg
