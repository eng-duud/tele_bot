import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from django.utils import timezone
from apps.users.models import TelegramProfile
from apps.users.services import AdminAuthService
from apps.payments.models import PaymentRequest
from apps.payments.services import PaymentService
from apps.wallet.services import WalletService
from apps.telegram_bot.common.bot_instances import get_customer_bot
from apps.core.utils import escape_md

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data.startswith("adm_pay_approve:"))
async def handle_admin_group_approve_payment(callback: CallbackQuery, user_profile: TelegramProfile):
    """
    Handle click on [Approve] button inside the private Admin Telegram Group or Admin Bot DM.
    Enforces RBAC permissions, atomic wallet deposit, idempotency, and updates message.
    """
    admin_id = callback.from_user.id
    
    # 1. Verify admin permissions
    has_perm = await sync_to_async(AdminAuthService.has_permission)(admin_id, 'MANAGE_PAYMENTS')
    if not has_perm:
        await callback.answer("⛔ عذراً، ليس لديك صلاحية اعتماد المدفوعات.", show_alert=True)
        return

    req_id = callback.data.split(":")[1]

    # 2. Execute idempotent approval
    success, msg, req = await sync_to_async(PaymentService.approve_payment)(
        payment_request_id=req_id,
        admin_profile=user_profile
    )

    if not success or not req:
        await callback.answer(f"⚠️ {msg}", show_alert=True)
        return

    await callback.answer("✅ تم قبول الطلب وإيداع الرصيد بنجاح!", show_alert=False)

    # 3. Update the admin group message to prevent duplicate clicks and show auditor info
    import html
    now_dt = timezone.now()
    time_str = now_dt.strftime("%Y-%m-%d %I:%M %p")

    raw_admin_name = callback.from_user.full_name or callback.from_user.username or str(admin_id)
    admin_name = html.escape(raw_admin_name)
    u_name = html.escape(req.user.full_name or "عميل")
    m_name = html.escape(req.payment_method.name)
    tx_val = html.escape(req.tx_number or 'لا يوجد')
    u_mention = f'<a href="tg://user?id={req.user.telegram_id}">{u_name}</a>'
    if req.user.username:
        clean_u = req.user.username.lstrip('@')
        customer_display = f"{u_mention} (<a href=\"https://t.me/{clean_u}\">@{html.escape(clean_u)}</a>)"
        customer_plain = f"{req.user.full_name} (@{clean_u} | ID: {req.user.telegram_id})"
    else:
        customer_display = f"{u_mention} (<code>{req.user.telegram_id}</code>)"
        customer_plain = f"{req.user.full_name} (ID: {req.user.telegram_id})"

    updated_caption = (
        f"✅ <b>تم اعتماد وقبول طلب الشحن بنجاح!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>العميل:</b> {customer_display}\n"
        f"💰 <b>المبلغ المودع:</b> <b>{req.amount_yer:,.0f} YER</b>\n"
        f"🏦 <b>طريقة الدفع:</b> {m_name}\n"
        f"🔢 <b>رقم العملية:</b> <code>{tx_val}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮‍♂️ <b>المشرف المنفذ:</b> {admin_name}\n"
        f"📅 <b>تاريخ الاعتماد:</b> <code>{time_str}</code>"
    )

    plain_caption = (
        f"✅ تم اعتماد وقبول طلب الشحن بنجاح!\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 العميل: {customer_plain}\n"
        f"💰 المبلغ المودع: {req.amount_yer:,.0f} YER\n"
        f"🏦 طريقة الدفع: {req.payment_method.name}\n"
        f"🔢 رقم العملية: {req.tx_number or 'لا يوجد'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮‍♂️ المشرف المنفذ: {raw_admin_name}\n"
        f"📅 تاريخ الاعتماد: {time_str}"
    )

    # All buttons disappear immediately after decision
    try:
        if callback.message.photo:
            try:
                await callback.message.edit_caption(caption=updated_caption, reply_markup=None, parse_mode='HTML')
            except Exception:
                await callback.message.edit_caption(caption=plain_caption, reply_markup=None)
        else:
            try:
                await callback.message.edit_text(text=updated_caption, reply_markup=None, parse_mode='HTML')
            except Exception:
                await callback.message.edit_text(text=plain_caption, reply_markup=None)
    except Exception as e:
        logger.warning(f"Could not edit admin group card: {e}")

    # 4. Notify customer via customer bot
    try:
        customer_bot = get_customer_bot()
        if customer_bot:
            wallet = await sync_to_async(WalletService.get_or_create_wallet)(req.user)
            cust_text = (
                f"🎉 <b>تم شحن رصيد محفظتك بنجاح!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"➕ <b>المبلغ المضاف:</b> <code>+{req.amount_yer:,.0f} YER</code>\n"
                f"💰 <b>رصيدك الحالي الآن:</b> <code>{wallet.balance_yer:,.0f} YER</code>\n"
                f"🏦 <b>طريقة الإيداع:</b> {m_name}\n"
                f"🔢 <b>رقم العملية:</b> <code>{tx_val}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"✨ <i>رصيدك متاح الآن في محفظتك ويمكنك استخدامه للشراء الفوري لأي منتج أو خدمة رقمية!</i>"
            )
            try:
                await customer_bot.send_message(chat_id=req.user.telegram_id, text=cust_text, parse_mode='HTML')
                logger.info(f"Successfully notified customer {req.user.telegram_id} of payment approval {req.id}")
            except Exception as e_html:
                logger.warning(f"Customer HTML notification failed: {e_html}, trying plain text...")
                plain_cust = (
                    f"🎉 تم شحن رصيد محفظتك بنجاح!\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"➕ المبلغ المضاف: +{req.amount_yer:,.0f} YER\n"
                    f"💰 رصيدك الحالي الآن: {wallet.balance_yer:,.0f} YER\n"
                    f"🏦 عبر: {req.payment_method.name}\n"
                    f"🔢 رقم العملية: {req.tx_number or 'لا يوجد'}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"رصيدك متاح الآن في محفظتك ويمكنك استخدامه للشراء الفوري لأي منتج أو خدمة رقمية!"
                )
                await customer_bot.send_message(chat_id=req.user.telegram_id, text=plain_cust, parse_mode=None)
        else:
            logger.error("Customer bot instance not available to send approval notification!")
    except Exception as notify_err:
        logger.error(f"Failed to notify customer about payment approval: {notify_err}", exc_info=True)


