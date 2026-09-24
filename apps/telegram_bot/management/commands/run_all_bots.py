import asyncio
import logging
from django.core.management.base import BaseCommand
from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ErrorEvent
from apps.core.models import ExchangeRate
from apps.telegram_bot.common.bot_instances import get_customer_bot, get_admin_bot
from apps.telegram_bot.common.middlewares import (
    UserAutoRegisterMiddleware, 
    MandatorySubscriptionMiddleware,
    AdminAuthMiddleware,
    CallbackRateLimitMiddleware,
)
from apps.telegram_bot.customer.handlers import start, shop, wallet, orders, services, settings
from apps.telegram_bot.admin import handlers as admin_handlers
from apps.telegram_bot.admin_group import handlers as admin_group_handlers

logger = logging.getLogger(__name__)

async def global_error_handler(event: ErrorEvent):
    """Catch unhandled errors, especially benign TelegramBadRequest (e.g. message is not modified)."""
    exception = event.exception
    if isinstance(exception, TelegramBadRequest):
        if "message is not modified" in str(exception).lower():
            if event.update and event.update.callback_query:
                try:
                    await event.update.callback_query.answer("📊 البيانات محدثة بالفعل")
                except Exception:
                    pass
            return True

    logger.error(f"Error processing update: {exception}", exc_info=exception)
    return True

class Command(BaseCommand):
    help = 'Run both Customer Bot and Admin Bot concurrently in one process'

    def handle(self, *args, **options):
        # Preload active exchange rate synchronously into in-memory cache
        current_rate = ExchangeRate.get_usd_to_yer_rate()
        self.stdout.write(self.style.NOTICE(f"💵 Active Exchange Rate loaded: 1 USD = {current_rate:,.0f} YER"))

        customer_bot = get_customer_bot()
        admin_bot = get_admin_bot()

        tasks = []

        # Setup Customer Bot Dispatcher
        if customer_bot:
            cust_dp = Dispatcher()
            cust_dp.error.register(global_error_handler)
            cust_dp.message.middleware(UserAutoRegisterMiddleware())
            cust_dp.callback_query.middleware(UserAutoRegisterMiddleware())
            cust_dp.message.middleware(MandatorySubscriptionMiddleware())
            cust_dp.callback_query.middleware(MandatorySubscriptionMiddleware())
            cust_dp.callback_query.middleware(CallbackRateLimitMiddleware())

            cust_dp.include_router(start.router)
            cust_dp.include_router(shop.router)
            cust_dp.include_router(wallet.router)
            cust_dp.include_router(orders.router)
            cust_dp.include_router(services.router)
            cust_dp.include_router(settings.router)

            tasks.append(cust_dp.start_polling(customer_bot, drop_pending_updates=True))
            self.stdout.write(self.style.SUCCESS("🤖 [1/2] Customer Bot dispatcher ready."))
        else:
            self.stdout.write(self.style.WARNING("⚠️ Customer Bot Token not configured in .env"))

        # Setup Admin Bot Dispatcher
        if admin_bot:
            admin_dp = Dispatcher()
            admin_dp.error.register(global_error_handler)
            admin_dp.message.middleware(UserAutoRegisterMiddleware())
            admin_dp.callback_query.middleware(UserAutoRegisterMiddleware())
            admin_dp.message.middleware(AdminAuthMiddleware())
            admin_dp.callback_query.middleware(AdminAuthMiddleware())

            admin_dp.include_router(admin_handlers.router)
            admin_dp.include_router(admin_group_handlers.router)

            tasks.append(admin_dp.start_polling(admin_bot, drop_pending_updates=True))
            self.stdout.write(self.style.SUCCESS("👑 [2/2] Admin Bot dispatcher ready."))
        else:
            self.stdout.write(self.style.WARNING("⚠️ Admin Bot Token not configured in .env"))

        if not tasks:
            self.stderr.write(self.style.ERROR("No active bot tokens found. Please configure your .env file."))
            return

        async def main():
            await asyncio.gather(*tasks)

        self.stdout.write(self.style.SUCCESS("🚀 All configured Telegram bots are now live and polling!"))
        try:
            asyncio.run(main())
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write(self.style.WARNING("Bots polling stopped."))
