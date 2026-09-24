import logging
from typing import Callable, Dict, Any, Awaitable, Tuple
from django.conf import settings
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from apps.users.models import TelegramProfile
from apps.wallet.models import Wallet
from apps.users.services import UserService, AdminAuthService
from apps.wallet.services import WalletService
from apps.notifications.services import ChannelSubscriptionService

import time

logger = logging.getLogger(__name__)

# Fast in-memory user cache: telegram_id -> (profile, timestamp)
_USER_CACHE: Dict[int, Tuple[TelegramProfile, float]] = {}
CACHE_TTL = 30.0  # 30 seconds for user profile registration check

class UserAutoRegisterMiddleware(BaseMiddleware):
    """Automatically synchronizes Telegram users with the Django backend and provides fresh wallet state."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user and not user.is_bot:
            now = time.time()
            if len(_USER_CACHE) > 5000:
                _USER_CACHE.clear()

            cached = _USER_CACHE.get(user.id)
            if cached and (now - cached[1] < CACHE_TTL):
                profile = cached[0]
            else:
                profile, _ = await sync_to_async(UserService.get_or_create_user)(
                    telegram_id=user.id,
                    username=user.username or "",
                    first_name=user.first_name or "",
                    last_name=user.last_name or ""
                )
                _USER_CACHE[user.id] = (profile, now)

            # Always retrieve fresh wallet so balance updates are instantaneous
            wallet = await sync_to_async(WalletService.get_or_create_wallet)(profile)

            data["user_profile"] = profile
            data["user_wallet"] = wallet

        return await handler(event, data)


class AdminAuthMiddleware(BaseMiddleware):
    """Enforces strict RBAC at the dispatcher root, allowing ONLY verified staff/admins to operate Admin Bot."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if not user or user.is_bot:
            return await handler(event, data)

        is_admin = await sync_to_async(AdminAuthService.is_admin)(user.id)
        if not is_admin:
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ عذراً، هذا البوت مخصص للإدارة والمشرفين فقط.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⛔ *عذراً، هذا البوت مخصص للمشرفين وإدارة المتجر فقط.*", parse_mode='Markdown')
            return

        return await handler(event, data)


class MandatorySubscriptionMiddleware(BaseMiddleware):
    """Enforces mandatory channel membership before accessing store services."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        bot = data.get("bot")

        # Skip checks for system bots or missing users
        if not user or user.is_bot or not bot:
            return await handler(event, data)

        # Allow super admin exemption
        super_admin_id = getattr(settings, 'SUPER_ADMIN_TELEGRAM_ID', 0)
        if super_admin_id and user.id == super_admin_id:
            return await handler(event, data)

        # Allow /start and check callbacks so user can verify subscription
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data and event.data.startswith("check_sub"):
            return await handler(event, data)

        # Check required channels
        missing_channels = await ChannelSubscriptionService.get_missing_channels(bot, user.id)
        if missing_channels:
            keyboard_buttons = []
            for ch in missing_channels:
                link = ch.invite_link or (f"https://t.me/{str(ch.channel_id).lstrip('@')}" if str(ch.channel_id).startswith('@') else "")
                keyboard_buttons.append([InlineKeyboardButton(text=f"📢 {ch.channel_title}", url=link)])
            keyboard_buttons.append([InlineKeyboardButton(text="🔄 التحقق من الاشتراك", callback_data="check_sub")])

            channel_word = "القناة التالية" if len(missing_channels) == 1 else "القنوات التالية"
            text = (
                f"⚠️ <b>تنبيه: اشتراك إجباري</b>\n\n"
                f"عزيزي العميل، لاستخدام المتجر وشراء المنتجات وشحن الرصيد، "
                f"يرجى الاشتراك في {channel_word} أولاً ثم النقر على زر <b>[🔄 التحقق من الاشتراك]</b> أدناه:"
            )
            markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

            if isinstance(event, CallbackQuery):
                await event.answer("⚠️ يرجى الاشتراك في القناة المطلوبة أولاً!", show_alert=True)
                if event.message:
                    try:
                        await event.message.answer(text, reply_markup=markup, parse_mode='HTML')
                    except Exception:
                        await event.message.answer(text, reply_markup=markup)
            elif isinstance(event, Message):
                try:
                    await event.answer(text, reply_markup=markup, parse_mode='HTML')
                except Exception:
                    await event.answer(text, reply_markup=markup)

            return  # Block execution of handler

        return await handler(event, data)
