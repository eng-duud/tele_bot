from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async
from apps.users.models import TelegramProfile
from apps.wallet.models import Wallet
from apps.wallet.services import InsufficientBalanceError
from apps.catalog.models import Category, Product
from apps.catalog.services import CatalogService
from apps.inventory.services import InventoryService
from apps.orders.services import OrderService
from apps.fulfillment.services import FulfillmentService
from apps.notifications.services import SuccessChannelService
from apps.telegram_bot.common.keyboards import (
    get_categories_keyboard, 
    get_products_keyboard, 
    get_product_detail_keyboard,
    get_quantity_selector_keyboard
)
from apps.telegram_bot.common.states import PurchaseStates

router = Router()

@router.message(F.text.in_(["🛍 المتجر", "📂 الأقسام"]))
async def handle_open_store(message: Message):
    """Open root catalog categories."""
    categories = await sync_to_async(CatalogService.get_root_categories)()
    if not categories:
        await message.answer("عذراً، لا توجد أقسام متاحة حالياً في المتجر. يرجى العودة لاحقاً.")
        return

    text = "📂 *أقسام المتجر الرقمي*\n\nاختر القسم الذي ترغب بتصفحه:"
    await message.answer(text, reply_markup=get_categories_keyboard(categories), parse_mode='Markdown')


@router.callback_query(F.data == "cat_root")
async def handle_cat_root(callback: CallbackQuery):
    """Back to root categories."""
    await callback.answer()
    categories = await sync_to_async(CatalogService.get_root_categories)()
    text = "📂 *أقسام المتجر الرقمي*\n\nاختر القسم الذي ترغب بتصفحه:"
    await callback.message.edit_text(text, reply_markup=get_categories_keyboard(categories), parse_mode='Markdown')


@router.callback_query(F.data.startswith("cat:"))
async def handle_category_selected(callback: CallbackQuery):
    """Handle click on a category."""
    await callback.answer()
    category_id = callback.data.split(":")[1]

    # Check for subcategories first
    subcategories = await sync_to_async(CatalogService.get_subcategories)(category_id)
    if subcategories:
        text = "📁 *التصنيفات الفرعية*\n\nاختر التصنيف الفرعي:"
        await callback.message.edit_text(text, reply_markup=get_categories_keyboard(subcategories, parent_id=category_id), parse_mode='Markdown')
        return

    # Otherwise fetch products
    products = await sync_to_async(CatalogService.get_products_by_category)(category_id)
    if not products:
        text = "عذراً، لا توجد منتجات مضافة في هذا القسم حالياً."
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 رجوع للأقسام", callback_data="cat_root")]])
        await callback.message.edit_text(text, reply_markup=markup)
        return

    text = "🛍 *قائمة المنتجات المتاحة:*"
    markup = await sync_to_async(get_products_keyboard)(products, category_id)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode='Markdown')


@router.callback_query(F.data.startswith("prod:"))
async def handle_product_details(callback: CallbackQuery, user_profile: TelegramProfile):
    """Display product information, stock status, and dual currency pricing."""
    await callback.answer()
    product_id = callback.data.split(":")[1]

    product = await sync_to_async(Product.objects.filter(id=product_id).first)()
    if not product:
        await callback.answer("المنتج غير موجود أو تم حذفه.", show_alert=True)
        return

    in_stock = await sync_to_async(CatalogService.is_in_stock)(product)
    price_display = await sync_to_async(CatalogService.get_price_display)(product, user_profile.preferred_currency)
    avail_count = await sync_to_async(get_available_stock_count)(product)

    import html
    prod_name = html.escape(product.name)
    prod_desc = html.escape(product.description or "منتج رقمي مميز مع تسليم فوري وآمن.")

    if product.stock_type in ('UNLIMITED', 'API_CAPACITY'):
        stock_badge = "🟢 <b>متوفر دائماً (تسليم فوري)</b>"
        qty_badge = "♾️ <b>غير محدود</b>"
    elif in_stock:
        stock_badge = "🟢 <b>متوفر للطلب الفوري</b>"
        qty_badge = f"📦 <b>{avail_count:,}</b> قطعة متوفرة"
    else:
        stock_badge = "🔴 <b>نفد المخزون مؤقتاً</b>"
        qty_badge = "❌ <b>0</b> قطعة متوفرة (غير متاح حالياً)"

    text = (
        f"🏷 <b>{prod_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 {prod_desc}\n\n"
        f"💰 <b>السعر:</b> {price_display}\n"
        f"📊 <b>الكمية الفعلية بالمخزون:</b> {qty_badge}\n"
        f"📦 <b>حالة التوفر:</b> {stock_badge}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    markup = get_product_detail_keyboard(product, in_stock)

    if product.image_url:
        if callback.message.photo:
            try:
                await callback.message.edit_caption(caption=text, reply_markup=markup, parse_mode='HTML')
                return
            except Exception:
                pass
        try:
            await callback.message.answer_photo(photo=product.image_url, caption=text, reply_markup=markup, parse_mode='HTML')
            try:
                await callback.message.delete()
            except Exception:
                pass
            return
        except Exception:
            pass

    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=markup, parse_mode='HTML')
        else:
            await callback.message.edit_text(text, reply_markup=markup, parse_mode='HTML')
    except Exception:
        await callback.message.answer(text, reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data.startswith("restock_sub:"))
