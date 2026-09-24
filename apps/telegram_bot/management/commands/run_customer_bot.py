import asyncio
import logging
from django.core.management.base import BaseCommand
from aiogram import Dispatcher
from apps.telegram_bot.common.bot_instances import get_customer_bot
from apps.telegram_bot.common.middlewares import UserAutoRegisterMiddleware, MandatorySubscriptionMiddleware
from apps.telegram_bot.customer.handlers import start, shop, wallet, orders, services, settings
from apps.telegram_bot.admin_group import handlers as admin_group_handlers

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run the Customer Telegram Bot via long polling'

    def handle(self, *args, **options):
        bot = get_customer_bot()
        if not bot:
            self.stderr.write(self.style.ERROR(
                "CUSTOMER_BOT_TOKEN is not configured in .env! Please set your bot token from @BotFather."
            ))
            return

        dp = Dispatcher()
        
        # Attach Middlewares
        dp.message.middleware(UserAutoRegisterMiddleware())
        dp.callback_query.middleware(UserAutoRegisterMiddleware())
        dp.message.middleware(MandatorySubscriptionMiddleware())
        dp.callback_query.middleware(MandatorySubscriptionMiddleware())

        # Include Routers
        dp.include_router(start.router)
        dp.include_router(shop.router)
        dp.include_router(wallet.router)
        dp.include_router(orders.router)
        dp.include_router(services.router)
        dp.include_router(settings.router)

        self.stdout.write(self.style.SUCCESS("🤖 Customer Bot started polling successfully..."))

        async def main():
            await dp.start_polling(bot, drop_pending_updates=True)

        try:
            asyncio.run(main())
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write(self.style.WARNING("Customer Bot stopped."))
