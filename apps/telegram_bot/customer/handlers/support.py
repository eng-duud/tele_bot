import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async
from apps.users.models import TelegramProfile
from apps.support.services import SupportService
from apps.core.services import SystemSettingService
from apps.telegram_bot.common.keyboards import get_customer_main_menu
from apps.telegram_bot.common.states import CustomerSupportStates

router = Router()

@router.message(F.text == "🎧 الدعم الفني")
@router.callback_query(F.data == "menu_support")
async def handle_support_menu(event: Message | CallbackQuery, user_profile: TelegramProfile):
    """Display dynamic support information and ticketing options."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    store_name = await sync_to_async(SystemSettingService.get_setting)('STORE_NAME', 'المتجر الرقمي')
    support_user = await sync_to_async(SystemSettingService.get_setting)('SUPPORT_USERNAME', '')
    is_enabled = await sync_to_async(SystemSettingService.get_bool)('SUPPORT_ENABLED', True)

    clean_user = support_user.lstrip('@').strip() if support_user else ""
    user_line = f"👤 <b>المعرف المباشر:</b> <a href=\"https://t.me/{clean_user}\">@{html.escape(clean_user)}</a>\n" if clean_user else ""

    text = (
        f"🎧 <b>قسم الدعم والمساعدة الفنية - {html.escape(store_name)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"فريق الدعم الفني متاح لمساعدتك في أي استفسار، متابعة طلب، أو حل أي مشكلة تواجهك.\n\n"
        f"{user_line}"
        f"⏰ <b>أوقات العمل:</b> على مدار الساعة 24/7\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 يمكنك فتح تذكرة دعم فني مباشرة وسيقوم المشرفون بالرد عليك في محادثة البوت:"
    )

    buttons = []
    if is_enabled:
        buttons.append([InlineKeyboardButton(text="✍️ فتح تذكرة وكتابة رسالة للدعم", callback_data="start_support_ticket")])
    if clean_user:
        buttons.append([InlineKeyboardButton(text=f"💬 تواصل مباشر (@{clean_user})", url=f"https://t.me/{clean_user}")])
    buttons.append([InlineKeyboardButton(text="🏠 الرئيسية", callback_data="menu_home")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await target.answer(text, reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data == "start_support_ticket")
async def handle_start_ticket(callback: CallbackQuery, state: FSMContext):
    """Prompt user to write their inquiry or issue."""
    await callback.answer()
    await state.set_state(CustomerSupportStates.waiting_for_message)

    text = (
        "✍️ <b>كتابة رسالة الدعم الفني</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        "يرجى كتابة استفسارك أو تفاصيل المشكلة بدقة وإرسالها.\n"
        "<i>(يمكنك أيضاً إرسال صورة توضيحية مع نص الشرح)</i>\n\n"
        "للإلغاء أرسل: <code>إلغاء</code>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_support_ticket")]
    ])
    await callback.message.answer(text, reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data == "cancel_support_ticket")
async def handle_cancel_ticket(callback: CallbackQuery, state: FSMContext):
    """Cancel ticket drafting."""
    await callback.answer("تم إلغاء التذكرة.")
    await state.clear()
    await callback.message.answer("❌ تم إلغاء كتابة التذكرة.", reply_markup=get_customer_main_menu())


@router.message(CustomerSupportStates.waiting_for_message)
async def handle_ticket_message_received(message: Message, user_profile: TelegramProfile, state: FSMContext, bot):
    """Receive message or photo from customer and dispatch ticket to Admin Group."""
    txt = (message.text or message.caption or "").strip()
    if txt.lower() in ("/cancel", "إلغاء", "الغاء", "رجوع"):
        await state.clear()
        await message.answer("❌ تم إلغاء كتابة التذكرة.", reply_markup=get_customer_main_menu())
        return

    # Extract attachments
    photo_file_id = ""
    doc_file_id = ""
    if message.photo:
        photo_file_id = message.photo[-1].file_id
    elif message.document:
        doc_file_id = message.document.file_id

    if not txt and not photo_file_id and not doc_file_id:
        await message.answer("⚠️ يرجى كتابة نص الرسالة أو إرفاق صورة توضيحية للمشكلة.")
        return

    await state.clear()

    # Create ticket in DB
    ticket, msg_obj = await sync_to_async(SupportService.create_ticket)(
        user=user_profile,
        text=txt,
        photo_file_id=photo_file_id,
        document_file_id=doc_file_id
    )

    # Dispatch to Admin Group
    await SupportService.send_ticket_card_to_admin_group(bot, ticket, msg_obj)

    confirm_text = (
        f"✅ <b>تم استلام تذكرتك بنجاح!</b> 📬\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔖 <b>رقم التذكرة:</b> <code>{ticket.ticket_number}</code>\n"
        f"⏳ <b>الحالة:</b> <b>قيد المراجعة لدى فريق الدعم</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"سيقوم أحد المشرفين بمراجعة رسالتك وإرسال الرد لك هنا في أسرع وقت."
    )
    await message.answer(confirm_text, reply_markup=get_customer_main_menu(), parse_mode='HTML')
