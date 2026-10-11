from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from apps.users.models import TelegramProfile
from apps.users.services import ReferralService
from apps.core.services import SystemSettingService

router = Router()

@router.message(F.text.in_(["🤝 الإحالات والأرباح", "🤝 نظام الإحالة", "🤝 الإحالات"]))
@router.callback_query(F.data == "menu_referrals")
async def handle_referrals_menu(event: Message | CallbackQuery, user_profile: TelegramProfile, bot):
    """Display user's unique referral link, statistics, and share buttons."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    is_enabled = await sync_to_async(SystemSettingService.get_bool)('REFERRAL_ENABLED', True)
    if not is_enabled:
        await target.answer("⚠️ نظام الإحالات متوقف مؤقتاً من قبل إدارة المتجر.")
        return

    bonus_yer = await sync_to_async(SystemSettingService.get_decimal)('REFERRAL_BONUS_YER', Decimal('50.00'))
    stats = await sync_to_async(ReferralService.get_referral_stats)(user_profile)

    # Generate personalized referral link
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_profile.telegram_id}"
    store_name = await sync_to_async(SystemSettingService.get_setting)('STORE_NAME', 'المتجر الرقمي')

    share_text = f"انضم إلى {store_name} عبر الرابط التالي واستمتع بأفضل العروض والمنتجات الرقمية والتسليم الفوري:\n{ref_link}"
    import urllib.parse
    encoded_share = urllib.parse.quote(share_text)
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote('أفضل متجر للمنتجات الرقمية ⚡')}"

    from apps.core.services import CurrencyService
    bonus_disp = CurrencyService.format_dual_price(bonus_yer, user_profile.preferred_currency)
    earned_disp = CurrencyService.format_dual_price(stats['total_earned_yer'], user_profile.preferred_currency)

    text = (
        f"🤝 <b>برنامج الإحالة والأرباح</b> 💰\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"شارِك رابطك الخاص مع أصدقائك أو في قنواتك، واحصل على <b>{bonus_disp}</b> تضاف فوراً لمحفظتك عن كل صديق ينضم إلى المتجر!\n\n"
        f"🔗 <b>رابط الإحالة الخاص بك:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"📊 <b>إحصائيات إحالاتك:</b>\n"
        f"👥 عدد الأصدقاء المدعوين: <b>{stats['total_invited']}</b> صديق\n"
        f"💵 إجمالي أرباحك من الإحالات: <b>{earned_disp}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>الأرباح تضاف مباشرة إلى محفظتك في البوت ويمكنك استخدامها لشراء أي بطاقة أو خدمة فوراً!</i>"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 مشاركة الرابط مع الأصدقاء", url=share_url),
        ],
        [
            InlineKeyboardButton(text="💰 عرض رصيد المحفظة", callback_data="menu_wallet"),
            InlineKeyboardButton(text="🏠 الرئيسية", callback_data="menu_home"),
        ]
    ])

    await target.answer(text, reply_markup=markup, parse_mode='HTML')
