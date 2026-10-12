import asyncio
import logging
from django.core.management.base import BaseCommand
from django.db import InterfaceError, OperationalError
from asgiref.sync import sync_to_async
from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ErrorEvent
from apps.telegram_bot.common.bot_instances import get_admin_bot
from apps.telegram_bot.common.middlewares import (
    DatabaseConnectionMiddleware,
    UserAutoRegisterMiddleware,
    AdminAuthMiddleware,
    force_close_db_connections,
)
from apps.telegram_bot.admin import handlers as admin_handlers
from apps.telegram_bot.admin_group import handlers as admin_group_handlers

logger = logging.getLogger(__name__)

async def global_error_handler(event: ErrorEvent):
    """Catch unhandled errors and handle dropped DB connections gracefully."""
    exception = event.exception
    if isinstance(exception, (OperationalError, InterfaceError)):
        logger.warning(f"Database connection error in global_error_handler ({exception}). Resetting connections...")
        await sync_to_async(force_close_db_connections)()
        return True

    if isinstance(exception, TelegramBadRequest):
        msg = str(exception).lower()
        if "query is too old" in msg or "message is not modified" in msg:
            if event.update and event.update.callback_query:
                try:
                    await event.update.callback_query.answer()
                except Exception:
                    pass
            return True

    logger.error(f"Error processing update: {exception}", exc_info=exception)
    return True

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
        dp.update.outer_middleware(DatabaseConnectionMiddleware())
        dp.error.register(global_error_handler)
        dp.message.middleware(UserAutoRegisterMiddleware())
        dp.callback_query.middleware(UserAutoRegisterMiddleware())
        dp.message.middleware(AdminAuthMiddleware())
        dp.callback_query.middleware(AdminAuthMiddleware())

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