async def handle_restock_subscription(callback: CallbackQuery, user_profile: TelegramProfile):
    """Subscribe to restock notification."""
    product_id = callback.data.split(":")[1]
    product = await sync_to_async(Product.objects.filter(id=product_id).first)()
    if not product:
        await callback.answer("المنتج غير موجود.", show_alert=True)
        return

    _, created = await sync_to_async(InventoryService.subscribe_to_restock)(product, user_profile)
    if created:
        await callback.answer("🔔 تم تفعيل التنبيه! سنرسل لك إشعاراً فور توفر هذا المنتج مجدداً.", show_alert=True)
    else:
        await callback.answer("أنت مشترك بالفعل في تنبيهات هذا المنتج.", show_alert=True)


def get_available_stock_count(product: Product) -> int:
    """Calculate maximum units available for purchase based on stock type."""
    if product.stock_type in ('UNLIMITED', 'API_CAPACITY'):
        return 9999
    if product.stock_type == 'QUANTITY':
        return product.stock_quantity
    if product.stock_type == 'INDIVIDUAL_ITEMS':
        from apps.inventory.models import StockItem
        return StockItem.objects.filter(product=product, status='AVAILABLE').count()
    return 0


async def render_quantity_selector(event: CallbackQuery | Message, product: Product, user_profile: TelegramProfile, quantity: int = 1, is_edit: bool = True):
    """Render or edit the interactive quantity adjustment card."""
    from apps.wallet.services import WalletService
    from apps.catalog.services import CatalogService
    import html

    wallet = await sync_to_async(WalletService.get_or_create_wallet)(user_profile)
    max_stock = await sync_to_async(get_available_stock_count)(product)

    # Constrain quantity
    if max_stock > 0 and quantity > max_stock:
        quantity = max_stock
    quantity = max(1, quantity)

    unit_price_yer = await sync_to_async(CatalogService.get_price_in_yer)(product)
    total_price_yer = unit_price_yer * Decimal(str(quantity))
    has_sufficient = wallet.balance_yer >= total_price_yer

    stock_text = f"{max_stock} وحدة" if max_stock < 9000 else "متوفر بكثرة"
    balance_status = "🟢 كافٍ" if has_sufficient else "🔴 غير كافٍ"

    text = (
        f"🛒 <b>تحديد كمية الشراء: {html.escape(product.name)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 سعر الحبة الواحدة: <b>{unit_price_yer:,.0f} YER</b>\n"
        f"📦 المخزون المتاح: <b>{stock_text}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔢 الكمية المختارة: <b>{quantity}</b>\n"
        f"💵 الإجمالي المطلوب: <b>{total_price_yer:,.0f} YER</b>\n"
        f"💳 رصيد محفظتك: <b>{wallet.balance_yer:,.0f} YER</b> ({balance_status})\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"عدّل الكمية بالأزرار أدناه أو اكتبها بنفسك:"
    )

    markup = get_quantity_selector_keyboard(
        product_id=str(product.id),
        current_qty=quantity,
        max_stock=max_stock,
        total_price_yer=float(total_price_yer),
        has_sufficient_balance=has_sufficient
    )

    if isinstance(event, CallbackQuery):
        if is_edit:
            try:
                if event.message.photo:
                    await event.message.edit_caption(caption=text, reply_markup=markup, parse_mode='HTML')
                else:
                    await event.message.edit_text(text, reply_markup=markup, parse_mode='HTML')
            except Exception as edit_err:
                if "message is not modified" in str(edit_err).lower():
                    return
                try:
                    if event.message.photo:
                        await event.message.edit_caption(caption=text, reply_markup=markup, parse_mode='HTML')
                    else:
                        await event.message.edit_text(text, reply_markup=markup, parse_mode='HTML')
                except Exception:
                    await event.message.answer(text, reply_markup=markup, parse_mode='HTML')
        else:
            await event.message.answer(text, reply_markup=markup, parse_mode='HTML')
    else:
        await event.answer(text, reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data.startswith("buy:"))
