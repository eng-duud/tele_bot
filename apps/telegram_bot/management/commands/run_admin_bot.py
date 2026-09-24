import asyncio
import logging
from django.core.management.base import BaseCommand
from aiogram import Dispatcher
from apps.telegram_bot.common.bot_instances import get_admin_bot
from apps.telegram_bot.common.middlewares import UserAutoRegisterMiddleware
from apps.telegram_bot.admin import handlers as admin_handlers
from apps.telegram_bot.admin_group import handlers as admin_group_handlers

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run the Admin Telegram Bot via long polling'

    def handle(self, *args, **options):
        bot = get_admin_bot()
        if not bot:
            self.stderr.write(self.style.ERROR(
                "ADMIN_BOT_TOKEN is not configured in .env! Please set your admin bot token from @BotFather."
            ))
            return

        dp = Dispatcher()
        dp.message.middleware(UserAutoRegisterMiddleware())
        dp.callback_query.middleware(UserAutoRegisterMiddleware())

        # Include Admin routers
        dp.include_router(admin_handlers.router)
        dp.include_router(admin_group_handlers.router)

        self.stdout.write(self.style.SUCCESS("👑 Admin Bot started polling successfully..."))

        async def main():
            await dp.start_polling(bot, drop_pending_updates=True)

        try:
            asyncio.run(main())
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write(self.style.WARNING("Admin Bot stopped."))
