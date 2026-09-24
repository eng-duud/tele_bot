from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async
from apps.users.models import TelegramProfile
from apps.services_app.models import DigitalService, ServiceRequest
from apps.services_app.services import ServiceWorkflowService
from apps.telegram_bot.common.states import ServiceOrderStates

router = Router()

@router.message(F.text == "🛎 الخدمات")
async def handle_services_menu(message: Message):
    """View digital services menu."""
    services = await sync_to_async(list)(DigitalService.objects.filter(is_active=True))
    if not services:
        await message.answer("عذراً، لا توجد خدمات رقمية متاحة حالياً.")
        return

    buttons = []
    for s in services:
        badge = f"({s.price_yer:,.0f} YER)" if s.service_type == 'FIXED' else "(تسعير مخصص)"
        buttons.append([InlineKeyboardButton(text=f"🛎 {s.name} {badge}", callback_data=f"srv:{s.id}")])
    buttons.append([InlineKeyboardButton(text="🏠 الرئيسية", callback_data="menu_home")])

    text = "🛎 *قسم الخدمات الرقمية المخصصة*\n\nاختر الخدمة المطلوبة لعرض التفاصيل وتقديم طلبك:"
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode='Markdown')


@router.callback_query(F.data.startswith("srv:"))
async def handle_service_details(callback: CallbackQuery, state: FSMContext):
    """Show service info and initiate request."""
    await callback.answer()
    service_id = callback.data.split(":")[1]

    service = await sync_to_async(DigitalService.objects.filter(id=service_id).first)()
    if not service:
        await callback.answer("الخدمة غير متوفرة.", show_alert=True)
        return

    await state.update_data(service_id=str(service.id))
    await state.set_state(ServiceOrderStates.waiting_for_notes)

    text = (
        f"🛎 *{service.name}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 {service.description}\n\n"
        f"📋 *البيانات المطلوبة:*\n{service.instructions or 'يرجى كتابة تفاصيل طلبك بدقة.'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✍️ يرجى كتابة وإرسال *تفاصيل ومتطلبات طلبك* الآن:"
    )
    await callback.message.answer(text, parse_mode='Markdown')


@router.message(ServiceOrderStates.waiting_for_notes)
async def handle_service_notes_received(message: Message, user_profile: TelegramProfile, state: FSMContext):
    """Save customer requirements and create ServiceRequest."""
    txt = message.text.strip().lower() if message.text else ""
    if txt in ("/cancel", "إلغاء", "رجوع", "الغاء"):
        await state.clear()
        from apps.telegram_bot.common.keyboards import get_customer_main_menu
        await message.answer("❌ تم إلغاء طلب الخدمة.", reply_markup=get_customer_main_menu())
        return

    data = await state.get_data()
    service_id = data.get("service_id")
    await state.clear()

    service = await sync_to_async(DigitalService.objects.filter(id=service_id).first)()
    notes = message.text.strip()

    req = await sync_to_async(ServiceWorkflowService.submit_request)(
        user=user_profile,
        service=service,
        customer_notes=notes
    )

    text = (
        f"✅ *تم استلام طلب الخدمة بنجاح!*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔖 رقم الطلب: `SRV-{str(req.id)[:6]}`\n"
        f"🛎 الخدمة: {service.name}\n"
        f"⏳ الحالة: *بانتظار مراجعة الإدارة وتقديم عرض السعر*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"سنرسل لك إشعاراً هنا فور اعتماد عرض السعر لتتمكن من قبوله وتنفيذه."
    )
    await message.answer(text, parse_mode='Markdown')


@router.callback_query(F.data.startswith("accept_quote:"))
async def handle_accept_quote(callback: CallbackQuery, user_profile: TelegramProfile):
    """Customer accepts provided quotation and pays from wallet."""
    await callback.answer()
    req_id = callback.data.split(":")[1]

    success, msg, order = await sync_to_async(ServiceWorkflowService.accept_quote_and_pay)(
        request_id=req_id,
        user=user_profile
    )

    if success and order:
        text = (
            f"🎉 *تم قبول عرض السعر والدفع بنجاح!*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔖 رقم الطلب: `{order.order_number}`\n"
            f"💰 المبلغ المخصوم: *{order.total_amount_yer:,.0f} YER*\n"
            f"⚙️ الحالة: *جاري العمل والتنفيذ من قبل الفريق*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"سيتم إشعارك فور اكتمال الخدمة وتسليمها."
        )
        await callback.message.edit_text(text, parse_mode='Markdown')
    else:
        await callback.message.answer(f"⚠️ {msg}")
