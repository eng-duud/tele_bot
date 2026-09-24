from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from apps.users.models import TelegramProfile
from apps.orders.models import Order

router = Router()

def _get_user_orders_data(user_profile: TelegramProfile):
    orders = Order.objects.filter(user=user_profile).prefetch_related('items').order_by('-created_at')[:8]
    data = []
    for ord in orders:
        item = ord.items.first()
        prod_title = item.product_name_snapshot if item else "طلب رقمي"
        data.append({
            'id': str(ord.id),
            'order_number': ord.order_number,
            'title': prod_title,
            'status': ord.get_status_display()
        })
    return data

def _get_single_order_details(order_id: str, user_profile: TelegramProfile):
    order = Order.objects.filter(id=order_id, user=user_profile).prefetch_related('items').first()
    if not order:
        return None
    item = order.items.first()
    prod_title = item.product_name_snapshot if item else "منتج رقمي"
    qty = item.quantity if item else 1
    date_str = order.created_at.strftime("%Y-%m-%d %H:%M")
    return {
        'order_number': order.order_number,
        'title': prod_title,
        'quantity': qty,
        'total_amount': order.total_amount_yer,
        'date_str': date_str,
        'status_display': order.get_status_display(),
        'status': order.status,
        'delivered_data': order.delivered_data,
        'failure_reason': order.failure_reason
    }

@router.message(F.text == "📦 طلباتي")
async def handle_my_orders(message: Message, user_profile: TelegramProfile):
    """View customer order history."""
    orders_data = await sync_to_async(_get_user_orders_data)(user_profile)

    if not orders_data:
        await message.answer("📦 ليس لديك أي طلبات سابقة حتى الآن. يمكنك تصفح *🛍 المتجر* للشراء!", parse_mode='Markdown')
        return

    buttons = []
    for ord in orders_data:
        buttons.append([InlineKeyboardButton(
            text=f"📦 {ord['order_number']} | {ord['title']} ({ord['status']})",
            callback_data=f"order_view:{ord['id']}"
        )])

    buttons.append([InlineKeyboardButton(text="🏠 الرئيسية", callback_data="menu_home")])

    text = "📦 *سجل طلباتك ومشترياتك:*\n\nاضغط على أي طلب لعرض بيانات التفعيل والتسليم:"
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode='Markdown')


@router.callback_query(F.data.startswith("order_view:"))
async def handle_order_view(callback: CallbackQuery, user_profile: TelegramProfile):
    """View specific order details and delivered credentials."""
    await callback.answer()
    order_id = callback.data.split(":")[1]

    details = await sync_to_async(_get_single_order_details)(order_id, user_profile)
    if not details:
        await callback.answer("الطلب غير موجود.", show_alert=True)
        return

    import html
    prod_title = html.escape(details['title'])
    status_disp = html.escape(details['status_display'])
    date_str = html.escape(details['date_str'])

    text_lines = [
        f"🔖 <b>تفاصيل الطلب: {details['order_number']}</b>",
        f"━━━━━━━━━━━━━━━━━━",
        f"🛍 المنتج: <b>{prod_title}</b>",
        f"🔢 الكمية: {details['quantity']}",
        f"💰 الإجمالي: <b>{details['total_amount']:,.0f} YER</b>",
        f"📅 التاريخ: <code>{date_str}</code>",
        f"⚡ الحالة: <b>{status_disp}</b>",
        f"━━━━━━━━━━━━━━━━━━"
    ]

    if details['status'] == 'COMPLETED' and details['delivered_data']:
        safe_data = html.escape(str(details['delivered_data']))
        text_lines.append(f"🔑 <b>بيانات الاستلام والتفعيل:</b>\n<code>{safe_data}</code>\n━━━━━━━━━━━━━━━━━━")
    elif details['status'] == 'PROCESSING':
        text_lines.append("⏳ <b>الطلب قيد التنفيذ والتسليم حالياً وسيصلك إشعار فوري عند اكتماله.</b>")
    elif details['status'] == 'REFUNDED':
        clean_fail = html.escape(str(details['failure_reason'] or 'تعذر التسليم'))
        text_lines.append(f"🔄 <b>تم استرجاع كامل المبلغ لمحفظتك.</b>\nالسبب: {clean_fail}")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 العودة للطلبات", callback_data="orders_list")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="menu_home")]
    ])

    html_content = "\n".join(text_lines)
    try:
        await callback.message.edit_text(html_content, reply_markup=markup, parse_mode='HTML')
    except Exception:
        plain_lines = [
            f"🔖 تفاصيل الطلب: {details['order_number']}",
            f"━━━━━━━━━━━━━━━━━━",
            f"🛍 المنتج: {details['title']}",
            f"🔢 الكمية: {details['quantity']}",
            f"💰 الإجمالي: {details['total_amount']:,.0f} YER",
            f"📅 التاريخ: {details['date_str']}",
            f"⚡ الحالة: {details['status_display']}",
            f"━━━━━━━━━━━━━━━━━━"
        ]
        if details['status'] == 'COMPLETED' and details['delivered_data']:
            plain_lines.append(f"🔑 بيانات الاستلام والتفعيل:\n{details['delivered_data']}\n━━━━━━━━━━━━━━━━━━")
        await callback.message.edit_text("\n".join(plain_lines), reply_markup=markup)


@router.callback_query(F.data == "orders_list")
async def handle_orders_back_list(callback: CallbackQuery, user_profile: TelegramProfile):
    """Back button to orders list."""
    await callback.answer()
    orders_data = await sync_to_async(_get_user_orders_data)(user_profile)

    buttons = []
    for ord in orders_data:
        buttons.append([InlineKeyboardButton(
            text=f"📦 {ord['order_number']} | {ord['title']} ({ord['status']})",
            callback_data=f"order_view:{ord['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🏠 الرئيسية", callback_data="menu_home")])
    await callback.message.edit_text("📦 *سجل طلباتك:*\nاختر طلباً لعرض تفاصيله:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode='Markdown')
