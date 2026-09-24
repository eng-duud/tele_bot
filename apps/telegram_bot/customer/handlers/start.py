from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async
from apps.users.models import TelegramProfile
from apps.wallet.models import Wallet
from apps.core.services import CurrencyService
from apps.core.utils import escape_md
from apps.telegram_bot.common.keyboards import get_customer_main_menu, get_settings_keyboard
from apps.notifications.services import ChannelSubscriptionService

router = Router()

@router.message(CommandStart())
async def handle_start(message: Message, user_profile: TelegramProfile, user_wallet: Wallet, bot, state: FSMContext):
    """Handle /start command with subscription check and welcome presentation."""
    await state.clear()
    clean_name = escape_md(user_profile.full_name)

    # Check mandatory channels
    missing = await ChannelSubscriptionService.get_missing_channels(bot, message.from_user.id)
    if missing:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        import html
        buttons = []
        for ch in missing:
            link = ch.invite_link or (f"https://t.me/{str(ch.channel_id).lstrip('@')}" if str(ch.channel_id).startswith('@') else "")
            buttons.append([InlineKeyboardButton(text=f"📢 {ch.channel_title}", url=link)])
        buttons.append([InlineKeyboardButton(text="🔄 التحقق من الاشتراك", callback_data="check_sub")])

        u_name = html.escape(user_profile.full_name or "عزيزي العميل")
        channel_word = "القناة التالية" if len(missing) == 1 else "القنوات التالية"
        sub_text = (
            f"👋 مرحباً بك <b>{u_name}</b> في متجرنا الرقمي! 🌟\n\n"
            f"⚠️ <b>تنبيه: اشتراك إجباري</b>\n"
            f"للبدء في استخدام البوت وتصفح الأقسام والشراء، "
            f"يرجى الاشتراك في {channel_word} أولاً ثم الضغط على زر <b>[🔄 التحقق من الاشتراك]</b> أدناه:"
        )

        await message.answer(
            sub_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode='HTML'
        )
        return

    yer_bal = user_wallet.balance_yer
    usd_bal = await sync_to_async(CurrencyService.convert)(yer_bal, from_curr='YER', to_curr='USD')

    welcome_text = (
        f"أهلاً بك يا *{clean_name}* في منصة المتجر الرقمي 🛍️✨\n\n"
        f"💰 *رصيد محفظتك الحالي:*\n"
        f"🇾🇪 `{yer_bal:,.0f} YER`\n"
        f"🇺🇸 `${usd_bal:,.2f} USD`\n\n"
        "استخدم القائمة أدناه لتصفح الأقسام والمنتجات والخدمات وشحن رصيدك بكل سهولة:"
    )

    await message.answer(
        welcome_text,
        reply_markup=get_customer_main_menu(),
        parse_mode='Markdown'
    )


@router.callback_query(F.data == "check_sub")
async def handle_check_subscription(callback: CallbackQuery, user_profile: TelegramProfile, user_wallet: Wallet, bot):
    """Verify subscription on demand button click."""
    missing = await ChannelSubscriptionService.get_missing_channels(bot, callback.from_user.id)
    if missing:
        await callback.answer("❌ لم تقم بالاشتراك في القناة المطلوبة بعد! يرجى الاشتراك أولاً ثم الضغط مجدداً.", show_alert=True)
        return

    await callback.answer("✅ تم التحقق من الاشتراك بنجاح! أهلاً بك في المتجر.", show_alert=False)
    await callback.message.delete()
    
    yer_bal = user_wallet.balance_yer
    clean_name = escape_md(user_profile.full_name)
    welcome_text = (
        f"مرحباً بك مجدداً *{clean_name}*! تم تأكيد اشتراكك بنجاح. 🎉\n\n"
        f"💰 رصيدك: *{yer_bal:,.0f} YER*\n"
        "يمكنك الآن تصفح المتجر وشراء الخدمات بحرية."
    )
    await callback.message.answer(welcome_text, reply_markup=get_customer_main_menu(), parse_mode='Markdown')


