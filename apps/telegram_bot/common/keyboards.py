from typing import List, Optional
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from apps.catalog.models import Category, Product
from apps.payments.models import PaymentMethod

def get_customer_main_menu() -> ReplyKeyboardMarkup:
    """Customer persistent main menu."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 المتجر"), KeyboardButton(text="📂 الأقسام")],
            [KeyboardButton(text="💰 المحفظة"), KeyboardButton(text="📦 طلباتي")],
            [KeyboardButton(text="🛎 الخدمات"), KeyboardButton(text="👤 حسابي")],
            [KeyboardButton(text="🎧 الدعم الفني")]
        ],
        resize_keyboard=True
    )


def get_categories_keyboard(categories: List[Category], parent_id: Optional[str] = None) -> InlineKeyboardMarkup:
    """Hierarchical categories inline keyboard."""
    buttons = []
    # Two categories per row
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(text=f"{cat.icon} {cat.name}", callback_data=f"cat:{cat.id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    nav_row = []
    if parent_id:
        nav_row.append(InlineKeyboardButton(text="🔙 رجوع للأقسام", callback_data="cat_root"))
    nav_row.append(InlineKeyboardButton(text="🏠 الرئيسية", callback_data="menu_home"))
    buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_products_keyboard(products: List[Product], category_id: str) -> InlineKeyboardMarkup:
    """Product list inline keyboard for a category with actual stock quantity indicator."""
    from apps.catalog.services import CatalogService
    buttons = []
    for prod in products:
        try:
            in_stock = CatalogService.is_in_stock(prod)
        except Exception:
            in_stock = getattr(prod, 'is_active', True)
        badge = "🟢" if in_stock else "🔴"
        if not in_stock:
            stock_label = " (نفد مؤقتاً)"
        elif prod.stock_type == 'QUANTITY':
            stock_label = f" (متوفر: {prod.stock_quantity})"
        elif prod.stock_type == 'INDIVIDUAL_ITEMS':
            from apps.inventory.models import StockItem
            cnt = StockItem.objects.filter(product=prod, status='AVAILABLE').count()
            stock_label = f" (متوفر: {cnt})"
        elif prod.stock_type in ('UNLIMITED', 'API_CAPACITY'):
            stock_label = " (متوفر فوري)"
        else:
            stock_label = ""
        buttons.append([InlineKeyboardButton(text=f"{badge} {prod.name}{stock_label}", callback_data=f"prod:{prod.id}")])

    buttons.append([
        InlineKeyboardButton(text="🔙 رجوع", callback_data="cat_root"),
        InlineKeyboardButton(text="🏠 الرئيسية", callback_data="menu_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_product_detail_keyboard(product: Product, in_stock: bool) -> InlineKeyboardMarkup:
    """Action keyboard for product view."""
    buttons = []
    if in_stock:
        buttons.append([InlineKeyboardButton(text="🛒 شراء المنتج الآن", callback_data=f"buy:{product.id}")])
    else:
        buttons.append([InlineKeyboardButton(text="🔔 أبلغني عند توفر المخزون", callback_data=f"restock_sub:{product.id}")])

    buttons.append([
        InlineKeyboardButton(text="🔙 رجوع للمنتجات", callback_data="cat_root"),
        InlineKeyboardButton(text="🏠 الرئيسية", callback_data="menu_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_quantity_selector_keyboard(
    product_id: str, 
    current_qty: int, 
    max_stock: int, 
    total_price_yer: float, 
    has_sufficient_balance: bool
) -> InlineKeyboardMarkup:
    """Dynamic interactive keyboard for adjusting and confirming purchase quantity."""
    buttons = []
    
    minus_qty = max(1, current_qty - 1)
    plus_qty = current_qty + 1 if (max_stock <= 0 or current_qty < max_stock) else current_qty

    # Row 1: - / current / +
    buttons.append([
        InlineKeyboardButton(text="➖", callback_data=f"buy_qty:{product_id}:{minus_qty}"),
        InlineKeyboardButton(text=f"🔢 الكمية: {current_qty}", callback_data="noop"),
        InlineKeyboardButton(text="➕", callback_data=f"buy_qty:{product_id}:{plus_qty}"),
    ])

    # Row 2: Quick quantities
    quick_nums = [2, 3, 5, 10]
    quick_row = []
    for q in quick_nums:
        if max_stock <= 0 or q <= max_stock:
            quick_row.append(InlineKeyboardButton(text=f"{q}", callback_data=f"buy_qty:{product_id}:{q}"))
    if quick_row:
        buttons.append(quick_row)

    # Row 3: Custom quantity input
    buttons.append([
        InlineKeyboardButton(text="✍️ كتابة كمية مخصصة", callback_data=f"buy_custom_qty:{product_id}")
    ])

    # Row 4: Confirm purchase
    if has_sufficient_balance:
        buttons.append([
            InlineKeyboardButton(text=f"✅ تأكيد وشراء ({total_price_yer:,.0f} YER)", callback_data=f"buy_confirm:{product_id}:{current_qty}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text=f"⚠️ الرصيد غير كافٍ ({total_price_yer:,.0f} YER)", callback_data="wallet_deposit")
        ])

    # Row 5: Back navigation
    buttons.append([
        InlineKeyboardButton(text="🔙 إلغاء والعودة للمنتج", callback_data=f"prod:{product_id}"),
        InlineKeyboardButton(text="🏠 الرئيسية", callback_data="menu_home")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_wallet_keyboard() -> InlineKeyboardMarkup:
    """Customer wallet actions keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ شحن الرصيد", callback_data="wallet_deposit")],
        [InlineKeyboardButton(text="📋 سجل المعاملات المالية", callback_data="wallet_history")],
        [InlineKeyboardButton(text="🏠 العودة للرئيسية", callback_data="menu_home")]
    ])