async def handle_initiate_buy(callback: CallbackQuery, user_profile: TelegramProfile, state: FSMContext):
    """Start purchase process by opening the interactive quantity selector."""
    await callback.answer()
    await state.clear()
    product_id = callback.data.split(":")[1]
    product = await sync_to_async(Product.objects.filter(id=product_id).first)()
    if not product:
        await callback.answer("المنتج غير موجود.", show_alert=True)
        return

    in_stock = await sync_to_async(CatalogService.is_in_stock)(product)
    if not in_stock:
        await callback.answer("عذراً، هذا المنتج غير متوفر في المخزون حالياً.", show_alert=True)
        return

    await render_quantity_selector(callback, product, user_profile, quantity=1, is_edit=True)


@router.callback_query(F.data.startswith("buy_qty:"))
async def handle_change_quantity(callback: CallbackQuery, user_profile: TelegramProfile):
    """Adjust selected quantity (+, -, or quick preset)."""
    await callback.answer()
    parts = callback.data.split(":")
    product_id = parts[1]
    qty = int(parts[2]) if len(parts) > 2 else 1

    product = await sync_to_async(Product.objects.filter(id=product_id).first)()
    if not product:
        await callback.answer("المنتج غير موجود.", show_alert=True)
        return

    await render_quantity_selector(callback, product, user_profile, quantity=qty, is_edit=True)


