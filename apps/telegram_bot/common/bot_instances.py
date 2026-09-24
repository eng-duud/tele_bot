import os
from typing import Optional
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from django.conf import settings

_customer_bot: Optional[Bot] = None
_admin_bot: Optional[Bot] = None

def get_customer_bot() -> Optional[Bot]:
    """Retrieve singleton instance of Customer Bot."""
    global _customer_bot
    token = getattr(settings, 'CUSTOMER_BOT_TOKEN', '') or os.getenv('CUSTOMER_BOT_TOKEN', '')
    if not token or token == 'YOUR_CUSTOMER_BOT_TOKEN_HERE':
        return None
    if _customer_bot is None:
        _customer_bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    return _customer_bot

def get_admin_bot() -> Optional[Bot]:
    """Retrieve singleton instance of Admin Bot."""
    global _admin_bot
    token = getattr(settings, 'ADMIN_BOT_TOKEN', '') or os.getenv('ADMIN_BOT_TOKEN', '')
    if not token or token == 'YOUR_ADMIN_BOT_TOKEN_HERE':
        return None
    if _admin_bot is None:
        _admin_bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    return _admin_bot
