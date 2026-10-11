import logging
import re
import html
from decimal import Decimal
from typing import List, Tuple, Optional
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from asgiref.sync import sync_to_async
from django.db.models import Sum, Count, Q
from django.utils.text import slugify
from django.conf import settings

from apps.users.models import TelegramProfile
from apps.users.services import AdminAuthService, UserService
from apps.orders.models import Order, OrderItem
from apps.payments.models import PaymentRequest, PaymentMethod
from apps.catalog.models import Product, Category
from apps.inventory.models import StockItem
from apps.inventory.services import InventoryService
from apps.core.models import ExchangeRate, SystemSetting
from apps.core.services import CurrencyService, SystemSettingService
from apps.core.backup_service import DatabaseBackupService
from apps.fulfillment.models import OrderIssue
from apps.notifications.models import RequiredChannel
from apps.notifications.services import RestockNotifierService, ChannelSubscriptionService
from apps.services_app.models import DigitalService, ServiceRequest
from apps.providers.models import ApiProvider, ProviderProductMapping
from apps.providers.services import ProviderDispatcherService
from apps.wallet.models import Wallet, WalletTransaction
from apps.wallet.services import WalletService
from apps.telegram_bot.common.bot_instances import get_customer_bot, get_admin_bot
from apps.telegram_bot.common.keyboards import get_admin_main_menu
from apps.telegram_bot.common.states import (
    AdminExchangeRateStates, 
    AdminStockAddStates,
    AdminAddCategoryStates,
    AdminAddProductStates,
    AdminAddPaymentMethodStates,
    AdminBroadcastStates,
    AdminEditProductPriceStates,
    AdminCustomerSearchStates,
    AdminManualWalletStates,
    AdminAddChannelStates,
    AdminAddDigitalServiceStates,
    AdminProvideQuoteStates,
    AdminMapProductApiStates,
    AdminSettingsStates
)

logger = logging.getLogger(__name__)
router = Router()