@router.callback_query(F.data.startswith("buy_custom_qty:"))
async def handle_custom_qty_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompt user to type a custom numeric quantity."""
    await callback.answer()
    product_id = callback.data.split(":")[1]
    product = await sync_to_async(Product.objects.filter(id=product_id).first)()
    if not product:
        await callback.answer("المنتج غير موجود.", show_alert=True)
        return

    import html
    await state.update_data(product_id=str(product.id))
    await state.set_state(PurchaseStates.waiting_for_quantity)
    await callback.message.answer(
        f"✍️ <b>إدخال كمية مخصصة: {html.escape(product.name)}</b>\n\n"
        f"يرجى إرسال رقم الكمية التي ترغب بشرائها (مثال: <code>5</code> أو <code>15</code>):\n"
        f"(أو اكتب <b>إلغاء</b> للرجوع)",
        parse_mode='HTML'
    )


@router.message(PurchaseStates.waiting_for_quantity)
async def handle_custom_quantity_received(message: Message, user_profile: TelegramProfile, state: FSMContext):
    """Process custom quantity text input."""
    txt = message.text.strip().lower() if message.text else ""
    if txt in ("/cancel", "إلغاء", "رجوع", "الغاء"):
        await state.clear()
        from apps.telegram_bot.common.keyboards import get_customer_main_menu
        await message.answer("❌ تم إلغاء تعديل الكمية.", reply_markup=get_customer_main_menu())
        return

    try:
        qty = int(message.text.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ يرجى إدخال رقم صحيح أكبر من الصفر (مثال: 3):")
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    await state.clear()

    product = await sync_to_async(Product.objects.filter(id=product_id).first)()
    if not product:
        await message.answer("المنتج غير موجود.")
        return

    max_stock = await sync_to_async(get_available_stock_count)(product)
    if max_stock > 0 and qty > max_stock:
        qty = max_stock
        await message.answer(f"ℹ️ تم ضبط الكمية على الحد الأقصى المتوفر حالياً ({max_stock} وحدة).")

    await render_quantity_selector(message, product, user_profile, quantity=qty, is_edit=False)


@router.callback_query(F.data.startswith("buy_confirm:"))
async def handle_confirm_buy(callback: CallbackQuery, user_profile: TelegramProfile, state: FSMContext):
    """Proceed to checkout or request required input for the chosen quantity."""
    await callback.answer()
    parts = callback.data.split(":")
    product_id = parts[1]
    quantity = int(parts[2]) if len(parts) > 2 else 1

    product = await sync_to_async(Product.objects.filter(id=product_id).first)()
    if not product:
        await callback.answer("المنتج غير موجود.", show_alert=True)
        return

    # Check if extra customer input is required
    if product.requires_customer_input:
        import html
        await state.update_data(product_id=str(product.id), quantity=quantity)
        await state.set_state(PurchaseStates.waiting_for_customer_input)
        prompt = product.customer_input_label or "البيانات المطلوبة (مثل: معرف الحساب أو ID اللاعب)"
        await callback.message.answer(
            f"✍️ <b>بيانات مطلوبة لإتمام الشراء (الكمية: {quantity}):</b>\n\n"
            f"يرجى كتابة وإرسال: <b>{html.escape(prompt)}</b>\n"
            f"(أو اكتب <b>إلغاء</b> للتراجع)",
            parse_mode='HTML'
        )
        return

    # Otherwise execute purchase directly with the chosen quantity
    await execute_checkout(callback.message, user_profile, product, quantity=quantity, customer_input="")


@router.message(PurchaseStates.waiting_for_customer_input)
async def handle_purchase_input_received(message: Message, user_profile: TelegramProfile, state: FSMContext):
    """Receive required player ID / email / account data from user and proceed."""
    txt = message.text.strip().lower() if message.text else ""
    if txt in ("/cancel", "إلغاء", "رجوع", "الغاء"):
        await state.clear()
        from apps.telegram_bot.common.keyboards import get_customer_main_menu
        await message.answer("❌ تم إلغاء عملية الشراء.", reply_markup=get_customer_main_menu())
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)
    await state.clear()

    product = await sync_to_async(Product.objects.filter(id=product_id).first)()
    if not product:
        await message.answer("حدث خطأ، المنتج لم يعد متوفراً.")
        return

    customer_input = message.text.strip()
    await execute_checkout(message, user_profile, product, quantity=quantity, customer_input=customer_input)


@router.callback_query(F.data == "noop")
async def handle_noop(callback: CallbackQuery):
    """Ignore clicks on informational buttons."""
    await callback.answer()


async def execute_checkout(target_msg, user_profile: TelegramProfile, product: Product, quantity: int, customer_input: str):
    """Atomic purchase checkout helper."""
    try:
        order, secrets = await sync_to_async(OrderService.process_purchase)(
            user=user_profile,
            product=product,
            quantity=quantity,
            customer_input_data=customer_input
        )

        import html
        prod_name = html.escape(product.name)

        if product.fulfillment_type == 'INVENTORY':
            # Instant delivery
            if secrets:
                secrets_formatted = "\n".join([f"<code>{html.escape(s)}</code>" for s in secrets])
                delivery_body = f"🔑 <b>بيانات المنتج / كود التفعيل:</b>\n{secrets_formatted}"
            else:
                delivery_body = f"📦 <b>الكمية:</b> {quantity} وحدة تم تفعيلها وإضافتها لحسابك بنجاح."

            success_text = (
                f"🎉 <b>تمت عملية الشراء بنجاح!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔖 <b>رقم الطلب:</b> <code>{order.order_number}</code>\n"
                f"🛍 <b>المنتج:</b> {prod_name}\n"
                f"💰 <b>المبلغ المخصوم:</b> <b>{order.total_amount_yer:,.0f} YER</b>\n\n"
                f"{delivery_body}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"احتفظ بهذه البيانات، كما يمكنك الرجوع إليها دائماً من قائمة <b>📦 طلباتي</b>."
            )
            await target_msg.answer(success_text, parse_mode='HTML')

            # Broadcast to public success channel
            try:
                bot = target_msg.bot
                await SuccessChannelService.broadcast_order(bot, order)
            except Exception:
                pass

        elif product.fulfillment_type == 'API':
            # Queue to background worker
            await sync_to_async(FulfillmentService.queue_fulfillment)(order)
            text = (
                f"⏳ <b>تم تأكيد طلبك بنجاح!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔖 <b>رقم الطلب:</b> <code>{order.order_number}</code>\n"
                f"🛍 <b>المنتج:</b> {prod_name}\n"
                f"💰 <b>المبلغ:</b> <b>{order.total_amount_yer:,.0f} YER</b>\n"
                f"⚙️ الحالة: <b>جاري المعالجة والتسليم التلقائي</b>\n\n"
                f"سيصلك إشعار فوري هنا حال اكتمال التنفيذ."
            )
            await target_msg.answer(text, parse_mode='HTML')

        else:
            text = (
                f"✅ <b>تم استلام طلبك بنجاح!</b>\n"
                f"🔖 رقم الطلب: <code>{order.order_number}</code>\n"
                f"الطلب قيد التنفيذ اليدوي من الإدارة وسيتم إشعارك فور اكتماله."
            )
            await target_msg.answer(text, parse_mode='HTML')

    except InsufficientBalanceError:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ شحن رصيد المحفظة الآن", callback_data="wallet_deposit")],
            [InlineKeyboardButton(text="🏠 العودة للرئيسية", callback_data="menu_home")]
        ])
        await target_msg.answer(
            "❌ <b>عذراً، رصيد محفظتك غير كافٍ لإتمام عملية الشراء.</b>\n\n"
            "يرجى شحن محفظتك أولاً ثم إعادة المحاولة:",
            reply_markup=markup,
            parse_mode='HTML'
        )

    except Exception as e:
        await target_msg.answer(f"⚠️ تعذر إتمام الشراء: {str(e)}")
