from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async
from apps.users.models import TelegramProfile
from apps.wallet.models import Wallet, WalletTransaction
from apps.core.services import CurrencyService
from apps.payments.models import PaymentMethod, PaymentRequest
from apps.payments.services import PaymentService
from apps.notifications.services import AdminGroupNotifierService
from apps.telegram_bot.common.keyboards import get_wallet_keyboard, get_payment_methods_keyboard, get_customer_main_menu
from apps.telegram_bot.common.states import DepositStates

router = Router()

@router.message(F.text == "💰 المحفظة")
@router.callback_query(F.data == "menu_wallet")
async def handle_wallet_menu(event: Message | CallbackQuery, user_profile: TelegramProfile, user_wallet: Wallet):
    """View wallet balance and operations."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    yer_bal = user_wallet.balance_yer
    usd_bal = await sync_to_async(CurrencyService.convert)(yer_bal, from_curr='YER', to_curr='USD')

    text = (
        f"💰 *محفظتك الإلكترونية*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🇾🇪 الرصيد بالريال: *{yer_bal:,.0f} YER*\n"
        f"🇺🇸 الرصيد بالدولار: *${usd_bal:,.2f} USD*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        "يمكنك استخدام رصيد محفظتك لشراء أي منتج أو خدمة رقمية في المتجر فورياً وبدون انتظار موافقات."
    )
    await target.answer(text, reply_markup=get_wallet_keyboard(), parse_mode='Markdown')


@router.callback_query(F.data == "wallet_deposit")
async def handle_start_deposit(callback: CallbackQuery):
    """Display available payment methods."""
    await callback.answer()
    methods = await sync_to_async(list)(PaymentMethod.objects.filter(is_active=True))
    if not methods:
        await callback.message.answer("عذراً، لا توجد طرق دفع مفعلة حالياً. يرجى التواصل مع الإدارة.")
        return

    text = "💳 *طرق شحن الرصيد المتاحة:*\n\nاختر وسيلة الدفع التي تناسبك لعرض التعليمات:"
    await callback.message.edit_text(text, reply_markup=get_payment_methods_keyboard(methods), parse_mode='Markdown')


@router.callback_query(F.data.startswith("paymethod:"))
async def handle_payment_method_selected(callback: CallbackQuery, state: FSMContext):
    """Show transfer instructions for chosen payment method and ask for amount."""
    await callback.answer()
    method_id = callback.data.split(":")[1]

    method = await sync_to_async(PaymentMethod.objects.filter(id=method_id).first)()
    if not method:
        await callback.answer("طريقة الدفع غير متوفرة.", show_alert=True)
        return

    await state.update_data(payment_method_id=str(method.id))
    await state.set_state(DepositStates.waiting_for_amount)

    text = (
        f"🏦 *{method.icon} {method.name}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 اسم الحساب: *{method.account_name or 'المتجر'}*\n"
        f"🔢 رقم الحساب / النقطة: `{method.account_number}`\n\n"
        f"📝 *تعليمات التحويل:*\n{method.instructions}\n\n"
        f"💵 الحد الأدنى: {method.min_deposit_yer:,.0f} YER\n"
        f"💵 الحد الأقصى: {method.max_deposit_yer:,.0f} YER\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✍️ *الخطوة 1:* يرجى كتابة وإرسال *المبلغ المحول بالريال اليمني (YER)*:"
    )
    await callback.message.answer(text, parse_mode='Markdown')


@router.message(DepositStates.waiting_for_amount)
async def handle_deposit_amount_entered(message: Message, state: FSMContext):
    """Validate amount and prompt for transaction proof."""
    txt = message.text.strip().lower() if message.text else ""
    if txt in ("/cancel", "إلغاء", "رجوع", "الغاء"):
        await state.clear()
        await message.answer("❌ تم إلغاء طلب الشحن بنجاح.", reply_markup=get_customer_main_menu())
        return

    try:
        amount = Decimal(message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError()
    except Exception:
        await message.answer("⚠️ يرجى إدخال مبلغ صحيح بالأرقام فقط (مثال: 10000):")
        return

    data = await state.get_data()
    method_id = data.get("payment_method_id")
    method = await sync_to_async(PaymentMethod.objects.filter(id=method_id).first)()

    if amount < method.min_deposit_yer:
        await message.answer(f"⚠️ المبلغ المدخل أقل من الحد الأدنى المسموح ({method.min_deposit_yer:,.0f} YER). أعد المحاولة:")
        return
    if amount > method.max_deposit_yer:
        await message.answer(f"⚠️ المبلغ المدخل يتجاوز الحد الأقصى المسموح ({method.max_deposit_yer:,.0f} YER). أعد المحاولة:")
        return

    await state.update_data(amount=str(amount))
    await state.set_state(DepositStates.waiting_for_tx_number)
    await message.answer(
        f"🔢 <b>الخطوة 2:</b> يرجى إرسال <b>رقم العملية أو الحوالة</b> الآن:\n\n"
        f"💡 <i>يتم التحقق من رقم العملية آلياً لمنع تكرار الشحن لنفس الدفعة.</i>\n"
        f"(أو اكتب <b>إلغاء</b> للتراجع والعودة للقائمة الرئيسية)",
        parse_mode='HTML'
    )


@router.message(DepositStates.waiting_for_tx_number)
async def handle_deposit_tx_number_received(message: Message, user_profile: TelegramProfile, state: FSMContext, bot):
    """Validate the transaction number, then request the transfer receipt photo."""
    import html

    tx_number = message.text.strip() if message.text else ""

    txt = tx_number.lower()
    if txt in ("/cancel", "إلغاء", "رجوع", "الغاء"):
        await state.clear()
        await message.answer("❌ تم إلغاء طلب الشحن بنجاح.", reply_markup=get_customer_main_menu())
        return

    if len(tx_number) < 2:
        await message.answer("⚠️ يرجى إدخال رقم عملية أو حوالة صحيح ومكتمل:")
        return

    # Check for duplicate transaction number across non-cancelled/non-rejected requests
    is_duplicate = await sync_to_async(
        PaymentRequest.objects.filter(
            tx_number__iexact=tx_number
        ).exclude(status__in=['REJECTED', 'CANCELLED']).exists
    )()

    if is_duplicate:
        await message.answer(
            f"⚠️ <b>عذراً، رقم العملية هذا (<code>{html.escape(tx_number)}</code>) مستخدم مسبقاً!</b>\n\n"
            f"لا يمكن تقديم طلب شحن بنفس رقم العملية لتفادي الشحن المزدوج.\n"
            f"يرجى التأكد من رقم العملية وإعادة إرساله (أو اكتب <b>إلغاء</b> للتراجع):",
            parse_mode='HTML'
        )
        return

    await state.update_data(tx_number=tx_number)
    await state.set_state(DepositStates.waiting_for_proof_photo)
    await message.answer(
        "📸 <b>الخطوة 3:</b> أرسل الآن <b>صورة إشعار التحويل</b> كصورة من Telegram.\n\n"
        "يجب أن تكون الصورة واضحة وتظهر المبلغ ورقم العملية، أو اكتب <b>إلغاء</b> للتراجع.",
        parse_mode='HTML'
    )


@router.message(DepositStates.waiting_for_proof_photo)
async def handle_deposit_proof_photo(message: Message, user_profile: TelegramProfile, state: FSMContext, bot):
    """Persist the Telegram photo file_id and submit the complete request."""
    import html

    txt = message.text.strip().lower() if message.text else ""
    if txt in ("/cancel", "إلغاء", "رجوع", "الغاء"):
        await state.clear()
        await message.answer("❌ تم إلغاء طلب الشحن بنجاح.", reply_markup=get_customer_main_menu())
        return

    if not message.photo:
        await message.answer(
            "⚠️ لم تصل صورة التحويل. أرسلها كـ <b>صورة Telegram</b> واضحة، أو اكتب <b>إلغاء</b> للتراجع.",
            parse_mode='HTML'
        )
        return

    data = await state.get_data()
    method_id = data.get("payment_method_id")
    amount = Decimal(data.get("amount"))
    tx_number = data.get("tx_number", "").strip()
    method = await sync_to_async(PaymentMethod.objects.filter(id=method_id).first)()
    if not method or not tx_number:
        await state.clear()
        await message.answer("⚠️ انتهت جلسة طلب الشحن. ابدأ الطلب من جديد.", reply_markup=get_customer_main_menu())
        return

    # Telegram keeps the file on its servers; the largest photo variant gives
    # the admin the best review quality while storing only a small file_id.
    proof_image_file_id = message.photo[-1].file_id
    req = await sync_to_async(PaymentService.create_payment_request)(
        user=user_profile,
        payment_method=method,
        amount_yer=amount,
        tx_number=tx_number,
        proof_image_file_id=proof_image_file_id,
        proof_image_url=""
    )
    await state.clear()

    await AdminGroupNotifierService.send_payment_request_card(bot, req)

    m_name = html.escape(method.name)
    text = (
        f"✅ <b>تم استلام طلب شحن الرصيد بنجاح!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔖 رقم الطلب: <code>PAY-{str(req.id)[:8]}</code>\n"
        f"💰 المبلغ: <b>{amount:,.0f} YER</b>\n"
        f"🔢 رقم العملية: <code>{html.escape(tx_number)}</code>\n"
        f"🏦 طريقة الدفع: {m_name}\n"
        f"📸 تم إرفاق صورة التحويل للمراجعة\n"
        f"⏳ الحالة: <b>قيد المراجعة والاعتماد</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"سيقوم المشرف بمطابقة البيانات وإيداع الرصيد في محفظتك بعد التحقق."
    )
    await message.answer(text, reply_markup=get_wallet_keyboard(), parse_mode='HTML')


@router.callback_query(F.data == "wallet_history")
async def handle_wallet_history(callback: CallbackQuery, user_wallet: Wallet):
    """View recent financial ledger movements."""
    await callback.answer()
    transactions = await sync_to_async(list)(
        WalletTransaction.objects.filter(wallet=user_wallet).order_by('-created_at')[:10]
    )

    if not transactions:
        await callback.message.answer("لا توجد حركات مالية مسجلة في محفظتك حتى الآن.")
        return

    lines = ["📋 *آخر الحركات المالية في محفظتك:*\n━━━━━━━━━━━━━━━━━━"]
    for t in transactions:
        sign = "🟢 +" if t.amount > 0 else "🔴 "
        date_str = t.created_at.strftime("%Y-%m-%d %H:%M")
        lines.append(f"{sign}{abs(t.amount):,.0f} YER | {t.get_tx_type_display()}\n📝 {t.description}\n📅 `{date_str}`\n")
    lines.append("━━━━━━━━━━━━━━━━━━")

    await callback.message.answer("\n".join(lines), parse_mode='Markdown')