def get_user_account_stats(user_profile: TelegramProfile) -> dict:
    """Calculate total purchased products and total amount spent in YER."""
    from decimal import Decimal
    from django.db.models import Sum
    from apps.orders.models import Order, OrderItem

    successful_orders = Order.objects.filter(
        user=user_profile, 
        status__in=['COMPLETED', 'PROCESSING']
    )
    
    total_spent = successful_orders.aggregate(total=Sum('total_amount_yer'))['total'] or Decimal('0.00')
    orders_count = successful_orders.count()
    
    total_items = OrderItem.objects.filter(
        order__in=successful_orders
    ).aggregate(total=Sum('quantity'))['total'] or orders_count

    return {
        'total_spent_yer': total_spent,
        'orders_count': orders_count,
        'total_items_count': total_items,
    }


@router.message(F.text == "👤 حسابي")
@router.callback_query(F.data == "menu_account")
async def handle_my_account(event: Message | CallbackQuery, user_profile: TelegramProfile, user_wallet: Wallet):
    """View account profile, purchased items count, total spent, and currency preferences."""
    import html
    from decimal import Decimal

    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
        is_edit = True
    else:
        target = event
        is_edit = False

    yer_bal = user_wallet.balance_yer
    usd_bal = await sync_to_async(CurrencyService.convert)(yer_bal, from_curr='YER', to_curr='USD')

    stats = await sync_to_async(get_user_account_stats)(user_profile)
    spent_yer = stats['total_spent_yer']
    spent_usd = await sync_to_async(CurrencyService.convert)(spent_yer, from_curr='YER', to_curr='USD')
    items_count = stats['total_items_count']
    orders_count = stats['orders_count']

    u_name = html.escape(user_profile.full_name)
    u_username = f"@{html.escape(user_profile.username)}" if user_profile.username else "لا يوجد"

    if items_count > 0 and items_count != orders_count:
        purchases_display = f"<b>{items_count:,}</b> منتج ({orders_count:,} طلب)"
    else:
        purchases_display = f"<b>{items_count:,}</b> منتج"

    text = (
        f"👤 <b>الملف الشخصي والحساب</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>معرف التليجرام:</b> <code>{user_profile.telegram_id}</code>\n"
        f"👤 <b>الاسم:</b> {u_name}\n"
        f"📩 <b>اسم المستخدم:</b> {u_username}\n"
        f"💰 <b>الرصيد المتاح:</b> <b>{yer_bal:,.0f} YER</b> (${usd_bal:,.2f})\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🛍️ <b>المنتجات المشتراة:</b> {purchases_display}\n"
        f"💸 <b>المبلغ المستخدم في المتجر:</b> <b>{spent_yer:,.0f} YER</b> (${spent_usd:,.2f})\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>عملة العرض المفضلة:</b> <b>{user_profile.get_preferred_currency_display()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"لتغيير عملة عرض الأسعار في المتجر:"
    )

    markup = get_settings_keyboard(user_profile.preferred_currency)

    if is_edit:
        try:
            await target.edit_text(text, reply_markup=markup, parse_mode='HTML')
        except Exception:
            await target.answer(text, reply_markup=markup, parse_mode='HTML')
    else:
        await target.answer(text, reply_markup=markup, parse_mode='HTML')


@router.message(F.text == "🎧 الدعم الفني")
async def handle_support(message: Message):
    """Customer support info."""
    text = (
        "🎧 *قسم الدعم والمساعدة الفنية*\n\n"
        "لأي استفسار، مشكلة في طلبك، أو مساعدة في شحن الرصيد، يرجى التواصل مع فريق الدعم المباشر:\n"
        "📩 الحساب المعتمد: @SupportStore\n"
        "⏰ أوقات العمل: على مدار الساعة 24/7"
    )
    await message.answer(text, parse_mode='Markdown')


@router.callback_query(F.data == "menu_home")
async def handle_back_home(callback: CallbackQuery, user_profile: TelegramProfile, user_wallet: Wallet, state: FSMContext):
    """Back to home button with FSM state cleanup."""
    await callback.answer()
    await state.clear()
    yer_bal = user_wallet.balance_yer
    text = (
        f"🏠 *القائمة الرئيسية*\n\n"
        f"💰 رصيدك الحالي: *{yer_bal:,.0f} YER*\n"
        "اختر القسم الذي تريده من الأزرار أدناه:"
    )
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(text, reply_markup=get_customer_main_menu(), parse_mode='Markdown')
