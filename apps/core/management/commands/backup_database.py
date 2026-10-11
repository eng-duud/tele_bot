import asyncio
from django.core.management.base import BaseCommand
from apps.core.backup_service import DatabaseBackupService


class Command(BaseCommand):
    help = 'Create a database backup and send it directly to the designated Telegram backup channel or admin'

    def add_arguments(self, parser):
        parser.add_argument(
            '--chat-id',
            type=str,
            default=None,
            help='Override target Telegram channel/chat ID'
        )

    def handle(self, *args, **options):
        chat_id = options.get('chat_id')
        self.stdout.write(self.style.NOTICE("📦 بدء إنشاء النسخة الاحتياطية لقاعدة البيانات وإرسالها..."))

        success, msg = asyncio.run(DatabaseBackupService.send_backup_to_telegram(target_chat_id=chat_id))

        if success:
            self.stdout.write(self.style.SUCCESS(f"✅ {msg}"))
        else:
            self.stdout.write(self.style.ERROR(f"❌ {msg}"))
