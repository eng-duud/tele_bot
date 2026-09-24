from aiogram import Router, F
from aiogram.types import CallbackQuery
from asgiref.sync import sync_to_async
from apps.users.services import UserService
from apps.telegram_bot.common.keyboards import get_settings_keyboard

router = Router()

@router.callback_query(F.data.startswith("set_curr:"))
async def handle_change_currency(callback: CallbackQuery):
    """Switch user's preferred currency dynamically."""
    await callback.answer()
    currency = callback.data.split(":")[1]

    profile = await sync_to_async(UserService.set_preferred_currency)(
        telegram_id=callback.from_user.id,
        currency=currency
    )

    if profile:
        curr_label = "🇾🇪 الريال اليمني (YER)" if currency == 'YER' else "🇺🇸 الدولار الأمريكي (USD)"
        await callback.message.edit_text(
            f"✅ تم تغيير عملة عرض الأسعار إلى: *{curr_label}* بنجاح!\n\n"
            "سيتم عرض أسعار كافة المنتجات الآن بعملتك المفضلة.",
            reply_markup=get_settings_keyboard(currency),
            parse_mode='Markdown'
        )