@router.callback_query(F.data.startswith("adm_pay_reject:"))
async def handle_admin_group_reject_payment(callback: CallbackQuery, user_profile: TelegramProfile):
    """
    Handle click on [Reject] button inside the private Admin Telegram Group or Admin Bot DM.
    """
    admin_id = callback.from_user.id
    has_perm = await sync_to_async(AdminAuthService.has_permission)(admin_id, 'MANAGE_PAYMENTS')
    if not has_perm:
        await callback.answer("⛔ ليس لديك صلاحية رفض المدفوعات.", show_alert=True)
        return

    req_id = callback.data.split(":")[1]

    success, msg, req = await sync_to_async(PaymentService.reject_payment)(
        payment_request_id=req_id,
        admin_profile=user_profile,
        reason="بيانات غير مطابقة أو لم يتم العثور على العملية"
    )

    if not success or not req:
        await callback.answer(f"⚠️ {msg}", show_alert=True)
        return

    await callback.answer("❌ تم رفض الطلب.", show_alert=False)

    import html
    now_dt = timezone.now()
    time_str = now_dt.strftime("%Y-%m-%d %I:%M %p")

    raw_admin_name = callback.from_user.full_name or callback.from_user.username or str(admin_id)
    admin_name = html.escape(raw_admin_name)
    u_name = html.escape(req.user.full_name or "عميل")
    m_name = html.escape(req.payment_method.name)
    tx_val = html.escape(req.tx_number or 'لا يوجد')
    u_mention = f'<a href="tg://user?id={req.user.telegram_id}">{u_name}</a>'
    if req.user.username:
        clean_u = req.user.username.lstrip('@')
        customer_display = f"{u_mention} (<a href=\"https://t.me/{clean_u}\">@{html.escape(clean_u)}</a>)"
        customer_plain = f"{req.user.full_name} (@{clean_u} | ID: {req.user.telegram_id})"
    else:
        customer_display = f"{u_mention} (<code>{req.user.telegram_id}</code>)"
        customer_plain = f"{req.user.full_name} (ID: {req.user.telegram_id})"

    updated_caption = (
        f"❌ <b>تم رفض طلب شحن الرصيد</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>العميل:</b> {customer_display}\n"
        f"💰 <b>المبلغ:</b> {req.amount_yer:,.0f} YER\n"
        f"🏦 <b>طريقة الدفع:</b> {m_name}\n"
        f"🔢 <b>رقم العملية:</b> <code>{tx_val}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮‍♂️ <b>تم الرفض بواسطة:</b> {admin_name}\n"
        f"📅 <b>الوقت:</b> <code>{time_str}</code>"
    )

    plain_caption = (
        f"❌ تم رفض طلب شحن الرصيد\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 العميل: {customer_plain}\n"
        f"💰 المبلغ: {req.amount_yer:,.0f} YER\n"
        f"🏦 طريقة الدفع: {req.payment_method.name}\n"
        f"🔢 رقم العملية: {req.tx_number or 'لا يوجد'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮‍♂️ تم الرفض بواسطة: {raw_admin_name}\n"
        f"📅 الوقت: {time_str}"
    )

    # All buttons disappear immediately after decision
    try:
        if callback.message.photo:
            try:
                await callback.message.edit_caption(caption=updated_caption, reply_markup=None, parse_mode='HTML')
            except Exception:
                await callback.message.edit_caption(caption=plain_caption, reply_markup=None)
        else:
            try:
                await callback.message.edit_text(text=updated_caption, reply_markup=None, parse_mode='HTML')
            except Exception:
                await callback.message.edit_text(text=plain_caption, reply_markup=None)
    except Exception as e:
        logger.warning(f"Could not edit admin rejection card: {e}")

    # Notify customer via customer bot
    try:
        customer_bot = get_customer_bot()
        if customer_bot:
            cust_text = (
                f"❌ <b>نأسف، تم رفض طلب شحن الرصيد الخاص بك</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💰 <b>المبلغ:</b> {req.amount_yer:,.0f} YER\n"
                f"🏦 <b>طريقة الدفع:</b> {m_name}\n"
                f"🔢 <b>رقم العملية:</b> <code>{tx_val}</code>\n"
                f"⚠️ <b>السبب:</b> {html.escape(req.rejection_reason or 'بيانات غير مطابقة')}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"يرجى التأكد من صحة رقم العملية، أو مراجعة الدعم الفني."
            )
            try:
                await customer_bot.send_message(chat_id=req.user.telegram_id, text=cust_text, parse_mode='HTML')
                logger.info(f"Successfully notified customer {req.user.telegram_id} of payment rejection {req.id}")
            except Exception as e_html:
                logger.warning(f"Customer rejection HTML notification failed: {e_html}, trying plain text...")
                plain_cust = (
                    f"❌ نأسف، تم رفض طلب شحن الرصيد الخاص بك\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"المبلغ: {req.amount_yer:,.0f} YER\n"
                    f"طريقة الدفع: {req.payment_method.name}\n"
                    f"رقم العملية: {req.tx_number or 'لا يوجد'}\n"
                    f"السبب: {req.rejection_reason or 'بيانات غير مطابقة'}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"يرجى التأكد من صحة رقم العملية، أو مراجعة الدعم الفني."
                )
                await customer_bot.send_message(chat_id=req.user.telegram_id, text=plain_cust, parse_mode=None)
        else:
            logger.error("Customer bot instance not available to send rejection notification!")
    except Exception as notify_err:
        logger.error(f"Failed to notify customer about rejection: {notify_err}", exc_info=True)


@router.callback_query(F.data.startswith("adm_contact:"))
async def handle_admin_contact_user(callback: CallbackQuery):
    """Inform admin how to reach customer when they have no public username."""
    user_id = callback.data.split(":")[1]
    await callback.answer(
        f"معرف العميل الرقمي: {user_id}\nيمكنك فتح محادثته بالضغط المباشر على اسمه في نص الإشعار أعلاه.",
        show_alert=True
    )