def get_payment_methods_keyboard(methods: List[PaymentMethod]) -> InlineKeyboardMarkup:
    """Active deposit methods keyboard."""
    buttons = []
    for m in methods:
        buttons.append([InlineKeyboardButton(text=f"{m.icon} {m.name}", callback_data=f"paymethod:{m.id}")])
    buttons.append([InlineKeyboardButton(text="🔙 إلغاء والعودة", callback_data="menu_wallet")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_keyboard(current_currency: str) -> InlineKeyboardMarkup:
    """Currency switcher keyboard."""
    yer_check = "✅ " if current_currency == 'YER' else ""
    usd_check = "✅ " if current_currency == 'USD' else ""

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{yer_check}🇾🇪 ريال يمني (YER)", callback_data="set_curr:YER")],
        [InlineKeyboardButton(text=f"{usd_check}🇺🇸 دولار أمريكي (USD)", callback_data="set_curr:USD")],
        [
            InlineKeyboardButton(text="👤 العودة لحسابي", callback_data="menu_account"),
            InlineKeyboardButton(text="🏠 الرئيسية", callback_data="menu_home")
        ]
    ])


def get_admin_main_menu() -> ReplyKeyboardMarkup:
    """Admin bot persistent control keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 لوحة التحكم والإحصائيات"), KeyboardButton(text="📥 طلبات الشحن المعلقة")],
            [KeyboardButton(text="🛍 إدارة المنتجات"), KeyboardButton(text="📂 الأقسام والتصنيفات")],
            [KeyboardButton(text="📦 إدارة المخزون المشفر"), KeyboardButton(text="📋 سجل وإدارة الطلبات")],
            [KeyboardButton(text="💳 طرق الدفع والشحن"), KeyboardButton(text="👥 إدارة العملاء والأرصدة")],
            [KeyboardButton(text="💵 أسعار الصرف والإعدادات"), KeyboardButton(text="📢 إذاعة وبث جماعي")],
            [KeyboardButton(text="📢 القنوات الإجبارية")]
        ],
        resize_keyboard=True
    )