def get_admin_dashboard_markup() -> InlineKeyboardMarkup:
    """Rich interactive inline dashboard keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 تحديث الإحصائيات", callback_data="adm_dash_stats"),
            InlineKeyboardButton(text="📥 طلبات الشحن المعلقة", callback_data="adm_deposits_list"),
        ],
        [
            InlineKeyboardButton(text="🛍 إدارة المنتجات", callback_data="adm_prods_list"),
            InlineKeyboardButton(text="🛠 الخدمات الرقمية", callback_data="adm_services_list"),
        ],
        [
            InlineKeyboardButton(text="📂 الأقسام والتصنيفات", callback_data="adm_cats_list"),
            InlineKeyboardButton(text="📦 المخزون المشفر", callback_data="adm_stock_menu"),
        ],
        [
            InlineKeyboardButton(text="💳 طرق الدفع والشحن", callback_data="adm_paymethods_list"),
            InlineKeyboardButton(text="👥 إدارة العملاء والأرصدة", callback_data="adm_users_menu"),
        ],
        [
            InlineKeyboardButton(text="⚙️ إعدادات المتجر والنظام", callback_data="adm_settings_view"),
            InlineKeyboardButton(text="📢 إذاعة وبث جماعي", callback_data="adm_broadcast_prompt"),
        ],

        [
            InlineKeyboardButton(text="📢 القنوات الإجبارية", callback_data="adm_channels_list"),
            InlineKeyboardButton(text="🔌 مزودو الـ API", callback_data="adm_providers_list"),
        ],
        [
            InlineKeyboardButton(text="⚠️ المشاكل الفنية", callback_data="adm_issues_list"),
        ]
    ])


@router.message(CommandStart())
async def handle_admin_start(message: Message):
    """Admin bot welcome and dashboard with persistent menu."""
    is_admin = await sync_to_async(AdminAuthService.is_admin)(message.from_user.id)
    if not is_admin:
        await message.answer("⛔ *عذراً، هذا البوت مخصص للمشرفين وإدارة المتجر فقط.*", parse_mode='Markdown')
        return

    admin_name = message.from_user.full_name or message.from_user.username or "المدير"
    text = (
        f"👑 *مرحباً بك في لوحة تحكم وإدارة المتجر الرقمي*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 المدير الحالي: *{admin_name}*\n"
        f"⚡ الصلاحيات: *Super Admin (تحكم شامل)*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"تحكّم بالمتجر والمنتجات والطلبات والعملاء فورياً من الأزرار أدناه:"
    )
    # Send persistent keyboard first then interactive dashboard
    await message.answer("⚡ تم تجهيز القائمة الرئيسية للوحة التحكم.", reply_markup=get_admin_main_menu())
    await message.answer(text, reply_markup=get_admin_dashboard_markup(), parse_mode='Markdown')


# ==============================================================================
# 1. إحصائيات لوحة التحكم (Live Analytics)
# ==============================================================================
@router.callback_query(F.data == "adm_dash_stats")
@router.message(F.text == "📊 لوحة التحكم والإحصائيات")
async def handle_admin_stats(event: Message | CallbackQuery):
    """Live analytics view."""
    user_id = event.from_user.id
    is_admin = await sync_to_async(AdminAuthService.is_admin)(user_id)
    if not is_admin:
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    def fetch_stats():
        u_cnt = TelegramProfile.objects.count()
        ord_tot = Order.objects.count()
        ord_comp = Order.objects.filter(status='COMPLETED').count()
        ord_proc = Order.objects.filter(status='PROCESSING').count()
        rev = Order.objects.filter(status='COMPLETED').aggregate(s=Sum('total_amount_yer'))['s'] or Decimal('0')
        pend_dep = PaymentRequest.objects.filter(status='PENDING').count()
        issues_cnt = OrderIssue.objects.filter(is_resolved=False).count()
        cats_cnt = Category.objects.filter(is_active=True).count()
        prods_cnt = Product.objects.filter(is_active=True).count()
        rate = ExchangeRate.get_usd_to_yer_rate()
        return u_cnt, ord_tot, ord_comp, ord_proc, rev, pend_dep, issues_cnt, cats_cnt, prods_cnt, rate

    u_cnt, ord_tot, ord_comp, ord_proc, rev, pend_dep, issues_cnt, cats_cnt, prods_cnt, rate = await sync_to_async(fetch_stats)()

    text = (
        f"📊 *لوحة الإحصائيات والأداء المباشر*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 إجمالي العملاء: *{u_cnt:,} عميل*\n"
        f"📦 إجمالي الطلبات: *{ord_tot:,}* (✅ مكتملة: *{ord_comp}* | ⏳ قيد المعالجة: *{ord_proc}*)\n"
        f"💰 إجمالي المبيعات المحققة: *{rev:,.0f} YER*\n"
        f"💳 طلبات شحن بانتظار الاعتماد: *{pend_dep} طلب*\n"
        f"📂 الأقسام المفعلة: *{cats_cnt} قسم*\n"
        f"🛍 المنتجات النشطة: *{prods_cnt} منتج*\n"
        f"⚠️ المشاكل الفنية العالقة: *{issues_cnt}*\n"
        f"💵 سعر صرف الدولار: *1 USD = {rate:,.0f} YER*\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📥 طلبات الشحن المعلقة ({pend_dep})", callback_data="adm_deposits_list")],
        [InlineKeyboardButton(text="🔄 تحديث الأرقام", callback_data="adm_dash_stats")],
        [InlineKeyboardButton(text="🛍 المنتجات", callback_data="adm_prods_list"), InlineKeyboardButton(text="📋 الطلبات", callback_data="adm_orders_list")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])

    if isinstance(event, CallbackQuery):
        try:
            await target.edit_text(text, reply_markup=markup, parse_mode='Markdown')
            await event.answer("✅ تم تحديث الأرقام")
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                await event.answer("📊 الأرقام محدثة بالفعل")
            else:
                raise
    else:
        await target.answer(text, reply_markup=markup, parse_mode='Markdown')


# ==============================================================================
# 2. إدارة الأقسام والتصنيفات (Categories Manager)
# ==============================================================================
@router.callback_query(F.data == "adm_cats_list")
@router.message(F.text == "📂 الأقسام والتصنيفات")
async def handle_categories_list(event: Message | CallbackQuery):
    """View categories with add/manage buttons."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    cats = await sync_to_async(list)(Category.objects.annotate(p_count=Count('products')).order_by('display_order'))

    buttons = []
    text_lines = ["📂 *أقسام وتصنيفات المتجر:*\n━━━━━━━━━━━━━━━━━━"]
    if not cats:
        text_lines.append("لا توجد أقسام مضافة بعد. اضغط أدناه لإضافة أول قسم!")
    else:
        for c in cats:
            status = "🟢" if c.is_active else "🔴"
            text_lines.append(f"{status} {c.icon} *{c.name}* (يحتوي: {c.p_count} منتج)")
            buttons.append([
                InlineKeyboardButton(text=f"⚙️ {c.icon} {c.name}", callback_data=f"adm_cat_view:{c.id}")
            ])

    text_lines.append("━━━━━━━━━━━━━━━━━━")
    buttons.append([InlineKeyboardButton(text="➕ إضافة قسم جديد", callback_data="adm_cat_add")])
    buttons.append([InlineKeyboardButton(text="🏠 عودة للرئيسية", callback_data="adm_home")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(event, CallbackQuery):
        await target.edit_text("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')
    else:
        await target.answer("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')


@router.callback_query(F.data.startswith("adm_cat_view:"))
async def handle_category_view(callback: CallbackQuery):
    """View single category details and actions."""
    await callback.answer()
    cat_id = callback.data.split(":")[1]

    def get_cat_info():
        cat = Category.objects.filter(id=cat_id).first()
        if not cat:
            return None
        prods = list(cat.products.all()[:5])
        prod_names = ", ".join([p.name for p in prods]) if prods else "لا توجد منتجات بعد"
        return cat, prod_names, cat.products.count()

    res = await sync_to_async(get_cat_info)()
    if not res:
        await callback.answer("القسم غير موجود.", show_alert=True)
        return

    cat, prod_names, p_count = res
    status_str = "🟢 مفعل ويظهر بالمتجر" if cat.is_active else "🔴 معطل ومخفي"
    toggle_btn_text = "تعطيل القسم 🔴" if cat.is_active else "تفعيل القسم 🟢"

    text = (
        f"📂 *إدارة القسم:* {cat.icon} *{cat.name}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏷 المعرف (Slug): `{cat.slug}`\n"
        f"⚡ الحالة: *{status_str}*\n"
        f"🛍 عدد المنتجات التابعة: *{p_count}*\n"
        f"📦 عينة منتجات: {prod_names}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    buttons = [
        [InlineKeyboardButton(text=toggle_btn_text, callback_data=f"adm_cat_toggle:{cat.id}")],
        [InlineKeyboardButton(text="🗑️ حذف القسم نهائياً", callback_data=f"adm_cat_delete:{cat.id}")],
        [InlineKeyboardButton(text="🔙 العودة للأقسام", callback_data="adm_cats_list")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode='Markdown')


@router.callback_query(F.data.startswith("adm_cat_toggle:"))
async def handle_category_toggle(callback: CallbackQuery):
    """Toggle category active status."""
    await callback.answer()
    cat_id = callback.data.split(":")[1]

    def toggle():
        c = Category.objects.filter(id=cat_id).first()
        if c:
            c.is_active = not c.is_active
            c.save(update_fields=['is_active', 'updated_at'])
            return c
        return None

    cat = await sync_to_async(toggle)()
    if cat:
        st = "مفعل 🟢" if cat.is_active else "معطل 🔴"
        await callback.answer(f"تم تغيير حالة {cat.name} إلى {st}!", show_alert=True)
    await handle_categories_list(callback)


@router.callback_query(F.data.startswith("adm_cat_delete:"))
async def handle_category_delete(callback: CallbackQuery):
    """Delete a category."""
    await callback.answer()
    cat_id = callback.data.split(":")[1]

    def delete_cat():
        c = Category.objects.filter(id=cat_id).first()
        if c:
            name = c.name
            c.delete()
            return name
        return None

    name = await sync_to_async(delete_cat)()
    if name:
        await callback.answer(f"تم حذف القسم ({name}) بنجاح!", show_alert=True)
    await handle_categories_list(callback)


@router.callback_query(F.data == "adm_cat_add")
async def handle_cat_add_prompt(callback: CallbackQuery, state: FSMContext):
    """Start category add wizard."""
    await callback.answer()
    await state.set_state(AdminAddCategoryStates.waiting_for_name)
    await callback.message.answer(
        "✍️ *الخطوة 1:* اكتب *اسم القسم الجديد* (مثال: شحن ألعاب، بطاقات تسوق، اشتراكات رقمية):",
        parse_mode='Markdown'
    )


@router.message(AdminAddCategoryStates.waiting_for_name)
async def handle_cat_name_entered(message: Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(cat_name=name)
    await state.set_state(AdminAddCategoryStates.waiting_for_icon)
    await message.answer(f"🎨 *الخطوة 2:* أرسل *أيقونة/إيموجي* للقسم (مثال: 🎮 أو 💳 أو 📺 أو 🌐):")


@router.message(AdminAddCategoryStates.waiting_for_icon)
async def handle_cat_icon_entered(message: Message, state: FSMContext):
    icon = message.text.strip()[:10] or "📁"
    data = await state.get_data()
    name = data.get("cat_name")
    await state.clear()

    raw_slug = slugify(name, allow_unicode=True) or "cat"

    def create_cat():
        base_slug = raw_slug
        cnt = 1
        while Category.objects.filter(slug=base_slug).exists():
            base_slug = f"{raw_slug}-{cnt}"
            cnt += 1
        return Category.objects.create(name=name, slug=base_slug, icon=icon, is_active=True)

    cat = await sync_to_async(create_cat)()

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 عرض الأقسام", callback_data="adm_cats_list")],
        [InlineKeyboardButton(text="➕ إضافة قسم آخر", callback_data="adm_cat_add")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])

    await message.answer(
        f"🎉 *تم إنشاء القسم بنجاح!*\n\n"
        f"الاسم: {cat.icon} *{cat.name}*\n"
        f"المعرف: `{cat.slug}`",
        reply_markup=markup,
        parse_mode='Markdown'
    )


# ==============================================================================
# 3. إدارة المنتجات وتعديل الأسعار (Products Manager & Detail Card)
# ==============================================================================
@router.callback_query(F.data == "adm_prods_list")
@router.message(F.text == "🛍 إدارة المنتجات")
async def handle_products_list(event: Message | CallbackQuery):
    """List products with quick detail access."""
    user_id = event.from_user.id
    is_admin = await sync_to_async(AdminAuthService.is_admin)(user_id)
    if not is_admin:
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    products = await sync_to_async(list)(Product.objects.all().order_by('-created_at')[:15])

    buttons = []
    text_lines = ["🛍 *قائمة المنتجات في المتجر:*\n━━━━━━━━━━━━━━━━━━"]
    if not products:
        text_lines.append("لا توجد منتجات مضافة بعد. اضغط أدناه لإضافة أول منتج!")
    else:
        for p in products:
            status = "🟢" if p.is_active else "🔴"
            text_lines.append(f"{status} *{p.name}* | {p.price:,.0f} {p.base_currency} ({p.get_stock_type_display()})")
            buttons.append([
                InlineKeyboardButton(text=f"⚙️ {status} {p.name[:25]}", callback_data=f"adm_prod_card:{p.id}")
            ])

    text_lines.append("━━━━━━━━━━━━━━━━━━")
    buttons.append([InlineKeyboardButton(text="➕ إضافة منتج جديد", callback_data="adm_prod_add_step1")])
    buttons.append([InlineKeyboardButton(text="🏠 عودة للرئيسية", callback_data="adm_home")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(event, CallbackQuery):
        await target.edit_text("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')
    else:
        await target.answer("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')


@router.callback_query(F.data.startswith("adm_prod_card:"))
async def handle_product_card(callback: CallbackQuery):
    """View full product details with edit price, toggle, restock, provider mapping, delete."""
    await callback.answer()
    prod_id = callback.data.split(":")[1]

    def get_prod_details():
        p = Product.objects.prefetch_related('categories').select_related('provider_mapping__provider').filter(id=prod_id).first()
        if not p:
            return None
        cats = ", ".join([c.name for c in p.categories.all()]) or "بدون قسم"
        avail_stock = "0"
        if p.stock_type == 'INDIVIDUAL_ITEMS':
            avail_stock = f"{StockItem.objects.filter(product=p, status='AVAILABLE').count()} عنصر"
        elif p.stock_type == 'QUANTITY':
            avail_stock = f"{p.stock_quantity} قطعة/وحدة"
        elif p.stock_type == 'UNLIMITED':
            avail_stock = "غير محدود (♾️)"
        elif p.stock_type == 'API_CAPACITY':
            avail_stock = "مرتبط بمزود خارجي (API)"
        usd_price = CurrencyService.convert(p.price, from_curr='YER', to_curr='USD') if p.base_currency == 'YER' else p.price
        mapping = getattr(p, 'provider_mapping', None)
        return p, cats, avail_stock, usd_price, mapping

    res = await sync_to_async(get_prod_details)()
    if not res:
        await callback.answer("المنتج غير موجود.", show_alert=True)
        return

    prod, cats, avail_stock, usd_price, mapping = res
    status_str = "🟢 مفعل ومتاح للعملاء" if prod.is_active else "🔴 معطل ومخفي"
    toggle_btn_text = "تعطيل المنتج 🔴" if prod.is_active else "تفعيل المنتج 🟢"

    provider_info_html = ""
    if mapping:
        provider_info_html = (
            f"🔌 <b>المزود الخارجي:</b> {html.escape(mapping.provider.name)} ({html.escape(mapping.provider.provider_code)})\n"
            f"🆔 <b>معرف الخدمة لدى المزود:</b> <code>{html.escape(mapping.external_service_id)}</code>\n"
        )
    elif prod.stock_type == 'API_CAPACITY':
        provider_info_html = "🔌 <b>المزود الخارجي:</b> ⚠️ <i>غير مربوط بمزود حتى الآن!</i>\n"

    input_req_html = ""
    if prod.requires_customer_input:
        lbl = html.escape(prod.customer_input_label or "بيانات مطلوبة")
        input_req_html = f"✍️ <b>مدخلات العميل:</b> نعم ({lbl})\n"
    else:
        input_req_html = "✍️ <b>مدخلات العميل:</b> غير مطلوبة (تلقائي)\n"

    text = (
        f"🛍 <b>بطاقة المنتج:</b> <b>{html.escape(prod.name)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📂 القسم: <b>{html.escape(cats)}</b>\n"
        f"💰 السعر: <b>{prod.price:,.0f} {prod.base_currency}</b> (${usd_price:,.2f} USD)\n"
        f"⚡ الحالة: <b>{status_str}</b>\n"
        f"📦 نوع المخزون: <b>{html.escape(prod.get_stock_type_display())}</b>\n"
        f"🔢 المتوفر حالياً: <b>{avail_stock}</b>\n"
        f"🚀 طريقة التسليم: <b>{html.escape(prod.get_fulfillment_type_display())}</b>\n"
        f"{provider_info_html}"
        f"{input_req_html}"
        f"📝 الوصف: {html.escape(prod.description) if prod.description else 'لا يوجد وصف'}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    btn_api_text = "🔌 ربط بمزود خارجي (API)" if not mapping else f"🔌 إعدادات المزود ({mapping.provider.name[:12]}) ⚙️"
    buttons = [
        [InlineKeyboardButton(text="✏️ تعديل السعر", callback_data=f"adm_prod_editprice:{prod.id}"), InlineKeyboardButton(text=toggle_btn_text, callback_data=f"adm_prod_toggle:{prod.id}")],
        [InlineKeyboardButton(text=btn_api_text, callback_data=f"adm_prod_map_api:{prod.id}")],
        [InlineKeyboardButton(text="📦 تعبئة وتحديث المخزون", callback_data=f"adm_add_stock:{prod.id}")],
        [InlineKeyboardButton(text="🗑️ حذف المنتج نهائياً", callback_data=f"adm_prod_delete:{prod.id}")],
        [InlineKeyboardButton(text="🔙 العودة لقائمة المنتجات", callback_data="adm_prods_list")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode='HTML')


@router.callback_query(F.data.startswith("adm_prod_toggle:"))
async def handle_product_toggle(callback: CallbackQuery):
    """Toggle product active/inactive."""
    await callback.answer()
    prod_id = callback.data.split(":")[1]

    def toggle():
        p = Product.objects.filter(id=prod_id).first()
        if p:
            p.is_active = not p.is_active
            p.save(update_fields=['is_active', 'updated_at'])
            return p
        return None

    prod = await sync_to_async(toggle)()
    if prod:
        st = "مفعل 🟢" if prod.is_active else "معطل 🔴"
        await callback.answer(f"تم تغيير حالة {prod.name} إلى {st}!", show_alert=True)
    await handle_product_card(callback)


@router.callback_query(F.data.startswith("adm_prod_delete:"))
async def handle_product_delete(callback: CallbackQuery):
    """Delete product."""
    await callback.answer()
    prod_id = callback.data.split(":")[1]

    def delete_p():
        p = Product.objects.filter(id=prod_id).first()
        if p:
            name = p.name
            p.delete()
            return name
        return None

    name = await sync_to_async(delete_p)()
    if name:
        try:
            await callback.answer(f"تم حذف المنتج ({name}) بنجاح!", show_alert=True)
        except Exception:
            pass
    await handle_products_list(callback)


@router.callback_query(F.data.startswith("adm_prod_editprice:"))
async def handle_product_edit_price_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompt for new product price."""
    await callback.answer()
    prod_id = callback.data.split(":")[1]
    await state.update_data(edit_prod_id=prod_id)
    await state.set_state(AdminEditProductPriceStates.waiting_for_new_price)
    await callback.message.answer(
        "💰 اكتب *السعر الجديد بالريال اليمني (YER)* للمنتج (مثال: 6000):",
        parse_mode='Markdown'
    )


@router.message(AdminEditProductPriceStates.waiting_for_new_price)
async def handle_product_edit_price_save(message: Message, state: FSMContext):
    """Save updated price."""
    try:
        new_price = Decimal(message.text.strip().replace(",", ""))
        if new_price <= 0:
            raise ValueError()
    except Exception:
        await message.answer("⚠️ يرجى إدخال رقم صحيح وموجب للسعر:")
        return

    data = await state.get_data()
    prod_id = data.get("edit_prod_id")
    await state.clear()

    def update_price():
        p = Product.objects.filter(id=prod_id).first()
        if p:
            p.price = new_price
            p.save(update_fields=['price', 'updated_at'])
            return p
        return None

    prod = await sync_to_async(update_price)()
    if prod:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍 بطاقة المنتج", callback_data=f"adm_prod_card:{prod.id}")],
            [InlineKeyboardButton(text="📋 قائمة المنتجات", callback_data="adm_prods_list")]
        ])
        await message.answer(
            f"✅ *تم تحديث سعر {prod.name} بنجاح!*\nالسعر الجديد: *{prod.price:,.0f} YER*",
            reply_markup=markup,
            parse_mode='Markdown'
        )


# Product Creation Wizard
@router.callback_query(F.data == "adm_prod_add_step1")
async def handle_prod_add_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    cats = await sync_to_async(list)(Category.objects.filter(is_active=True))
    if not cats:
        await callback.message.answer(
            "⚠️ يجب عليك إضافة قسم واحد على الأقل أولاً قبل إضافة المنتجات!\n"
            "اضغط على *📂 الأقسام والتصنيفات* ثم أضف قسماً.",
            parse_mode='Markdown'
        )
        return

    buttons = []
    for c in cats:
        buttons.append([InlineKeyboardButton(text=f"{c.icon} {c.name}", callback_data=f"adm_wiz_cat:{c.id}")])
    buttons.append([InlineKeyboardButton(text="❌ إلغاء", callback_data="adm_prods_list")])

    await state.set_state(AdminAddProductStates.waiting_for_category)
    await callback.message.edit_text(
        "🛍 *معالج إضافة منتج جديد (الخطوة 1/5)*\n\nاختر القسم الذي ينتمي إليه المنتج:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode='Markdown'
    )


@router.callback_query(F.data.startswith("adm_wiz_cat:"), AdminAddProductStates.waiting_for_category)
async def handle_prod_wiz_cat_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    cat_id = callback.data.split(":")[1]
    await state.update_data(cat_id=cat_id)
    await state.set_state(AdminAddProductStates.waiting_for_name)
    await callback.message.answer("✍️ *الخطوة 2/5:* اكتب *اسم المنتج الرقمي* (مثال: اشتراك نتفلكس بريميوم شهر):", parse_mode='Markdown')


@router.message(AdminAddProductStates.waiting_for_name)
async def handle_prod_wiz_name_entered(message: Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(prod_name=name)
    await state.set_state(AdminAddProductStates.waiting_for_desc)
    await message.answer("📝 *الخطوة 3/5:* اكتب *وصفاً للمنتج* يظهر للعميل (أو أرسل نقطة . لتخطي الوصف):", parse_mode='Markdown')


@router.message(AdminAddProductStates.waiting_for_desc)
async def handle_prod_wiz_desc_entered(message: Message, state: FSMContext):
    desc = message.text.strip()
    if desc == ".":
        desc = ""
    await state.update_data(prod_desc=desc)
    await state.set_state(AdminAddProductStates.waiting_for_price)
    await message.answer("💰 *الخطوة 4/5:* اكتب *سعر المنتج بالريال اليمني (YER)* (مثال: 5500):", parse_mode='Markdown')


@router.message(AdminAddProductStates.waiting_for_price)
async def handle_prod_wiz_price_entered(message: Message, state: FSMContext):
    try:
        price = Decimal(message.text.strip().replace(",", ""))
        if price <= 0:
            raise ValueError()
    except Exception:
        await message.answer("⚠️ يرجى إدخال رقم صحيح وموجب للسعر:")
        return

    await state.update_data(prod_price=str(price))
    await state.set_state(AdminAddProductStates.waiting_for_stock_type)

    buttons = [
        [InlineKeyboardButton(text="🔑 حسابات وأكواد فردية مشفرة", callback_data="adm_wiz_stock:INDIVIDUAL_ITEMS")],
        [InlineKeyboardButton(text="🔢 كمية عددية رقمية", callback_data="adm_wiz_stock:QUANTITY")],
        [InlineKeyboardButton(text="🔌 مزود API خارجي", callback_data="adm_wiz_stock:API_CAPACITY")],
        [InlineKeyboardButton(text="♾️ مخزون غير محدود", callback_data="adm_wiz_stock:UNLIMITED")]
    ]
    await message.answer("📦 *الخطوة 5/5:* اختر *نوع المخزون والتسليم*:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode='Markdown')


@router.callback_query(F.data.startswith("adm_wiz_stock:"), AdminAddProductStates.waiting_for_stock_type)
async def handle_prod_wiz_finish(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    stock_type = callback.data.split(":")[1]

    if stock_type == 'API_CAPACITY':
        # Route to external provider setup wizard
        providers = await sync_to_async(list)(ApiProvider.objects.filter(is_active=True))
        if not providers:
            await callback.message.answer(
                "⚠️ <b>لا يوجد أي مزود API خارجي مفعّل في النظام حالياً!</b>\n\n"
                "يرجى أولاً إضافة أو تفعيل مزود خارجي (مثل Vente Bot)، أو اختيار نوع مخزون آخر.",
                parse_mode='HTML'
            )
            return

        await state.update_data(stock_type='API_CAPACITY', fulfillment_type='API')
        await state.set_state(AdminAddProductStates.waiting_for_provider)

        buttons = []
        for prov in providers:
            buttons.append([
                InlineKeyboardButton(
                    text=f"🌐 {prov.name} ({prov.provider_code})",
                    callback_data=f"adm_wiz_prov:{prov.id}"
                )
            ])
        buttons.append([InlineKeyboardButton(text="❌ إلغاء", callback_data="adm_prods_list")])

        await callback.message.edit_text(
            "🔌 <b>معالج إضافة منتج API (الخطوة 5.1/6):</b>\n\n"
            "اختر <b>المزود الخارجي</b> الذي سيتم تنفيذ وشراء هذا المنتج من خلاله تلقائياً:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode='HTML'
        )
        return

    # Non-API stock types: Save product immediately
    data = await state.get_data()
    await state.clear()

    cat_id = data.get("cat_id")
    name = data.get("prod_name")
    desc = data.get("prod_desc", "")
    price = Decimal(data.get("prod_price", "0"))
    fulfillment_type = 'INVENTORY'

    def save_product():
        category = Category.objects.filter(id=cat_id).first()
        prod = Product.objects.create(
            name=name,
            description=desc,
            price=price,
            base_currency='YER',
            stock_type=stock_type,
            fulfillment_type=fulfillment_type,
            is_active=True
        )
        if category:
            prod.categories.add(category)
        return prod

    new_prod = await sync_to_async(save_product)()

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ تعبئة مخزون له الآن", callback_data=f"adm_add_stock:{new_prod.id}")],
        [InlineKeyboardButton(text="🛍 بطاقة المنتج", callback_data=f"adm_prod_card:{new_prod.id}")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])

    await callback.message.edit_text(
        f"🎉 <b>تمت إضافة المنتج بنجاح إلى قاعدة البيانات!</b> ✨\n\n"
        f"🏷 الاسم: <b>{html.escape(new_prod.name)}</b>\n"
        f"💰 السعر: <b>{new_prod.price:,.0f} YER</b>\n"
        f"📦 المخزون: <b>{html.escape(new_prod.get_stock_type_display())}</b>\n"
        f"⚡ التسليم: <b>{html.escape(new_prod.get_fulfillment_type_display())}</b>",
        reply_markup=markup,
        parse_mode='HTML'
    )


# ---------------------------------------------------------
# خطوات معالج إضافة منتج بمزود خارجي (API Provider Wizard)
# ---------------------------------------------------------

@router.callback_query(F.data.startswith("adm_wiz_prov:"), AdminAddProductStates.waiting_for_provider)
async def handle_prod_wiz_provider_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    prov_id = callback.data.split(":")[1]
    provider = await sync_to_async(ApiProvider.objects.filter(id=prov_id).first)()
    if not provider:
        await callback.message.answer("⚠️ المزود المحدد غير موجود.", parse_mode='HTML')
        return

    await state.update_data(provider_id=prov_id, provider_name=provider.name)
    await state.set_state(AdminAddProductStates.waiting_for_external_service_id)

    await callback.message.edit_text(
        f"🆔 <b>معالج إضافة منتج API (الخطوة 5.2/6):</b>\n\n"
        f"المزود المختار: <b>{html.escape(provider.name)}</b>\n\n"
        f"يرجى كتابة وإرسال <b>معرّف الخدمة أو كود المنتج (Service ID / SKU)</b> لدى هذا المزود:\n"
        f"<i>(مثال: <code>pubg_60</code> أو <code>101</code> أو <code>freefire_100</code>)</i>:",
        parse_mode='HTML'
    )


@router.message(AdminAddProductStates.waiting_for_external_service_id)
async def handle_prod_wiz_service_id_entered(message: Message, state: FSMContext):
    service_id = message.text.strip()
    if not service_id:
        await message.answer("⚠️ يرجى إدخال معرّف خدمة صحيح:")
        return

    await state.update_data(external_service_id=service_id)
    await state.set_state(AdminAddProductStates.waiting_for_customer_input_label)

    buttons = [
        [InlineKeyboardButton(text="🎮 معرف اللاعب (Player ID)", callback_data="adm_wiz_input:player_id")],
        [InlineKeyboardButton(text="🔗 رابط الحساب / المنشور (Link)", callback_data="adm_wiz_input:link")],
        [InlineKeyboardButton(text="📱 رقم الهاتف / الحساب", callback_data="adm_wiz_input:phone")],
        [InlineKeyboardButton(text="📧 البريد الإلكتروني (Email)", callback_data="adm_wiz_input:email")],
        [InlineKeyboardButton(text="🚫 لا يتطلب أي بيانات من العميل", callback_data="adm_wiz_input:none")],
    ]

    await message.answer(
        f"✍️ <b>معالج إضافة منتج API (الخطوة 5.3/6):</b>\n\n"
        f"🆔 معرّف الخدمة: <code>{html.escape(service_id)}</code>\n\n"
        f"<b>هل يتطلب هذا المنتج بيانات يدخلها العميل عند الشراء؟</b>\n"
        f"<i>(مثال: شحن الألعاب يتطلب ID اللاعب، خدمات التواصل تتطلب رابط، إلخ)</i>\n\n"
        f"اختر من النماذج الجاهزة أدناه، أو <b>اكتب نص الحقل المطلوب مباشرة</b> في رسالة:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode='HTML'
    )


async def _finalize_api_product_creation(target, state: FSMContext, requires_input: bool, input_label: str):
    data = await state.get_data()
    await state.clear()

    cat_id = data.get("cat_id")
    name = data.get("prod_name")
    desc = data.get("prod_desc", "")
    price = Decimal(data.get("prod_price", "0"))
    provider_id = data.get("provider_id")
    external_service_id = data.get("external_service_id")

    def save_api_product():
        category = Category.objects.filter(id=cat_id).first()
        provider = ApiProvider.objects.filter(id=provider_id).first()
        prod = Product.objects.create(
            name=name,
            description=desc,
            price=price,
            base_currency='YER',
            stock_type='API_CAPACITY',
            fulfillment_type='API',
            requires_customer_input=requires_input,
            customer_input_label=input_label if requires_input else "",
            is_active=True
        )
        if category:
            prod.categories.add(category)

        if provider:
            ProviderProductMapping.objects.create(
                product=prod,
                provider=provider,
                external_service_id=external_service_id
            )
        return prod, provider

    prod, provider = await sync_to_async(save_api_product)()

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 بطاقة المنتج", callback_data=f"adm_prod_card:{prod.id}")],
        [InlineKeyboardButton(text="➕ إضافة منتج آخر", callback_data="adm_prod_add_step1")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])

    prov_name = provider.name if provider else "مزود خارجي"
    cust_input_str = f"نعم ({html.escape(input_label)})" if requires_input else "غير مطلوبة (شراء تلقائي مباشر)"

    success_msg = (
        f"🎉 <b>تم إنشاء وربط المنتج بالمزود بنجاح!</b> ⚡\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🛍 <b>الاسم:</b> <b>{html.escape(prod.name)}</b>\n"
        f"💰 <b>السعر:</b> <b>{prod.price:,.0f} YER</b>\n"
        f"🔌 <b>المزود المربوط:</b> {html.escape(prov_name)}\n"
        f"🆔 <b>معرف الخدمة لدى المزود:</b> <code>{html.escape(external_service_id)}</code>\n"
        f"✍️ <b>مدخلات العميل:</b> {cust_input_str}\n"
        f"🚀 <b>طريقة التسليم:</b> شراء فوري وتلقائي عبر API المزود\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(success_msg, reply_markup=markup, parse_mode='HTML')
    else:
        await target.answer(success_msg, reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data.startswith("adm_wiz_input:"), AdminAddProductStates.waiting_for_customer_input_label)
async def handle_prod_wiz_input_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    preset = callback.data.split(":")[1]
    presets_map = {
        'player_id': (True, "معرف اللاعب (Player ID)"),
        'link': (True, "رابط الحساب أو المنشور"),
        'phone': (True, "رقم الهاتف / الحساب"),
        'email': (True, "البريد الإلكتروني"),
        'none': (False, ""),
    }
    req, lbl = presets_map.get(preset, (False, ""))
    await _finalize_api_product_creation(callback, state, req, lbl)


@router.message(AdminAddProductStates.waiting_for_customer_input_label)
async def handle_prod_wiz_input_message(message: Message, state: FSMContext):
    txt = message.text.strip()
    if txt.lower() in ("لا", "بدون", "لا يوجد", "none", "-", "0"):
        req = False
        lbl = ""
    else:
        req = True
        lbl = txt
    await _finalize_api_product_creation(message, state, req, lbl)


# ---------------------------------------------------------
# ربط / تعديل المزود لمنتج موجود مسبقاً (Map Existing Product)
# ---------------------------------------------------------

@router.callback_query(F.data.startswith("adm_prod_map_api:"))
async def handle_prod_map_api_start(callback: CallbackQuery, state: FSMContext):
    """Start wizard to map an existing product to an external API provider."""
    await callback.answer()
    prod_id = callback.data.split(":")[1]

    def get_prod_and_mapping():
        p = Product.objects.filter(id=prod_id).first()
        if not p:
            return None, None
        m = ProviderProductMapping.objects.filter(product=p).select_related('provider').first()
        return p, m

    prod, mapping = await sync_to_async(get_prod_and_mapping)()
    if not prod:
        await callback.answer("المنتج غير موجود.", show_alert=True)
        return

    providers = await sync_to_async(list)(ApiProvider.objects.filter(is_active=True))
    if not providers:
        await callback.message.answer(
            "⚠️ <b>لا يوجد أي مزود API خارجي مفعّل في النظام حالياً!</b>",
            parse_mode='HTML'
        )
        return

    await state.update_data(map_prod_id=str(prod.id))
    await state.set_state(AdminMapProductApiStates.waiting_for_provider)

    buttons = []
    for prov in providers:
        is_cur = " (الحالي ✅)" if mapping and mapping.provider_id == prov.id else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"🌐 {prov.name} ({prov.provider_code}){is_cur}",
                callback_data=f"adm_map_prov:{prov.id}"
            )
        ])

    if mapping:
        buttons.append([
            InlineKeyboardButton(text="🔓 فك الارتباط بالمزود (تحويل لمخزون عادي)", callback_data=f"adm_map_unlink:{prod.id}")
        ])

    buttons.append([InlineKeyboardButton(text="🔙 العودة لبطاقة المنتج", callback_data=f"adm_prod_card:{prod.id}")])

    cur_status = f"المزود الحالي: <b>{html.escape(mapping.provider.name)}</b> (ID: <code>{html.escape(mapping.external_service_id)}</code>)" if mapping else "المنتج غير مربوط بأي مزود حالياً."

    await callback.message.edit_text(
        f"🔌 <b>ربط وتحديث مزود الـ API للمنتج:</b>\n"
        f"🛍 <b>{html.escape(prod.name)}</b>\n\n"
        f"📌 {cur_status}\n\n"
        f"اختر المزود الذي تود ربط المنتج به:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode='HTML'
    )


@router.callback_query(F.data.startswith("adm_map_unlink:"))
async def handle_prod_map_unlink(callback: CallbackQuery, state: FSMContext):
    """Unlink product from external provider."""
    await callback.answer()
    await state.clear()
    prod_id = callback.data.split(":")[1]

    def unlink():
        p = Product.objects.filter(id=prod_id).first()
        if p:
            ProviderProductMapping.objects.filter(product=p).delete()
            p.stock_type = 'QUANTITY'
            p.fulfillment_type = 'INVENTORY'
            p.requires_customer_input = False
            p.customer_input_label = ""
            p.save(update_fields=['stock_type', 'fulfillment_type', 'requires_customer_input', 'customer_input_label', 'updated_at'])
            return p.name
        return None

    name = await sync_to_async(unlink)()
    if name:
        await callback.answer("✅ تم فك ارتباط المنتج بالمزود وتحويله لمخزون داخلي.", show_alert=True)
    await handle_product_card(callback)


@router.callback_query(F.data.startswith("adm_map_prov:"), AdminMapProductApiStates.waiting_for_provider)
async def handle_prod_map_prov_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    prov_id = callback.data.split(":")[1]
    provider = await sync_to_async(ApiProvider.objects.filter(id=prov_id).first)()
    if not provider:
        await callback.message.answer("⚠️ المزود المحدد غير موجود.", parse_mode='HTML')
        return

    await state.update_data(provider_id=prov_id, provider_name=provider.name)
    await state.set_state(AdminMapProductApiStates.waiting_for_external_service_id)

    await callback.message.edit_text(
        f"🆔 <b>ربط مزود الـ API (الخطوة 2/3):</b>\n\n"
        f"المزود المختار: <b>{html.escape(provider.name)}</b>\n\n"
        f"يرجى كتابة وإرسال <b>معرّف الخدمة أو كود المنتج (Service ID / SKU)</b> لدى هذا المزود:\n"
        f"<i>(مثال: <code>pubg_60</code> أو <code>101</code> أو <code>netflix_1m</code>)</i>:",
        parse_mode='HTML'
    )


@router.message(AdminMapProductApiStates.waiting_for_external_service_id)
async def handle_prod_map_service_id_entered(message: Message, state: FSMContext):
    service_id = message.text.strip()
    if not service_id:
        await message.answer("⚠️ يرجى إدخال معرّف خدمة صحيح:")
        return

    await state.update_data(external_service_id=service_id)
    await state.set_state(AdminMapProductApiStates.waiting_for_customer_input_label)

    buttons = [
        [InlineKeyboardButton(text="🎮 معرف اللاعب (Player ID)", callback_data="adm_map_input:player_id")],
        [InlineKeyboardButton(text="🔗 رابط الحساب / المنشور (Link)", callback_data="adm_map_input:link")],
        [InlineKeyboardButton(text="📱 رقم الهاتف / الحساب", callback_data="adm_map_input:phone")],
        [InlineKeyboardButton(text="📧 البريد الإلكتروني (Email)", callback_data="adm_map_input:email")],
        [InlineKeyboardButton(text="🚫 لا يتطلب أي بيانات من العميل", callback_data="adm_map_input:none")],
    ]

    await message.answer(
        f"✍️ <b>ربط مزود الـ API (الخطوة 3/3):</b>\n\n"
        f"🆔 معرّف الخدمة: <code>{html.escape(service_id)}</code>\n\n"
        f"<b>هل يتطلب هذا المنتج بيانات يدخلها العميل عند الشراء؟</b>\n"
        f"اختر من الخيارات السريعة، أو <b>اكتب التسمية مباشرة</b> في رسالة:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode='HTML'
    )


async def _finalize_existing_product_mapping(target, state: FSMContext, requires_input: bool, input_label: str):
    data = await state.get_data()
    await state.clear()

    prod_id = data.get("map_prod_id")
    provider_id = data.get("provider_id")
    external_service_id = data.get("external_service_id")

    def save_mapping():
        p = Product.objects.filter(id=prod_id).first()
        provider = ApiProvider.objects.filter(id=provider_id).first()
        if not p or not provider:
            return None, None

        p.stock_type = 'API_CAPACITY'
        p.fulfillment_type = 'API'
        p.requires_customer_input = requires_input
        p.customer_input_label = input_label if requires_input else ""
        p.save(update_fields=['stock_type', 'fulfillment_type', 'requires_customer_input', 'customer_input_label', 'updated_at'])

        mapping, _ = ProviderProductMapping.objects.update_or_create(
            product=p,
            defaults={
                'provider': provider,
                'external_service_id': external_service_id
            }
        )
        return p, provider

    prod, provider = await sync_to_async(save_mapping)()
    if not prod:
        msg = "⚠️ حدث خطأ أثناء حفظ الربط، المنتج غير موجود."
        if isinstance(target, CallbackQuery):
            await target.message.answer(msg)
        else:
            await target.answer(msg)
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 العودة لبطاقة المنتج", callback_data=f"adm_prod_card:{prod.id}")],
        [InlineKeyboardButton(text="📋 قائمة المنتجات", callback_data="adm_prods_list")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])

    cust_input_str = f"نعم ({html.escape(input_label)})" if requires_input else "غير مطلوبة"

    text = (
        f"✅ <b>تم تحديث ربط المنتج بالمزود الخارجي بنجاح!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🛍 <b>المنتج:</b> <b>{html.escape(prod.name)}</b>\n"
        f"🔌 <b>المزود:</b> {html.escape(provider.name)}\n"
        f"🆔 <b>معرف الخدمة:</b> <code>{html.escape(external_service_id)}</code>\n"
        f"✍️ <b>مدخلات العميل:</b> {cust_input_str}\n"
        f"⚡ <b>نوع التسليم:</b> شراء فوري عبر API المزود\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup, parse_mode='HTML')
    else:
        await target.answer(text, reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data.startswith("adm_map_input:"), AdminMapProductApiStates.waiting_for_customer_input_label)
async def handle_prod_map_input_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    preset = callback.data.split(":")[1]
    presets_map = {
        'player_id': (True, "معرف اللاعب (Player ID)"),
        'link': (True, "رابط الحساب أو المنشور"),
        'phone': (True, "رقم الهاتف / الحساب"),
        'email': (True, "البريد الإلكتروني"),
        'none': (False, ""),
    }
    req, lbl = presets_map.get(preset, (False, ""))
    await _finalize_existing_product_mapping(callback, state, req, lbl)


@router.message(AdminMapProductApiStates.waiting_for_customer_input_label)
async def handle_prod_map_input_message(message: Message, state: FSMContext):
    txt = message.text.strip()
    if txt.lower() in ("لا", "بدون", "لا يوجد", "none", "-", "0"):
        req = False
        lbl = ""
    else:
        req = True
        lbl = txt
    await _finalize_existing_product_mapping(message, state, req, lbl)


# ---------------------------------------------------------
# قائمة وإدارة مزودي الـ API في لوحة التحكم (Providers List)
# ---------------------------------------------------------

@router.callback_query(F.data == "adm_providers_list")
@router.message(F.text == "🔌 مزودو الـ API الخارجيون")
async def handle_admin_providers_list(event: Message | CallbackQuery):
    """View and manage external API providers, their status, balance, and mapped products."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    def get_providers_data():
        providers = list(ApiProvider.objects.all())
        results = []
        for p in providers:
            mapped_count = p.product_mappings.count()
            results.append((p, mapped_count))
        return results

    providers_data = await sync_to_async(get_providers_data)()

    if not providers_data:
        text = (
            "🔌 <b>مزودو الـ API الخارجيون</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⚠️ لا يوجد أي مزود معرف في النظام حتى الآن."
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
        ])
    else:
        text_lines = [
            "🔌 <b>إدارة مزودي الـ API الخارجيين:</b>",
            "━━━━━━━━━━━━━━━━━━"
        ]
        buttons = []
        for prov, mapped_cnt in providers_data:
            st_icon = "🟢" if prov.is_active else "🔴"
            st_text = "نشط" if prov.is_active else "معطل"
            text_lines.append(
                f"{st_icon} <b>{html.escape(prov.name)}</b> (<code>{html.escape(prov.provider_code)}</code>)\n"
                f"   ⚡ النوع: {prov.get_provider_type_display()}\n"
                f"   📦 المنتجات المربوطة: <b>{mapped_cnt} منتج</b>\n"
                f"   🌐 الرابط: <code>{html.escape(prov.base_url or 'افتراضي')}</code>"
            )
            buttons.append([
                InlineKeyboardButton(text=f"💰 رصيد {prov.name[:12]}", callback_data=f"adm_prov_bal:{prov.id}"),
                InlineKeyboardButton(text=f"{st_icon} {st_text}", callback_data=f"adm_prov_toggle:{prov.id}")
            ])
        text_lines.append("━━━━━━━━━━━━━━━━━━")
        buttons.append([InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")])
        text = "\n".join(text_lines)
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(event, CallbackQuery):
        await target.edit_text(text, reply_markup=markup, parse_mode='HTML')
    else:
        await target.answer(text, reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data.startswith("adm_prov_bal:"))
async def handle_admin_provider_balance(callback: CallbackQuery):
    """Check live wallet balance at external API provider."""
    await callback.answer("⏳ جاري الاستعلام عن الرصيد من المزود...", show_alert=False)
    prov_id = callback.data.split(":")[1]

    def check_bal():
        prov = ApiProvider.objects.filter(id=prov_id).first()
        if not prov:
            return None, "المزود غير موجود"
        try:
            adapter = ProviderDispatcherService.get_adapter(prov)
            bal = adapter.get_balance()
            return prov, bal
        except Exception as e:
            return prov, f"خطأ: {e}"

    prov, bal_result = await sync_to_async(check_bal)()
    if not prov:
        await callback.answer("المزود غير موجود.", show_alert=True)
        return

    await callback.answer(
        f"💰 رصيدك لدى {prov.name}:\n{bal_result}",
        show_alert=True
    )


@router.callback_query(F.data.startswith("adm_prov_toggle:"))
async def handle_admin_provider_toggle(callback: CallbackQuery):
    """Toggle provider active status."""
    await callback.answer()
    prov_id = callback.data.split(":")[1]

    def toggle_prov():
        p = ApiProvider.objects.filter(id=prov_id).first()
        if p:
            p.is_active = not p.is_active
            p.save(update_fields=['is_active', 'updated_at'])
            return p
        return None

    p = await sync_to_async(toggle_prov)()
    if p:
        st = "مفعّل 🟢" if p.is_active else "معطّل 🔴"
        await callback.answer(f"تم تغيير حالة المزود إلى {st}", show_alert=True)
    await handle_admin_providers_list(callback)


# ==============================================================================
# 4. إدارة المخزون المشفر (Encrypted Stock Manager)
# ==============================================================================
@router.callback_query(F.data == "adm_stock_menu")
@router.message(F.text == "📦 إدارة المخزون المشفر")
async def handle_admin_inventory(event: Message | CallbackQuery):
    """Manage stock and select product for filling."""
    user_id = event.from_user.id
    is_admin = await sync_to_async(AdminAuthService.is_admin)(user_id)
    if not is_admin:
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    def get_stock_products():
        prods = list(Product.objects.filter(stock_type__in=['INDIVIDUAL_ITEMS', 'QUANTITY'], is_active=True))
        result = []
        for p in prods:
            if p.stock_type == 'INDIVIDUAL_ITEMS':
                avail = StockItem.objects.filter(product=p, status='AVAILABLE').count()
                sold = StockItem.objects.filter(product=p, status='SOLD').count()
            else:
                avail = p.stock_quantity
                sold = 0
            result.append((p, avail, sold))
        return result

    items = await sync_to_async(get_stock_products)()

    if not items:
        text = "⚠️ لا توجد منتجات (أكواد أو كميات عددية) لإضافة مخزون لها حالياً. أضف منتجاً أولاً!"
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]])
        if isinstance(event, CallbackQuery):
            await target.edit_text(text, reply_markup=markup, parse_mode='Markdown')
        else:
            await target.answer(text, reply_markup=markup, parse_mode='Markdown')
        return

    buttons = []
    text_lines = ["📦 *حالة المخزون للمنتجات:*\n━━━━━━━━━━━━━━━━━━"]
    for prod, avail, sold in items:
        badge = "🟢" if avail > 0 else "🔴"
        st_type = "مشفر" if prod.stock_type == 'INDIVIDUAL_ITEMS' else "كمية"
        text_lines.append(f"{badge} *{prod.name}* ({st_type})\nالمتوفر: `{avail}` | المباع: `{sold}`\n")
        buttons.append([InlineKeyboardButton(text=f"➕ تعبئة: {prod.name[:25]}", callback_data=f"adm_add_stock:{prod.id}")])

    text_lines.append("━━━━━━━━━━━━━━━━━━")
    buttons.append([InlineKeyboardButton(text="🧹 تنظيف المخزون المباع", callback_data="adm_stock_cleanup")])
    buttons.append([InlineKeyboardButton(text="🏠 عودة للرئيسية", callback_data="adm_home")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(event, CallbackQuery):
        await target.edit_text("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')
    else:
        await target.answer("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')


@router.callback_query(F.data.startswith("adm_add_stock:"))
async def handle_stock_add_select(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    product_id = callback.data.split(":")[1]
    product = await sync_to_async(Product.objects.filter(id=product_id).first)()
    if not product:
        await callback.answer("المنتج غير موجود.", show_alert=True)
        return

    await state.update_data(product_id=str(product.id))
    await state.set_state(AdminStockAddStates.waiting_for_items_text)

    if product.stock_type == 'QUANTITY':
        text = (
            f"🔢 *تعبئة مخزون رقمي لمنتج: {product.name}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"المتوفر حالياً: *{product.stock_quantity} قطعة/وحدة*\n\n"
            f"أرسل *الكمية العددية* المطلوب إضافتها إلى المخزون (مثال: 50):"
        )
    else:
        text = (
            f"✍️ *تعبئة مخزون مشفر لمنتج: {product.name}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"أرسل الأكواد أو الحسابات (كل عنصر في سطر منفصل):\n\n"
            f"مثال:\n"
            f"`user1@vip.com:pass123`\n"
            f"`user2@vip.com:pass456`\n"
            f"`CODE-XYZ-12345`\n\n"
            f"🔒 *تشفير آلي:* سيتم تشفيرها فوراً بتقنية Fernet قبل حفظها بقاعدة البيانات."
        )
    await callback.message.answer(text, parse_mode='Markdown')


@router.message(AdminStockAddStates.waiting_for_items_text)
async def handle_stock_add_save(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("product_id")
    await state.clear()

    product = await sync_to_async(Product.objects.filter(id=product_id).first)()
    if not product:
        await message.answer("⚠️ المنتج غير موجود.")
        return

    if product.stock_type == 'QUANTITY':
        try:
            qty_add = int(message.text.strip().replace(",", ""))
            if qty_add <= 0:
                raise ValueError()
        except Exception:
            await message.answer("⚠️ يرجى إدخال رقم صحيح وموجب للكمية (مثال: 25).")
            return

        def add_qty():
            product.stock_quantity += qty_add
            product.save(update_fields=['stock_quantity', 'updated_at'])
            return product.stock_quantity

        total_qty = await sync_to_async(add_qty)()
        notified_count = await RestockNotifierService.notify_subscribers(product)

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 إدارة المخزون", callback_data="adm_stock_menu")],
            [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
        ])

        alert_info = f"\n🔔 تم إرسال إشعار فوري إلى *{notified_count}* عميل من المشتركين بتنبيهات هذا المنتج!" if notified_count > 0 else ""

        await message.answer(
            f"✅ *تمت إضافة {qty_add} وحدة بنجاح إلى مخزون {product.name}!* 🎉\n"
            f"المخزون الإجمالي المتوفر الآن: *{total_qty} وحدة*{alert_info}",
            reply_markup=markup,
            parse_mode='Markdown'
        )
        return

    lines = [line.strip() for line in message.text.split("\n") if line.strip()]
    if not lines:
        await message.answer("⚠️ لم يتم استلام أي أسطر صالحة.")
        return

    count = await sync_to_async(InventoryService.bulk_add_individual_items)(product, lines)
    notified_count = await RestockNotifierService.notify_subscribers(product)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 إدارة المخزون", callback_data="adm_stock_menu")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])

    alert_info = f"\n🔔 تم إرسال إشعار فوري إلى *{notified_count}* عميل من المشتركين بتنبيهات هذا المنتج!" if notified_count > 0 else ""

    await message.answer(
        f"✅ *تم تشفير وحفظ {count} عنصر بنجاح في مخزون {product.name}!* 🎉\n"
        f"أصبح المنتج متاحاً للشراء الفوري الآن للعملاء.{alert_info}",
        reply_markup=markup,
        parse_mode='Markdown'
    )


@router.callback_query(F.data == "adm_stock_cleanup")
async def handle_stock_cleanup(callback: CallbackQuery):
    """Purge sold stock items to keep database lean."""
    await callback.answer()
    
    def cleanup():
        return StockItem.objects.filter(status='SOLD').delete()[0]

    cnt = await sync_to_async(cleanup)()
    await callback.answer(f"تم حذف {cnt} عنصر مباع بنجاح لتنظيف قاعدة البيانات!", show_alert=True)
    await handle_admin_inventory(callback)


# ==============================================================================
# 5. سجل وإدارة الطلبات (Orders Management)
# ==============================================================================
@router.callback_query(F.data == "adm_orders_list")
@router.message(F.text == "📋 سجل وإدارة الطلبات")
async def handle_admin_orders_list(event: Message | CallbackQuery):
    """View recent orders in the store."""
    user_id = event.from_user.id
    is_admin = await sync_to_async(AdminAuthService.is_admin)(user_id)
    if not is_admin:
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    def get_orders():
        orders = list(Order.objects.select_related('user').prefetch_related('items').order_by('-created_at')[:10])
        res = []
        for o in orders:
            item = o.items.first()
            p_name = item.product_name_snapshot if item else "طلب"
            u_name = o.user.full_name if o.user else "عميل"
            res.append((o.id, o.order_number, p_name, u_name, o.total_amount_yer, o.status, o.get_status_display()))
        return res

    orders_data = await sync_to_async(get_orders)()

    buttons = []
    text_lines = ["📋 *سجل آخر طلبات المتجر:*\n━━━━━━━━━━━━━━━━━━"]
    if not orders_data:
        text_lines.append("لا توجد طلبات مسجلة في المتجر حتى الآن.")
    else:
        for oid, onum, pname, uname, total, st, st_display in orders_data:
            badge = "✅" if st == 'COMPLETED' else ("⏳" if st == 'PROCESSING' else "🔴")
            text_lines.append(f"{badge} `{onum}` | *{pname}*\n👤 {uname} | 💰 {total:,.0f} YER [{st_display}]\n")
            buttons.append([
                InlineKeyboardButton(text=f"🔍 طلب #{onum} ({st_display})", callback_data=f"adm_ord_view:{oid}")
            ])

    text_lines.append("━━━━━━━━━━━━━━━━━━")
    buttons.append([InlineKeyboardButton(text="🔄 تحديث الطلبات", callback_data="adm_orders_list")])
    buttons.append([InlineKeyboardButton(text="🏠 عودة للرئيسية", callback_data="adm_home")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(event, CallbackQuery):
        await target.edit_text("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')
    else:
        await target.answer("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')


@router.callback_query(F.data.startswith("adm_ord_view:"))
async def handle_admin_order_view(callback: CallbackQuery):
    """View single order details with customer contact and secrets."""
    await callback.answer()
    order_id = callback.data.split(":")[1]

    def get_order_details():
        o = Order.objects.select_related('user').prefetch_related('items').filter(id=order_id).first()
        if not o:
            return None
        item = o.items.first()
        pname = item.product_name_snapshot if item else "منتج رقمي"
        qty = item.quantity if item else 1
        date_str = o.created_at.strftime("%Y-%m-%d %I:%M %p")
        return {
            'order_number': o.order_number,
            'user_name': o.user.full_name,
            'telegram_id': o.user.telegram_id,
            'username': o.user.username or "لا يوجد",
            'product_name': pname,
            'qty': qty,
            'total_amount': o.total_amount_yer,
            'status': o.status,
            'status_display': o.get_status_display(),
            'delivered_data': o.delivered_data,
            'customer_input': o.customer_input_data,
            'date_str': date_str,
            'id': str(o.id)
        }

    d = await sync_to_async(get_order_details)()
    if not d:
        await callback.answer("الطلب غير موجود.", show_alert=True)
        return

    text = (
        f"🔖 *تفاصيل الطلب: {d['order_number']}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 العميل: *{d['user_name']}* (`{d['telegram_id']}`)\n"
        f"📩 المعرف: @{d['username']}\n"
        f"🛍 المنتج: *{d['product_name']}* (كمية: {d['qty']})\n"
        f"💰 القيمة: *{d['total_amount']:,.0f} YER*\n"
        f"⚡ الحالة: *{d['status_display']}*\n"
        f"📅 التاريخ: `{d['date_str']}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )

    if d['customer_input']:
        text += f"📝 بيانات مرسلة من العميل: `{d['customer_input']}`\n\n"

    if d['delivered_data']:
        text += f"🔑 البيانات المسلمة للعميل:\n`{d['delivered_data']}`\n"

    buttons = [
        [InlineKeyboardButton(text="🔙 العودة للطلبات", callback_data="adm_orders_list")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode='Markdown')


# ==============================================================================
# 6. إدارة العملاء والأرصدة اليدوية (Customers & Manual Wallet Engine)
# ==============================================================================
@router.callback_query(F.data == "adm_users_menu")
@router.message(F.text == "👥 إدارة العملاء والأرصدة")
async def handle_admin_users_menu(event: Message | CallbackQuery):
    """Customer management hub."""
    user_id = event.from_user.id
    is_admin = await sync_to_async(AdminAuthService.is_admin)(user_id)
    if not is_admin:
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    def get_users_summary():
        total_users = TelegramProfile.objects.count()
        total_balance = Wallet.objects.aggregate(s=Sum('balance_yer'))['s'] or Decimal('0')
        recent_users = list(TelegramProfile.objects.order_by('-created_at')[:6])
        return total_users, total_balance, recent_users

    total_users, total_balance, recent_users = await sync_to_async(get_users_summary)()

    text_lines = [
        f"👥 *إدارة العملاء والمحافظ المالية*\n━━━━━━━━━━━━━━━━━━",
        f"👥 إجمالي العملاء المسجلين: *{total_users:,} عميل*",
        f"💰 إجمالي الأرصدة في محافظ العملاء: *{total_balance:,.0f} YER*\n",
        f"🆕 *آخر المنضمين للمتجر:*"
    ]
    for u in recent_users:
        text_lines.append(f"• {u.full_name} (`{u.telegram_id}`)")

    text_lines.append("━━━━━━━━━━━━━━━━━━\nابحث عن أي عميل بواسطة الـ ID لشحن رصيده أو خصم رصيد يدوياً:")

    buttons = [
        [InlineKeyboardButton(text="🔍 البحث عن عميل بالـ ID", callback_data="adm_cust_search")],
        [InlineKeyboardButton(text="🏠 العودة للرئيسية", callback_data="adm_home")]
    ]

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(event, CallbackQuery):
        await target.edit_text("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')
    else:
        await target.answer("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')


@router.callback_query(F.data == "adm_cust_search")
async def handle_cust_search_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompt for customer telegram ID."""
    await callback.answer()
    await state.set_state(AdminCustomerSearchStates.waiting_for_query)
    await callback.message.answer(
        "🔍 اكتب *معرف التليجرام الرقمي (Telegram ID)* أو اسم المستخدم للعميل:",
        parse_mode='Markdown'
    )


@router.message(AdminCustomerSearchStates.waiting_for_query)
async def handle_cust_search_find(message: Message, state: FSMContext):
    query = message.text.strip().lstrip("@")
    await state.clear()

    def find_user():
        if query.isdigit():
            p = TelegramProfile.objects.filter(telegram_id=int(query)).first()
        else:
            p = TelegramProfile.objects.filter(username__iexact=query).first()
        if not p:
            return None
        w = Wallet.objects.filter(profile=p).first()
        bal = w.balance_yer if w else Decimal('0')
        usd_bal = CurrencyService.convert(bal, from_curr='YER', to_curr='USD')
        orders_cnt = Order.objects.filter(user=p).count()
        return p, bal, usd_bal, orders_cnt

    res = await sync_to_async(find_user)()
    if not res:
        await message.answer(f"❌ لم يتم العثور على أي عميل يطابق `{query}`.")
        return

    profile, bal, usd_bal, orders_cnt = res
    text = (
        f"👤 *ملف العميل: {profile.full_name}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 معرف التليجرام: `{profile.telegram_id}`\n"
        f"📩 اسم المستخدم: @{profile.username or 'لا يوجد'}\n"
        f"💰 الرصيد الحالي: *{bal:,.0f} YER* (${usd_bal:,.2f})\n"
        f"📦 إجمالي طلباته: *{orders_cnt} طلب*\n"
        f"📅 تاريخ التسجيل: `{profile.created_at.strftime('%Y-%m-%d')}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"اختر إجراءً للتحكم بمحفظة العميل:"
    )

    buttons = [
        [InlineKeyboardButton(text="➕ شحن رصيد يدوي", callback_data=f"adm_cust_credit:{profile.telegram_id}"), InlineKeyboardButton(text="➖ خصم رصيد يدوي", callback_data=f"adm_cust_debit:{profile.telegram_id}")],
        [InlineKeyboardButton(text="👥 إدارة العملاء", callback_data="adm_users_menu"), InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode='Markdown')


@router.callback_query(F.data.startswith("adm_cust_credit:"))
async def handle_cust_credit_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tid = callback.data.split(":")[1]
    await state.update_data(target_telegram_id=tid, action='CREDIT')
    await state.set_state(AdminManualWalletStates.waiting_for_amount)
    await callback.message.answer(f"➕ اكتب *المبلغ المراد إيداعه* بالريال اليمني في محفظة العميل `{tid}`:")


@router.callback_query(F.data.startswith("adm_cust_debit:"))
async def handle_cust_debit_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tid = callback.data.split(":")[1]
    await state.update_data(target_telegram_id=tid, action='DEBIT')
    await state.set_state(AdminManualWalletStates.waiting_for_amount)
    await callback.message.answer(f"➖ اكتب *المبلغ المراد خصمه* بالريال اليمني من محفظة العميل `{tid}`:")


@router.message(AdminManualWalletStates.waiting_for_amount)
async def handle_cust_wallet_execute(message: Message, state: FSMContext, bot):
    try:
        amount = Decimal(message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError()
    except Exception:
        await message.answer("⚠️ يرجى إدخال مبلغ صحيح بالأرقام فقط:")
        return

    data = await state.get_data()
    tid = int(data.get("target_telegram_id"))
    action = data.get("action")
    await state.clear()

    def do_action():
        p = TelegramProfile.objects.filter(telegram_id=tid).first()
        if not p:
            return None, "العميل غير موجود"
        w = WalletService.get_or_create_wallet(p)
        if action == 'CREDIT':
            tx, _ = WalletService.deposit(w, amount, reference_id="ADMIN-ADJ", description="إيداع رصيد يدوي من إدارة المتجر")
            return w.balance_yer, "تم إيداع الرصيد بنجاح"
        else:
            tx, _ = WalletService.debit(w, amount, reference_id="ADMIN-ADJ", description="خصم رصيد يدوي من إدارة المتجر")
            return w.balance_yer, "تم خصم الرصيد بنجاح"

    try:
        new_bal, msg = await sync_to_async(do_action)()
        if new_bal is None:
            await message.answer(f"❌ {msg}")
            return

        await message.answer(
            f"✅ *{msg}!*\n"
            f"الرصيد الجديد للعميل: *{new_bal:,.0f} YER*",
            parse_mode='Markdown'
        )

        # Notify customer if credit
        try:
            from apps.telegram_bot.common.bot_instances import get_customer_bot
            cust_bot = get_customer_bot()
            if cust_bot:
                sign_str = f"+{amount:,.0f} YER" if action == 'CREDIT' else f"-{amount:,.0f} YER"
                cust_notify = (
                    f"💳 *إشعار تعديل رصيد المحفظة*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"تم تعديل رصيدك بواسطة الإدارة بمقدار: *{sign_str}*\n"
                    f"رصيدك الحالي الآن: *{new_bal:,.0f} YER*\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                await cust_bot.send_message(chat_id=tid, text=cust_notify, parse_mode='Markdown')
        except Exception:
            pass

    except Exception as e:
        await message.answer(f"⚠️ فشلت العملية: {str(e)}")


# ==============================================================================
# 7. طرق الدفع والشحن (Payment Methods Manager)
# ==============================================================================
@router.callback_query(F.data == "adm_paymethods_list")
@router.message(F.text == "💳 طرق الدفع والشحن")
async def handle_payment_methods_manager(event: Message | CallbackQuery):
    """View and manage payment methods."""
    user_id = event.from_user.id
    is_admin = await sync_to_async(AdminAuthService.is_admin)(user_id)
    if not is_admin:
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    methods = await sync_to_async(list)(PaymentMethod.objects.all().order_by('display_order'))

    buttons = []
    text_lines = ["💳 *طرق الدفع والشحن في المتجر:*\n━━━━━━━━━━━━━━━━━━"]
    if not methods:
        text_lines.append("لا توجد طرق دفع مضافة بعد. اضغط أدناه لإضافة أول طريقة دفع!")
    else:
        for m in methods:
            status = "🟢 مفعلة" if m.is_active else "🔴 معطلة"
            text_lines.append(f"{m.icon} *{m.name}* [{status}]\nالحساب: `{m.account_number}` | المستفيد: {m.account_name}\n")
            action = "تعطيل 🔴" if m.is_active else "تفعيل 🟢"
            buttons.append([
                InlineKeyboardButton(text=f"{m.icon} {m.name} ({action})", callback_data=f"adm_pay_toggle:{m.id}"),
                InlineKeyboardButton(text="🗑️", callback_data=f"adm_pay_del:{m.id}")
            ])

    text_lines.append("━━━━━━━━━━━━━━━━━━")
    buttons.append([InlineKeyboardButton(text="📥 طلبات الشحن بانتظار المراجعة", callback_data="adm_deposits_list")])
    buttons.append([InlineKeyboardButton(text="➕ إضافة وسيلة دفع جديدة", callback_data="adm_pay_add")])
    buttons.append([InlineKeyboardButton(text="🏠 عودة للرئيسية", callback_data="adm_home")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(event, CallbackQuery):
        await target.edit_text("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')
    else:
        await target.answer("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')


@router.callback_query(F.data.startswith("adm_pay_toggle:"))
async def handle_payment_toggle(callback: CallbackQuery):
    await callback.answer()
    method_id = callback.data.split(":")[1]

    def toggle(m_id):
        m = PaymentMethod.objects.filter(id=m_id).first()
        if m:
            m.is_active = not m.is_active
            m.save(update_fields=['is_active', 'updated_at'])
            return m
        return None

    m = await sync_to_async(toggle)(method_id)
    if m:
        st = "مفعلة 🟢" if m.is_active else "معطلة 🔴"
        await callback.answer(f"تم تحويل {m.name} إلى {st}!", show_alert=True)
    await handle_payment_methods_manager(callback)


@router.callback_query(F.data.startswith("adm_pay_del:"))
async def handle_payment_delete(callback: CallbackQuery):
    await callback.answer()
    method_id = callback.data.split(":")[1]

    def del_m():
        m = PaymentMethod.objects.filter(id=method_id).first()
        if m:
            name = m.name
            m.delete()
            return name
        return None

    name = await sync_to_async(del_m)()
    if name:
        await callback.answer(f"تم حذف {name} بنجاح!", show_alert=True)
    await handle_payment_methods_manager(callback)


@router.callback_query(F.data == "adm_pay_add")
async def handle_payment_add_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminAddPaymentMethodStates.waiting_for_name)
    await callback.message.answer(
        "💳 *إضافة وسيلة دفع جديدة (الخطوة 1/4)*\n\n"
        "اكتب *اسم طريقة الدفع* (مثال: بنك الكريمي - حاسب، محفظة جيب، ون كاش):",
        parse_mode='Markdown'
    )


@router.message(AdminAddPaymentMethodStates.waiting_for_name)
async def handle_pay_name_entered(message: Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(pay_name=name)
    await state.set_state(AdminAddPaymentMethodStates.waiting_for_account)
    await message.answer("🔢 *الخطوة 2/4:* اكتب *رقم الحساب أو رقم النقطة/المحفظة*:")


@router.message(AdminAddPaymentMethodStates.waiting_for_account)
async def handle_pay_account_entered(message: Message, state: FSMContext):
    acc = message.text.strip()
    await state.update_data(pay_account=acc)
    await state.set_state(AdminAddPaymentMethodStates.waiting_for_account_name)
    await message.answer("👤 *الخطوة 3/4:* اكتب *اسم صاحب الحساب أو المستفيد*:")


@router.message(AdminAddPaymentMethodStates.waiting_for_account_name)
async def handle_pay_acc_name_entered(message: Message, state: FSMContext):
    acc_name = message.text.strip()
    await state.update_data(pay_acc_name=acc_name)
    await state.set_state(AdminAddPaymentMethodStates.waiting_for_instructions)
    await message.answer("📝 *الخطوة 4/4:* اكتب *تعليمات التحويل للعميل* (مثال: أرسل الحوالة للرقم الموضح ثم ارفع الإشعار):")


@router.message(AdminAddPaymentMethodStates.waiting_for_instructions)
async def handle_pay_instructions_entered(message: Message, state: FSMContext):
    instructions = message.text.strip()
    data = await state.get_data()
    await state.clear()

    name = data.get("pay_name")
    acc = data.get("pay_account")
    acc_name = data.get("pay_acc_name")

    def create_method():
        return PaymentMethod.objects.create(
            name=name,
            icon="🏦",
            account_number=acc,
            account_name=acc_name,
            instructions=instructions,
            requires_proof_image=True,
            is_active=True
        )

    method = await sync_to_async(create_method)()

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 عرض طرق الدفع", callback_data="adm_paymethods_list")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])

    await message.answer(
        f"🎉 *تمت إضافة طريقة الدفع بنجاح!* ✨\n\n"
        f"الطريقة: *{method.name}*\n"
        f"رقم الحساب: `{method.account_number}`\n"
        f"المستفيد: *{method.account_name}*",
        reply_markup=markup,
        parse_mode='Markdown'
    )


# ==============================================================================
# 7.1 إدارة طلبات الشحن والمدفوعات (Deposit Requests Manager)
# ==============================================================================
@router.callback_query(F.data == "adm_deposits_list")
@router.message(F.text == "📥 طلبات الشحن المعلقة")
async def handle_admin_deposits_list(event: Message | CallbackQuery):
    """View pending customer top-up requests."""
    user_id = event.from_user.id
    is_admin = await sync_to_async(AdminAuthService.is_admin)(user_id)
    if not is_admin:
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ ليس لديك صلاحية المشرف.", show_alert=True)
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    requests = await sync_to_async(list)(
        PaymentRequest.objects.filter(status='PENDING')
        .select_related('user', 'payment_method')
        .order_by('-created_at')[:20]
    )

    if not requests:
        text = (
            "💳 *طلبات شحن الرصيد المعلقة:*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ *لا توجد طلبات شحن معلقة حالياً.*\n"
            "جميع طلبات العملاء تمت مراجعتها بالكامل."
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 تحديث القائمة", callback_data="adm_deposits_list")],
            [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
        ])
        if isinstance(event, CallbackQuery):
            await target.edit_text(text, reply_markup=markup, parse_mode='Markdown')
        else:
            await target.answer(text, reply_markup=markup, parse_mode='Markdown')
        return

    buttons = []
    text_lines = [
        f"💳 *طلبات شحن الرصيد المعلقة ({len(requests)} طلب):*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"اختر أي طلب لعرض بيانات التحويل، صورة الإشعار، واعتماده:\n"
    ]

    for req in requests:
        u_name = req.user.full_name[:18]
        has_img = "📸 " if (req.proof_image_file_id or req.proof_image_url) else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{has_img}{req.amount_yer:,.0f} YER | {u_name} ({req.payment_method.name})",
                callback_data=f"adm_dep_view:{req.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="🔄 تحديث القائمة", callback_data="adm_deposits_list"),
        InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(event, CallbackQuery):
        await target.edit_text("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')
    else:
        await target.answer("\n".join(text_lines), reply_markup=markup, parse_mode='Markdown')


@router.callback_query(F.data.startswith("adm_dep_view:"))
async def handle_admin_deposit_view(callback: CallbackQuery):
    """View details of a single deposit request with receipt photo and action buttons."""
    user_id = callback.from_user.id
    is_admin = await sync_to_async(AdminAuthService.is_admin)(user_id)
    if not is_admin:
        await callback.answer("⛔ ليس لديك صلاحية المشرف.", show_alert=True)
        return

    await callback.answer()
    req_id = callback.data.split(":")[1]

    req = await sync_to_async(
        PaymentRequest.objects.filter(id=req_id)
        .select_related('user', 'payment_method')
        .first
    )()

    if not req:
        await callback.answer("طلب الشحن غير موجود أو تم حذفه.", show_alert=True)
        return

    import html
    u_name = html.escape(req.user.full_name or "عميل")
    u_mention = f'<a href="tg://user?id={req.user.telegram_id}">{u_name}</a>'
    if req.user.username:
        clean_u = req.user.username.lstrip('@')
        user_block = (
            f"👤 <b>العميل:</b> {u_mention}\n"
            f"🔗 <b>اسم المستخدم:</b> @{html.escape(clean_u)} (<a href=\"https://t.me/{clean_u}\">مراسلة</a>)\n"
            f"🆔 <b>آيدي العميل:</b> <code>{req.user.telegram_id}</code>"
        )
        user_plain = f"👤 العميل: {req.user.full_name or 'عميل'}\n🔗 اسم المستخدم: @{clean_u} (https://t.me/{clean_u})\n🆔 آيدي العميل: {req.user.telegram_id}"
    else:
        user_block = (
            f"👤 <b>العميل:</b> {u_mention}\n"
            f"🆔 <b>آيدي العميل:</b> <code>{req.user.telegram_id}</code> (<a href=\"tg://user?id={req.user.telegram_id}\">رابط الحساب</a>)"
        )
        user_plain = f"👤 العميل: {req.user.full_name or 'عميل'}\n🆔 آيدي العميل: {req.user.telegram_id} (tg://user?id={req.user.telegram_id})"

    m_name = html.escape(req.payment_method.name)
    tx_val = html.escape(req.tx_number or "لا يوجد")
    status_disp = html.escape(req.get_status_display())

    text = (
        f"💳 <b>طلب شحن رصيد: PAY-{str(req.id)[:8]}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{user_block}\n"
        f"💰 <b>المبلغ المحول:</b> <b>{req.amount_yer:,.0f} YER</b>\n"
        f"🏦 <b>طريقة الدفع:</b> {m_name}\n"
        f"🔢 <b>رقم الحوالة:</b> <code>{tx_val}</code>\n"
        f"⏱ <b>الحالة:</b> {status_disp}\n"
        f"📅 <b>تاريخ الإنشاء:</b> <code>{req.created_at.strftime('%Y-%m-%d %I:%M %p')}</code>\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    plain_text = (
        f"💳 طلب شحن رصيد: PAY-{str(req.id)[:8]}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{user_plain}\n"
        f"💰 المبلغ المحول: {req.amount_yer:,.0f} YER\n"
        f"🏦 طريقة الدفع: {req.payment_method.name}\n"
        f"🔢 رقم الحوالة: {req.tx_number or 'لا يوجد'}\n"
        f"⏱ الحالة: {req.get_status_display()}\n"
        f"📅 تاريخ الإنشاء: {req.created_at.strftime('%Y-%m-%d %I:%M %p')}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    buttons = []
    if req.status == 'PENDING':
        buttons.append([
            InlineKeyboardButton(text="✅ قبول وإيداع الرصيد", callback_data=f"adm_pay_approve:{req.id}"),
            InlineKeyboardButton(text="❌ رفض الطلب", callback_data=f"adm_pay_reject:{req.id}")
        ])
    if req.user.username:
        clean_u = req.user.username.lstrip('@')
        buttons.append([
            InlineKeyboardButton(text="👤 محادثة العميل", url=f"https://t.me/{clean_u}")
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 العودة لطلبات الشحن", callback_data="adm_deposits_list"),
        InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")
    ])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    # Download photo directly into RAM so it renders cleanly without URL restrictions
    photo_bytes = None
    if req.proof_image_file_id:
        cust_bot = get_customer_bot()
        admin_bot = get_admin_bot()
        for b in [cust_bot, admin_bot]:
            if not b:
                continue
            try:
                stream = await b.download(req.proof_image_file_id)
                if stream:
                    photo_bytes = stream.read()
                    if photo_bytes:
                        break
            except Exception as dl_err:
                logger.debug(f"Could not download receipt photo: {dl_err}")

    if photo_bytes:
        from aiogram.types import BufferedInputFile
        try:
            await callback.message.delete()
        except Exception:
            pass
        try:
            await callback.message.answer_photo(
                photo=BufferedInputFile(photo_bytes, filename=f"payment_{req.id}.jpg"),
                caption=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
            return
        except Exception:
            try:
                await callback.message.answer_photo(
                    photo=BufferedInputFile(photo_bytes, filename=f"payment_{req.id}.jpg"),
                    caption=plain_text,
                    reply_markup=markup
                )
                return
            except Exception:
                pass

    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode='HTML')
    except Exception:
        try:
            await callback.message.edit_text(plain_text, reply_markup=markup)
        except Exception:
            await callback.message.answer(plain_text, reply_markup=markup)


# ==============================================================================
# 8. إعدادات المتجر والنظام وأسعار الصرف (Store Settings & SaaS Configuration)
# ==============================================================================
@router.callback_query(F.data.in_(["adm_settings_view", "adm_rate_view"]))
@router.message(F.text.in_(["⚙️ إعدادات المتجر والنظام", "💵 أسعار الصرف والإعدادات"]))
async def handle_admin_settings_view(event: Message | CallbackQuery):
    """View and manage dynamic SaaS system settings, store branding, and exchange rates."""
    user_id = event.from_user.id
    is_admin = await sync_to_async(AdminAuthService.is_admin)(user_id)
    if not is_admin:
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    rate = await sync_to_async(ExchangeRate.get_usd_to_yer_rate)()
    base_curr = await sync_to_async(CurrencyService.get_base_currency)()
    store_name = await sync_to_async(SystemSettingService.get_setting)('STORE_NAME', 'المتجر الرقمي')
    support_user = await sync_to_async(SystemSettingService.get_setting)('SUPPORT_USERNAME', '')
    ref_bonus = await sync_to_async(SystemSettingService.get_decimal)('REFERRAL_BONUS_YER', Decimal('50.00'))
    ref_enabled = await sync_to_async(SystemSettingService.get_bool)('REFERRAL_ENABLED', True)
    success_ch_id = await sync_to_async(SystemSettingService.get_setting)('SUCCESS_CHANNEL_ID', '@duudsuccess')
    success_enabled = await sync_to_async(SystemSettingService.get_bool)('SUCCESS_CHANNEL_ENABLED', True)
    mand_sub_enabled = await sync_to_async(SystemSettingService.get_bool)('MANDATORY_SUBSCRIPTION_ENABLED', True)
    backup_ch_id = await sync_to_async(SystemSettingService.get_setting)('BACKUP_CHANNEL_ID', '')
    backup_enabled = await sync_to_async(SystemSettingService.get_bool)('BACKUP_AUTO_ENABLED', True)

    support_display = f"@{support_user.lstrip('@')}" if support_user else "غير محدد (مفتوح للتذاكر فقط)"
    ref_status = "🟢 مفعّل" if ref_enabled else "🔴 معطّل"
    success_status = "🟢 مفعّل" if success_enabled else "🔴 معطّل"
    mand_status = "🟢 إجباري" if mand_sub_enabled else "⚪ اختياري (معطّل)"
    backup_status = "🟢 مفعّل" if backup_enabled else "🔴 معطّل"
    backup_display = backup_ch_id if backup_ch_id else "حساب المالك الافتراضي"
    curr_label = "🇾🇪 ريال يمني (YER)" if base_curr == 'YER' else "🇺🇸 دولار أمريكي (USD)"

    text = (
        f"⚙️ <b>لوحة إعدادات النظام والمتجر (SaaS Settings)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ <b>اسم المتجر:</b> <code>{html.escape(store_name)}</code>\n"
        f"💱 <b>العملة الرسمية للمتجر:</b> <b>{curr_label}</b>\n"
        f"💵 <b>سعر الصرف المعتمد:</b> <b>1 USD = {rate:,.2f} YER</b>\n"
        f"📢 <b>قناة التفعيلات:</b> <code>{html.escape(success_ch_id or 'غير محددة')}</code> ({success_status})\n"
        f"🔒 <b>الاشتراك الإجباري:</b> {mand_status}\n"
        f"📦 <b>قناة النسخ الاحتياطي:</b> <code>{html.escape(backup_display)}</code> ({backup_status})\n"
        f"🎧 <b>يوزر الدعم الفني:</b> <code>{html.escape(support_display)}</code>\n"
        f"🤝 <b>مكافأة الإحالة:</b> <b>{ref_bonus:,.0f} YER</b> ({ref_status})\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"اختر الإعداد الذي ترغب بتهيئته أو تعديله:"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💵 تعديل سعر الصرف", callback_data="adm_edit_rate"),
            InlineKeyboardButton(text=f"💱 تحويل العملة إلى {'USD' if base_curr == 'YER' else 'YER'}", callback_data="adm_toggle_base_currency"),
        ],
        [
            InlineKeyboardButton(text="📢 إعدادات قناة التفعيلات", callback_data="adm_success_ch_view"),
            InlineKeyboardButton(text="🔒 قنوات الاشتراك الإجباري", callback_data="adm_channels_list"),
        ],
        [
            InlineKeyboardButton(text="📦 إعدادات النسخ الاحتياطي للبيانات", callback_data="adm_backup_view"),
        ],
        [
            InlineKeyboardButton(text="🏷️ تعديل اسم المتجر", callback_data="adm_edit_store_name"),
            InlineKeyboardButton(text="🎧 تعديل يوزر الدعم", callback_data="adm_edit_support_user"),
        ],
        [
            InlineKeyboardButton(text="🤝 تعديل مكافأة الإحالة", callback_data="adm_edit_ref_bonus"),
            InlineKeyboardButton(text=f"🔄 {'تعطيل' if ref_enabled else 'تفعيل'} نظام الإحالات", callback_data="adm_toggle_referral"),
        ],
        [
            InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")
        ]
    ])

    if isinstance(event, CallbackQuery):
        await target.edit_text(text, reply_markup=markup, parse_mode='HTML')
    else:
        await target.answer(text, reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data == "adm_toggle_base_currency")
async def handle_toggle_base_currency(callback: CallbackQuery):
    """Toggle official base currency between YER and USD."""
    current = await sync_to_async(CurrencyService.get_base_currency)()
    new_curr = 'USD' if current == 'YER' else 'YER'
    await sync_to_async(CurrencyService.set_base_currency)(new_curr)
    curr_name = "الدولار الأمريكي (USD)" if new_curr == 'USD' else "الريال اليمني (YER)"
    await callback.answer(f"✅ تم تغيير العملة الرسمية للمتجر إلى: {curr_name} بنجاح!", show_alert=True)
    await handle_admin_settings_view(callback)


@router.callback_query(F.data == "adm_success_ch_view")
async def handle_success_channel_view(callback: CallbackQuery):
    """View and manage success/activations channel settings."""
    await callback.answer()
    ch_id = await sync_to_async(SystemSettingService.get_setting)('SUCCESS_CHANNEL_ID', '@duudsuccess')
    ch_title = await sync_to_async(SystemSettingService.get_setting)('SUCCESS_CHANNEL_TITLE', 'قناة التفعيلات المباشرة')
    ch_url = await sync_to_async(SystemSettingService.get_setting)('SUCCESS_CHANNEL_URL', 'https://t.me/duudsuccess')
    is_enabled = await sync_to_async(SystemSettingService.get_bool)('SUCCESS_CHANNEL_ENABLED', True)

    status_text = "🟢 مفعّل (يتم النشر تلقائياً)" if is_enabled else "🔴 معطّل (النشر متوقف)"

    text = (
        f"📢 <b>إعدادات قناة التفعيلات الناجحة (Success Channel)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>معرف القناة:</b> <code>{html.escape(ch_id or 'غير محدد')}</code>\n"
        f"🏷️ <b>اسم القناة:</b> <b>{html.escape(ch_title)}</b>\n"
        f"🔗 <b>رابط القناة:</b> <code>{html.escape(ch_url or 'لا يوجد')}</code>\n"
        f"⚡ <b>حالة النشر:</b> <b>{status_text}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>ملاحظة: تأكد من إضافة بوت المتجر كمشرف في القناة ولديه صلاحية نشر الرسائل.</i>"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🔄 {'تعطيل' if is_enabled else 'تفعيل'} النشر التلقائي", callback_data="adm_toggle_success_ch"),
        ],
        [
            InlineKeyboardButton(text="🆔 تعديل معرف القناة (ID/@)", callback_data="adm_edit_success_ch_id"),
            InlineKeyboardButton(text="🏷️ تعديل اسم القناة", callback_data="adm_edit_success_ch_title"),
        ],
        [
            InlineKeyboardButton(text="🔗 تعديل رابط القناة", callback_data="adm_edit_success_ch_url"),
            InlineKeyboardButton(text="🧪 فحص إرسال تجريبي", callback_data="adm_test_success_ch"),
        ],
        [
            InlineKeyboardButton(text="⚙️ العودة للإعدادات", callback_data="adm_settings_view"),
            InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home"),
        ]
    ])

    await callback.message.edit_text(text, reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data == "adm_toggle_success_ch")
async def handle_toggle_success_channel(callback: CallbackQuery):
    """Toggle success channel broadcasting."""
    current = await sync_to_async(SystemSettingService.get_bool)('SUCCESS_CHANNEL_ENABLED', True)
    new_state = "false" if current else "true"
    await sync_to_async(SystemSettingService.set_setting)('SUCCESS_CHANNEL_ENABLED', new_state, "تفعيل/تعطيل النشر في قناة التفعيلات")
    await callback.answer(f"تم {'تعطيل' if current else 'تفعيل'} النشر التلقائي بنجاح!")
    await handle_success_channel_view(callback)


@router.callback_query(F.data == "adm_edit_success_ch_id")
async def handle_prompt_success_ch_id(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_success_channel_id)
    await callback.message.answer(
        "✍️ اكتب وأرسل <b>معرف قناة التفعيلات الجديد</b> (مثال: <code>@duudsuccess</code> أو <code>-1004496030171</code>):\n"
        "<i>(أو اكتب إلغاء للتراجع)</i>",
        parse_mode='HTML'
    )


@router.message(AdminSettingsStates.waiting_for_success_channel_id)
async def handle_save_success_ch_id(message: Message, state: FSMContext):
    txt = message.text.strip()
    if txt.lower() in ("/cancel", "إلغاء", "الغاء"):
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return

    await state.clear()
    await sync_to_async(SystemSettingService.set_setting)('SUCCESS_CHANNEL_ID', txt, "معرف قناة التفعيلات الناجحة")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 العودة لقناة التفعيلات", callback_data="adm_success_ch_view")],
        [InlineKeyboardButton(text="⚙️ العودة للإعدادات", callback_data="adm_settings_view")]
    ])
    await message.answer(f"✅ تم تحديث معرف قناة التفعيلات إلى: <code>{html.escape(txt)}</code>", reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data == "adm_edit_success_ch_title")
async def handle_prompt_success_ch_title(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_success_channel_title)
    await callback.message.answer("✍️ اكتب وأرسل <b>اسم قناة التفعيلات</b> (مثال: قناة التفعيلات والعمليات الناجحة):", parse_mode='HTML')


@router.message(AdminSettingsStates.waiting_for_success_channel_title)
async def handle_save_success_ch_title(message: Message, state: FSMContext):
    txt = message.text.strip()
    if txt.lower() in ("/cancel", "إلغاء", "الغاء"):
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return

    await state.clear()
    await sync_to_async(SystemSettingService.set_setting)('SUCCESS_CHANNEL_TITLE', txt, "اسم قناة التفعيلات")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 العودة لقناة التفعيلات", callback_data="adm_success_ch_view")],
        [InlineKeyboardButton(text="⚙️ العودة للإعدادات", callback_data="adm_settings_view")]
    ])
    await message.answer(f"✅ تم حفظ اسم قناة التفعيلات: <b>{html.escape(txt)}</b>", reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data == "adm_edit_success_ch_url")
async def handle_prompt_success_ch_url(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_success_channel_url)
    await callback.message.answer("✍️ اكتب وأرسل <b>رابط قناة التفعيلات</b> (مثال: <code>https://t.me/duudsuccess</code>):", parse_mode='HTML')


@router.message(AdminSettingsStates.waiting_for_success_channel_url)
async def handle_save_success_ch_url(message: Message, state: FSMContext):
    txt = message.text.strip()
    if txt.lower() in ("/cancel", "إلغاء", "الغاء"):
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return

    await state.clear()
    await sync_to_async(SystemSettingService.set_setting)('SUCCESS_CHANNEL_URL', txt, "رابط قناة التفعيلات")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 العودة لقناة التفعيلات", callback_data="adm_success_ch_view")],
        [InlineKeyboardButton(text="⚙️ العودة للإعدادات", callback_data="adm_settings_view")]
    ])
    await message.answer(f"✅ تم حفظ رابط قناة التفعيلات: <code>{html.escape(txt)}</code>", reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data == "adm_test_success_ch")
async def handle_test_success_channel(callback: CallbackQuery):
    """Test send message to verify bot admin rights in success channel."""
    await callback.answer("⏳ جاري الفحص والإرسال للقناة...")
    ch_id = await sync_to_async(SystemSettingService.get_setting)('SUCCESS_CHANNEL_ID', '')
    if not ch_id:
        await callback.message.answer("⚠️ لم يتم تعيين معرف قناة التفعيلات بعد!")
        return

    bot = callback.bot
    try:
        sent = await bot.send_message(
            chat_id=ch_id,
            text="🧪 <b>رسالة فحص تجريبية من لوحة الإدارة</b> ✅\nالبوت متصل بالقناة بنجاح ولديه صلاحيات المشرف الكاملة.",
            parse_mode='HTML'
        )
        await callback.message.answer(
            f"✅ <b>نجح الإرسال للقناة!</b>\n"
            f"معرف القناة: <code>{html.escape(ch_id)}</code>\n"
            f"معرف الرسالة المرسلة: <code>{sent.message_id}</code>\n\n"
            f"تم التحقق بنجاح من أن البوت مشرف في القناة.",
            parse_mode='HTML'
        )
    except Exception as e:
        await callback.message.answer(
            f"❌ <b>فشل الإرسال إلى القناة:</b>\n"
            f"<code>{html.escape(str(e))}</code>\n\n"
            f"يرجى التأكد من إضافة البوت كمشرف في القناة <code>{html.escape(ch_id)}</code> ومنحه صلاحية إرسال الرسائل.",
            parse_mode='HTML'
        )


@router.callback_query(F.data == "adm_backup_view")
async def handle_admin_backup_view(callback: CallbackQuery):
    """View database backup settings and trigger manual backup."""
    await callback.answer()
    backup_ch_id = await sync_to_async(SystemSettingService.get_setting)('BACKUP_CHANNEL_ID', '')
    is_auto = await sync_to_async(SystemSettingService.get_bool)('BACKUP_AUTO_ENABLED', True)
    last_time = await sync_to_async(SystemSettingService.get_setting)('LAST_BACKUP_TIME', 'لم يتم أخذ نسخة بعد')
    super_admin_id = getattr(settings, 'SUPER_ADMIN_TELEGRAM_ID', 'غير محدد')

    dest_display = backup_ch_id if backup_ch_id else f"حساب المالك الأساسي ({super_admin_id})"
    auto_status = "🟢 مفعّل" if is_auto else "🔴 معطّل"

    text = (
        f"📦 <b>إعدادات النسخ الاحتياطي لقاعدة البيانات</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>وجهة استلام النسخة:</b> <code>{html.escape(str(dest_display))}</code>\n"
        f"⚡ <b>النسخ التلقائي:</b> <b>{auto_status}</b>\n"
        f"🕒 <b>آخر عملية نسخ:</b> <code>{html.escape(str(last_time))}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>يقوم النظام بضغط كافة جداول قاعدة البيانات والعمليات والمستخدمين والمخزون في ملف مشفر وإرساله مباشرة لتليجرام.</i>\n\n"
        f"اختر الإجراء المطلوب:"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 إنشاء وإرسال نسخة احتياطية الآن", callback_data="adm_run_backup_now"),
        ],
        [
            InlineKeyboardButton(text="🆔 تعديل معرف قناة/شات النسخ", callback_data="adm_edit_backup_id"),
            InlineKeyboardButton(text=f"🔄 {'تعطيل' if is_auto else 'تفعيل'} النسخ التلقائي", callback_data="adm_toggle_backup_auto"),
        ],
        [
            InlineKeyboardButton(text="⚙️ العودة للإعدادات", callback_data="adm_settings_view"),
            InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home"),
        ]
    ])

    await callback.message.edit_text(text, reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data == "adm_toggle_backup_auto")
async def handle_toggle_backup_auto(callback: CallbackQuery):
    """Toggle automated database backup setting."""
    current = await sync_to_async(SystemSettingService.get_bool)('BACKUP_AUTO_ENABLED', True)
    new_state = "false" if current else "true"
    await sync_to_async(SystemSettingService.set_setting)('BACKUP_AUTO_ENABLED', new_state, "تفعيل أو تعطيل النسخ الاحتياطي التلقائي")
    await callback.answer(f"تم {'تعطيل' if current else 'تفعيل'} النسخ التلقائي بنجاح!", show_alert=True)
    await handle_admin_backup_view(callback)


@router.callback_query(F.data == "adm_edit_backup_id")
async def handle_prompt_backup_id(callback: CallbackQuery, state: FSMContext):
    """Prompt admin to enter backup channel or chat ID."""
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_backup_channel_id)
    await callback.message.answer(
        "✍️ أرسل <b>معرف قناة النسخ الاحتياطي</b> (مثال: <code>-1001234567890</code> أو <code>@MyBackupChannel</code>)\n"
        "أو أرسل الآيدي الخاص بك <code>6069495114</code> لاستلامها في محادثتك الخاصة مباشرة:\n\n"
        "<i>(أرسل 'إلغاء' للإلغاء، أو 'تفريغ' للاعتماد على آيدي المالك الافتراضي)</i>",
        parse_mode='HTML'
    )


@router.message(AdminSettingsStates.waiting_for_backup_channel_id)
async def handle_save_backup_id(message: Message, state: FSMContext):
    """Save backup channel or chat ID."""
    txt = message.text.strip()
    if txt.lower() in ("/cancel", "إلغاء", "الغاء"):
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return

    await state.clear()
    new_val = "" if txt in ("تفريغ", "افتراضي", "حذف") else txt
    await sync_to_async(SystemSettingService.set_setting)(
        'BACKUP_CHANNEL_ID',
        new_val,
        "معرف قناة أو شات النسخ الاحتياطي لقاعدة البيانات"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 العودة لقسم النسخ الاحتياطي", callback_data="adm_backup_view")],
        [InlineKeyboardButton(text="⚙️ العودة للإعدادات", callback_data="adm_settings_view")]
    ])
    display = new_val if new_val else "حساب المالك الافتراضي"
    await message.answer(
        f"✅ تم حفظ وجهة النسخ الاحتياطي: <code>{html.escape(display)}</code>\n"
        f"تأكد من إضافة بوت الإدارة مشرفاً في القناة إذا كانت قناة خاصة.",
        reply_markup=markup,
        parse_mode='HTML'
    )


@router.callback_query(F.data == "adm_run_backup_now")
async def handle_admin_run_backup_now(callback: CallbackQuery):
    """Trigger on-demand database backup and send to Telegram."""
    await callback.answer("⏳ جاري إنشاء النسخة الاحتياطية وإرسالها...", show_alert=True)
    status_msg = await callback.message.answer("⏳ <i>جاري إنشاء وتجهيز النسخة الاحتياطية لقاعدة البيانات الآن...</i>", parse_mode='HTML')

    success, msg = await DatabaseBackupService.send_backup_to_telegram()

    if success:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 العودة لقسم النسخ الاحتياطي", callback_data="adm_backup_view")],
            [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
        ])
        await status_msg.edit_text(
            f"✅ <b>نجحت عملية النسخ الاحتياطي!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{msg}\n\n"
            f"تم إرسال الملف المضغوط إلى وجهة النسخ بنجاح.",
            reply_markup=markup,
            parse_mode='HTML'
        )
    else:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 محاولة أخرى", callback_data="adm_run_backup_now")],
            [InlineKeyboardButton(text="📦 العودة للنسخ الاحتياطي", callback_data="adm_backup_view")]
        ])
        await status_msg.edit_text(
            f"❌ <b>فشلت عملية النسخ الاحتياطي:</b>\n"
            f"<code>{html.escape(msg)}</code>\n\n"
            f"يرجى التأكد من أن البوت عضو ومشرف في القناة ولديه صلاحية إرسال المستندات.",
            reply_markup=markup,
            parse_mode='HTML'
        )


@router.callback_query(F.data == "adm_toggle_referral")
async def handle_toggle_referral(callback: CallbackQuery):
    """Toggle referral system on/off."""
    current = await sync_to_async(SystemSettingService.get_bool)('REFERRAL_ENABLED', True)
    new_state = "false" if current else "true"
    await sync_to_async(SystemSettingService.set_setting)('REFERRAL_ENABLED', new_state, "تفعيل أو تعطيل نظام الإحالات")
    await callback.answer(f"تم {'تعطيل' if current else 'تفعيل'} نظام الإحالات بنجاح!")
    await handle_admin_settings_view(callback)


@router.callback_query(F.data == "adm_edit_rate")
async def handle_prompt_new_rate(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminExchangeRateStates.waiting_for_rate)
    await callback.message.answer("✍️ اكتب وأرسل <b>سعر الصرف الجديد</b> (مثال: 560):", parse_mode='HTML')


@router.message(AdminExchangeRateStates.waiting_for_rate)
async def handle_save_new_rate(message: Message, state: FSMContext):
    txt = message.text.strip().lower() if message.text else ""
    if txt in ("/cancel", "إلغاء", "الغاء"):
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return

    try:
        new_rate = Decimal(message.text.strip().replace(",", ""))
        if new_rate <= 0:
            raise ValueError()
    except Exception:
        await message.answer("⚠️ يرجى إدخال رقم صحيح وموجب لسعر الصرف:")
        return

    await state.clear()

    def update_rate(val):
        rate_obj, _ = ExchangeRate.objects.get_or_create(source_currency='USD', target_currency='YER')
        rate_obj.rate = val
        rate_obj.is_active = True
        rate_obj.save()
        return rate_obj

    await sync_to_async(update_rate)(new_rate)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ العودة للإعدادات", callback_data="adm_settings_view")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])

    await message.answer(
        f"✅ <b>تم تحديث سعر الصرف بنجاح!</b>\n"
        f"السعر الجديد: <b>1 USD = {new_rate:,.2f} YER</b>",
        reply_markup=markup,
        parse_mode='HTML'
    )


@router.callback_query(F.data == "adm_edit_store_name")
async def handle_prompt_new_store_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_store_name)
    await callback.message.answer("✍️ اكتب وأرسل <b>اسم المتجر الجديد</b> الذي يظهر للعملاء في البوت والرسائل:", parse_mode='HTML')


@router.message(AdminSettingsStates.waiting_for_store_name)
async def handle_save_new_store_name(message: Message, state: FSMContext):
    txt = message.text.strip()
    if txt.lower() in ("/cancel", "إلغاء", "الغاء"):
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return

    await state.clear()
    await sync_to_async(SystemSettingService.set_setting)('STORE_NAME', txt, "اسم المتجر العام")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ العودة للإعدادات", callback_data="adm_settings_view")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])
    await message.answer(f"✅ تم تحديث اسم المتجر إلى: <b>{html.escape(txt)}</b>", reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data == "adm_edit_support_user")
async def handle_prompt_new_support_user(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_support_user)
    await callback.message.answer("✍️ اكتب وأرسل <b>يوزر التليجرام الخاص بحساب الدعم</b> (مثال: <code>@MySupportAccount</code> أو أرسل <code>0</code> لإلغاء المعرف والاعتماد على التذاكر فقط):", parse_mode='HTML')


@router.message(AdminSettingsStates.waiting_for_support_user)
async def handle_save_new_support_user(message: Message, state: FSMContext):
    txt = message.text.strip()
    if txt.lower() in ("/cancel", "إلغاء", "الغاء"):
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return

    await state.clear()
    val = "" if txt in ("0", "-", "لا يوجد", "none") else txt.lstrip('@')
    await sync_to_async(SystemSettingService.set_setting)('SUPPORT_USERNAME', val, "يوزر حساب الدعم الفني المباشر")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ العودة للإعدادات", callback_data="adm_settings_view")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])
    display_user = f"@{val}" if val else "بدون معرف (تذاكر داخلية فقط)"
    await message.answer(f"✅ تم حفظ يوزر الدعم الفني: <b>{html.escape(display_user)}</b>", reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data == "adm_edit_ref_bonus")
async def handle_prompt_new_ref_bonus(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_referral_bonus)
    await callback.message.answer("✍️ اكتب وأرسل <b>مبلغ مكافأة الإحالة بالريال اليمني (YER)</b> التي تضاف للداعي عند انضمام صديق جديد (مثال: <code>50</code>):", parse_mode='HTML')


@router.message(AdminSettingsStates.waiting_for_referral_bonus)
async def handle_save_new_ref_bonus(message: Message, state: FSMContext):
    txt = message.text.strip().lower()
    if txt in ("/cancel", "إلغاء", "الغاء"):
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return

    try:
        amount = Decimal(message.text.strip().replace(",", ""))
        if amount < 0:
            raise ValueError()
    except Exception:
        await message.answer("⚠️ يرجى إدخال مبلغ صحيح (0 أو أكبر):")
        return

    await state.clear()
    await sync_to_async(SystemSettingService.set_setting)('REFERRAL_BONUS_YER', str(amount), "مبلغ مكافأة دعوة الأصدقاء بالريال اليمني")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ العودة للإعدادات", callback_data="adm_settings_view")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])
    await message.answer(f"✅ تم تحديث مبلغ مكافأة الإحالة إلى: <b>{amount:,.0f} YER</b>", reply_markup=markup, parse_mode='HTML')



# ==============================================================================
# 9. إدارة القنوات الإجبارية (Mandatory Channels Manager)
# ==============================================================================
@router.callback_query(F.data == "adm_channels_list")
@router.message(F.text == "📢 القنوات الإجبارية")
async def handle_channels_list(event: Message | CallbackQuery):
    """View and manage mandatory channels."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    channels = await sync_to_async(list)(RequiredChannel.objects.all())
    mand_sub_enabled = await sync_to_async(SystemSettingService.get_bool)('MANDATORY_SUBSCRIPTION_ENABLED', True)
    global_status = "🟢 مفعّل (الاشتراك إجباري)" if mand_sub_enabled else "🔴 معطّل (الدخول متاح للجميع)"

    buttons = []
    text_lines = [
        "📢 <b>قنوات الاشتراك الإجباري لبوت المتجر:</b>\n"
        f"⚡ <b>حالة النظام:</b> <b>{global_status}</b>\n"
        "━━━━━━━━━━━━━━━━━━"
    ]
    if not channels:
        text_lines.append("لا توجد قنوات إجبارية مضافة حالياً. (المتجر متاح للجميع بدون قيود)")
    else:
        for ch in channels:
            status = "🟢" if ch.is_active else "🔴"
            title_escaped = html.escape(str(ch.channel_title))
            id_escaped = html.escape(str(ch.channel_id))
            link_escaped = html.escape(str(ch.invite_link or 'لا يوجد'))
            text_lines.append(f"{status} <b>{title_escaped}</b>\nالمعرف: <code>{id_escaped}</code>\nالرابط: {link_escaped}\n")
            buttons.append([
                InlineKeyboardButton(text=f"🗑️ حذف: {ch.channel_title[:20]}", callback_data=f"adm_ch_del:{ch.id}")
            ])

    text_lines.append("━━━━━━━━━━━━━━━━━━")
    buttons.append([
        InlineKeyboardButton(
            text=f"🔄 {'تعطيل' if mand_sub_enabled else 'تفعيل'} نظام الاشتراك الإجباري",
            callback_data="adm_toggle_mand_sub"
        )
    ])
    buttons.append([InlineKeyboardButton(text="➕ إضافة قناة إجبارية جديدة", callback_data="adm_ch_add")])
    buttons.append([
        InlineKeyboardButton(text="⚙️ العودة للإعدادات", callback_data="adm_settings_view"),
        InlineKeyboardButton(text="🏠 عودة للرئيسية", callback_data="adm_home")
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(event, CallbackQuery):
        await target.edit_text("\n".join(text_lines), reply_markup=markup, parse_mode='HTML')
    else:
        await target.answer("\n".join(text_lines), reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data == "adm_toggle_mand_sub")
async def handle_toggle_mandatory_sub(callback: CallbackQuery):
    """Toggle mandatory channel subscription on/off globally."""
    current = await sync_to_async(SystemSettingService.get_bool)('MANDATORY_SUBSCRIPTION_ENABLED', True)
    new_state = "false" if current else "true"
    await sync_to_async(SystemSettingService.set_setting)('MANDATORY_SUBSCRIPTION_ENABLED', new_state, "تفعيل أو تعطيل نظام الاشتراك الإجباري")
    ChannelSubscriptionService.clear_cache()
    await callback.answer(f"تم {'تعطيل' if current else 'تفعيل'} نظام الاشتراك الإجباري بنجاح!", show_alert=True)
    await handle_channels_list(callback)


@router.callback_query(F.data.startswith("adm_ch_del:"))
async def handle_channel_del(callback: CallbackQuery):
    await callback.answer()
    ch_id = callback.data.split(":")[1]

    def del_c():
        c = RequiredChannel.objects.filter(id=ch_id).first()
        if c:
            title = c.channel_title
            c.delete()
            return title
        return None

    title = await sync_to_async(del_c)()
    if title:
        ChannelSubscriptionService.clear_cache()
        await callback.answer(f"تم حذف القناة ({title}) بنجاح!", show_alert=True)
    await handle_channels_list(callback)


@router.callback_query(F.data == "adm_ch_add")
async def handle_channel_add_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminAddChannelStates.waiting_for_title)
    await callback.message.answer(
        "📢 *إضافة قناة اشتراك إجباري (الخطوة 1/3)*\n\n"
        "اكتب *اسم القناة* (مثال: قناة المتجر الرسمية):",
        parse_mode='Markdown'
    )


@router.message(AdminAddChannelStates.waiting_for_title)
async def handle_channel_title_entered(message: Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(ch_title=title)
    await state.set_state(AdminAddChannelStates.waiting_for_channel_id)
    await message.answer(
        "🆔 *الخطوة 2/3:* اكتب *معرف القناة أو يوزرها* (مثال: `@your_channel` أو `-10012345678`):\n"
        "⚠️ ملاحظة: تأكد من إضافة بوت المتجر كمشرف في القناة!",
        parse_mode='Markdown'
    )


@router.message(AdminAddChannelStates.waiting_for_channel_id)
async def handle_channel_id_entered(message: Message, state: FSMContext):
    ch_id = message.text.strip()
    await state.update_data(ch_id=ch_id)
    await state.set_state(AdminAddChannelStates.waiting_for_invite_link)
    await message.answer("🔗 *الخطوة 3/3:* أرسل *رابط الدعوة للقناة* (مثال: `https://t.me/your_channel`):", parse_mode='Markdown')


@router.message(AdminAddChannelStates.waiting_for_invite_link)
async def handle_channel_link_entered(message: Message, state: FSMContext):
    link = message.text.strip()
    data = await state.get_data()
    await state.clear()

    title = data.get("ch_title")
    ch_id = data.get("ch_id")

    def create_channel():
        return RequiredChannel.objects.create(
            channel_id=ch_id,
            channel_title=title,
            invite_link=link,
            is_mandatory=True,
            is_active=True
        )

    ch = await sync_to_async(create_channel)()
    ChannelSubscriptionService.clear_cache()

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 عرض القنوات", callback_data="adm_channels_list")],
        [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")]
    ])

    await message.answer(
        f"✅ *تمت إضافة القناة الإجبارية بنجاح!*\n\n"
        f"القناة: *{ch.channel_title}*\n"
        f"المعرف: `{ch.channel_id}`",
        reply_markup=markup,
        parse_mode='Markdown'
    )


# ==============================================================================
# 10. المشاكل الفنية (Technical Issues)
# ==============================================================================
@router.callback_query(F.data == "adm_issues_list")
async def handle_issues_list(callback: CallbackQuery):
    await callback.answer()
    issues = await sync_to_async(list)(
        OrderIssue.objects.filter(is_resolved=False).select_related('order')[:8]
    )

    if not issues:
        text = "✅ *ممتاز! لا توجد أي مشاكل فنية أو طلبات متعثرة حالياً.*"
    else:
        text_lines = ["⚠️ *المشاكل الفنية والطلبات المتعثرة:*\n━━━━━━━━━━━━━━━━━━"]
        for iss in issues:
            text_lines.append(f"🔴 طلب #{iss.order.order_number} | {iss.issue_type}\nتفاصيل: {iss.details[:60]}...\n")
        text = "\n".join(text_lines)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 عودة للرئيسية", callback_data="adm_home")]
    ])
    await callback.message.edit_text(text, reply_markup=markup, parse_mode='Markdown')


# ==============================================================================
# 11. البث الجماعي (Broadcast Announcement)
# ==============================================================================
@router.callback_query(F.data == "adm_broadcast_prompt")
@router.message(F.text == "📢 إذاعة وبث جماعي")
async def handle_broadcast_prompt(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    await state.set_state(AdminBroadcastStates.waiting_for_text)
    await target.answer(
        "📢 *إرسال رسالة بث جماعي لجميع المشتركين*\n\n"
        "أرسل نص الرسالة الإعلانية أو التنبيه الآن ليتم إرساله لكافة مستخدمي البوت:",
        parse_mode='Markdown'
    )


@router.message(AdminBroadcastStates.waiting_for_text)
async def handle_broadcast_send(message: Message, state: FSMContext, bot):
    text = message.text.strip()
    await state.clear()

    user_ids = await sync_to_async(list)(TelegramProfile.objects.values_list('telegram_id', flat=True))
    sent_cnt = 0
    fail_cnt = 0

    status_msg = await message.answer(f"⏳ جاري إرسال البث إلى {len(user_ids)} عميل...")

    from apps.telegram_bot.common.bot_instances import get_customer_bot
    sender_bot = get_customer_bot() or bot

    for uid in user_ids:
        try:
            await sender_bot.send_message(chat_id=uid, text=text, parse_mode='Markdown')
            sent_cnt += 1
        except Exception:
            fail_cnt += 1

    await status_msg.edit_text(
        f"✅ *اكتمل إرسال البث الجماعي بنجاح!*\n\n"
        f"تم الإرسال: *{sent_cnt}*\n"
        f"تعذر (محظور أو ملغي): *{fail_cnt}*",
        parse_mode='Markdown'
    )


# ==============================================================================
# 12. الرجوع للرئيسية
# ==============================================================================
@router.callback_query(F.data == "adm_home")
async def handle_admin_back_home(callback: CallbackQuery, state: FSMContext):
    """Return to admin main menu."""
    await callback.answer()
    await state.clear()
    admin_name = callback.from_user.full_name or "المدير"
    text = (
        f"👑 *لوحة تحكم المتجر الرقمي*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 المدير: *{admin_name}*\n"
        f"تحكّم بالمتجر بالكامل من الأزرار التفاعلية أدناه:"
    )
    if callback.message and callback.message.photo:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=get_admin_dashboard_markup(), parse_mode='Markdown')
    else:
        try:
            await callback.message.edit_text(text, reply_markup=get_admin_dashboard_markup(), parse_mode='Markdown')
        except Exception:
            await callback.message.answer(text, reply_markup=get_admin_dashboard_markup(), parse_mode='Markdown')


# ==============================================================================
# 13. إدارة الخدمات الرقمية (Digital Services Management)
# ==============================================================================

@router.callback_query(F.data == "adm_services_list")
@router.message(F.text == "🛠 إدارة الخدمات الرقمية")
async def handle_admin_services_list(event: Message | CallbackQuery, state: FSMContext = None):
    """View and manage digital services."""
    if state:
        await state.clear()
        
    user_id = event.from_user.id
    is_admin = await sync_to_async(AdminAuthService.is_admin)(user_id)
    if not is_admin:
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event

    services = await sync_to_async(list)(DigitalService.objects.all().order_by('-created_at'))
    pending_quotes = await sync_to_async(ServiceRequest.objects.filter(status='PENDING_QUOTE').count)()

    buttons = []
    text_lines = ["🛠 <b>إدارة الخدمات الرقمية المخصصة:</b>\n━━━━━━━━━━━━━━━━━━"]

    if not services:
        text_lines.append("لا توجد خدمات رقمية مضافة حالياً.")
    else:
        for srv in services:
            status = "🟢" if srv.is_active else "🔴"
            type_label = "سعر ثابت" if srv.service_type == 'FIXED' else "تسعير مخصص"
            price_text = f"{srv.price_yer:,.0f} YER" if srv.service_type == 'FIXED' else "حسب العرض"
            text_lines.append(f"{status} <b>{html.escape(srv.name)}</b> ({type_label} - {price_text})")
            
            toggle_action = "تعطيل" if srv.is_active else "تفعيل"
            buttons.append([
                InlineKeyboardButton(text=f"🔄 {toggle_action}: {srv.name[:15]}", callback_data=f"adm_srv_tog:{srv.id}"),
                InlineKeyboardButton(text="🗑️ حذف", callback_data=f"adm_srv_del:{srv.id}")
            ])

    text_lines.append("━━━━━━━━━━━━━━━━━━")
    if pending_quotes > 0:
        text_lines.append(f"⚠️ يوجد <b>{pending_quotes}</b> طلبات خدمات جديدة بانتظار تقديم عرض السعر!")
        buttons.append([InlineKeyboardButton(text=f"💼 طلبات بانتظار التسعير ({pending_quotes})", callback_data="adm_srv_reqs")])

    buttons.append([InlineKeyboardButton(text="➕ إضافة خدمة رقمية جديدة", callback_data="adm_srv_add")])
    buttons.append([InlineKeyboardButton(text="🏠 عودة للرئيسية", callback_data="adm_home")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(event, CallbackQuery):
        try:
            await target.edit_text("\n".join(text_lines), reply_markup=markup, parse_mode='HTML')
        except Exception:
            await target.answer("\n".join(text_lines), reply_markup=markup, parse_mode='HTML')
    else:
        await target.answer("\n".join(text_lines), reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data.startswith("adm_srv_tog:"))
async def handle_service_toggle(callback: CallbackQuery):
    """Toggle digital service active status."""
    await callback.answer()
    srv_id = callback.data.split(":")[1]

    def _toggle():
        srv = DigitalService.objects.filter(id=srv_id).first()
        if srv:
            srv.is_active = not srv.is_active
            srv.save(update_fields=['is_active'])
            return srv.is_active
        return None

    await sync_to_async(_toggle)()
    await handle_admin_services_list(callback)


@router.callback_query(F.data.startswith("adm_srv_del:"))
async def handle_service_del(callback: CallbackQuery):
    """Delete a digital service."""
    await callback.answer()
    srv_id = callback.data.split(":")[1]

    def _del():
        srv = DigitalService.objects.filter(id=srv_id).first()
        if srv:
            srv.delete()
            return True
        return False

    await sync_to_async(_del)()
    try:
        await callback.answer("تم حذف الخدمة بنجاح!", show_alert=True)
    except Exception:
        pass
    await handle_admin_services_list(callback)


@router.callback_query(F.data == "adm_srv_add")
async def handle_service_add_start(callback: CallbackQuery, state: FSMContext):
    """Start FSM wizard to add a new digital service."""
    await callback.answer()
    await state.set_state(AdminAddDigitalServiceStates.waiting_for_name)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="adm_services_list")]
    ])
    await callback.message.answer(
        "🛠 <b>إضافة خدمة رقمية جديدة</b>\n\nأرسل <b>اسم الخدمة</b> (مثال: شحن تيك توك عملات، ترقية حساب، تصميم متجر):",
        reply_markup=cancel_kb,
        parse_mode='HTML'
    )


@router.message(AdminAddDigitalServiceStates.waiting_for_name)
async def handle_service_add_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ الاسم قصير جداً، يرجى كتابة اسم مناسب للخدمة:")
        return
    await state.update_data(srv_name=name)
    await state.set_state(AdminAddDigitalServiceStates.waiting_for_desc)
    await message.answer(
        f"📝 تم حفظ الاسم: <b>{html.escape(name)}</b>\n\nالآن أرسل <b>وصف الخدمة</b> والشروط والتفاصيل للعميل:",
        parse_mode='HTML'
    )


@router.message(AdminAddDigitalServiceStates.waiting_for_desc)
async def handle_service_add_desc(message: Message, state: FSMContext):
    desc = message.text.strip()
    await state.update_data(srv_desc=desc)
    await state.set_state(AdminAddDigitalServiceStates.waiting_for_type)
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏷️ خدمة بسعر ثابت (شراء مباشر)", callback_data="adm_srv_settype:FIXED")],
        [InlineKeyboardButton(text="💼 خدمة مخصصة (تسعير وعرض سعر)", callback_data="adm_srv_settype:CUSTOM")],
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="adm_services_list")]
    ])
    await message.answer(
        "⚙️ اختر <b>نوع تسعير الخدمة</b>:",
        reply_markup=markup,
        parse_mode='HTML'
    )


@router.callback_query(F.data.startswith("adm_srv_settype:"))
async def handle_service_add_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    stype = callback.data.split(":")[1]
    await state.update_data(srv_type=stype)
    
    if stype == 'FIXED':
        await state.set_state(AdminAddDigitalServiceStates.waiting_for_price)
        await callback.message.answer(
            "💰 أدخل <b>سعر الخدمة الثابت بالريال اليمني (YER)</b> (مثال: 5000):",
            parse_mode='HTML'
        )
    else:
        await state.update_data(srv_price=Decimal('0.00'))
        await state.set_state(AdminAddDigitalServiceStates.waiting_for_instructions)
        await callback.message.answer(
            "📋 أرسل <b>البيانات أو الحقول المطلوبة من العميل</b> عند طلب الخدمة (مثال: 'أرسل رابط الحساب والبريد الإلكتروني'):",
            parse_mode='HTML'
        )


@router.message(AdminAddDigitalServiceStates.waiting_for_price)
async def handle_service_add_price(message: Message, state: FSMContext):
    txt = message.text.strip().replace(',', '')
    try:
        val = Decimal(txt)
        if val < 0:
            raise ValueError()
    except Exception:
        await message.answer("⚠️ يرجى إدخال رقم صحيح وموجب للسعر (مثال: 5000):")
        return
    await state.update_data(srv_price=val)
    await state.set_state(AdminAddDigitalServiceStates.waiting_for_instructions)
    await message.answer(
        "📋 أرسل الآن <b>البيانات أو التعليمات المطلوبة من العميل</b> عند الشراء (مثال: 'أدخل رقم الهوية أو الـ ID الخاص بحسابك'):",
        parse_mode='HTML'
    )


@router.message(AdminAddDigitalServiceStates.waiting_for_instructions)
async def handle_service_add_finish(message: Message, state: FSMContext):
    instructions = message.text.strip()
    data = await state.get_data()
    await state.clear()

    name = data.get('srv_name')
    desc = data.get('srv_desc')
    stype = data.get('srv_type', 'FIXED')
    price = data.get('srv_price', Decimal('0.00'))

    def _create():
        return DigitalService.objects.create(
            name=name,
            description=desc,
            service_type=stype,
            price_yer=price,
            instructions=instructions,
            is_active=True
        )

    srv = await sync_to_async(_create)()

    await message.answer(
        f"✅ <b>تمت إضافة الخدمة الرقمية بنجاح!</b>\n\n"
        f"🛠 الاسم: <b>{html.escape(srv.name)}</b>\n"
        f"🏷 النوع: <b>{'سعر ثابت' if srv.service_type == 'FIXED' else 'تسعير مخصص'}</b>\n"
        f"💰 السعر: <b>{srv.price_yer:,.0f} YER</b>\n\n"
        f"الخدمة الآن متاحة للعملاء في بوت العميل تحت قسم <b>🛎 الخدمات</b>.",
        parse_mode='HTML'
    )
    await handle_admin_services_list(message)


@router.callback_query(F.data == "adm_srv_reqs")
async def handle_service_requests_list(callback: CallbackQuery):
    """View pending service quotation requests from customers."""
    await callback.answer()
    
    def _fetch_pending():
        return list(ServiceRequest.objects.filter(status='PENDING_QUOTE').select_related('service', 'user')[:10])

    reqs = await sync_to_async(_fetch_pending)()
    buttons = []
    text_lines = ["📋 <b>طلبات الخدمات المخصصة بانتظار التسعير:</b>\n━━━━━━━━━━━━━━━━━━"]

    if not reqs:
        text_lines.append("لا توجد طلبات معلقة بانتظار التسعير حالياً.")
    else:
        for r in reqs:
            user_label = r.user.first_name or r.user.username or str(r.user.telegram_id)
            text_lines.append(
                f"🔹 <b>طلب #{str(r.id)[:6]}</b>\n"
                f"الخدمة: <b>{html.escape(r.service.name)}</b>\n"
                f"العميل: {html.escape(user_label)}\n"
                f"ملاحظات العميل: <i>{html.escape(r.customer_notes[:100])}</i>\n"
            )

    text_lines.append("━━━━━━━━━━━━━━━━━━")
    buttons.append([InlineKeyboardButton(text="🔙 عودة لقائمة الخدمات", callback_data="adm_services_list")])
    buttons.append([InlineKeyboardButton(text="🏠 الرئيسية", callback_data="adm_home")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await callback.message.edit_text("\n".join(text_lines), reply_markup=markup, parse_mode='HTML')
    except Exception:
        await callback.message.answer("\n".join(text_lines), reply_markup=markup, parse_mode='HTML')
