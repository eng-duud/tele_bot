import logging
from typing import List, Tuple
from django.conf import settings
from apps.notifications.models import RequiredChannel
from apps.orders.models import Order
from apps.payments.models import PaymentRequest

logger = logging.getLogger(__name__)

from asgiref.sync import sync_to_async

import time

_CHANNELS_CACHE = None
_CHANNELS_CACHE_TIME = 0.0

class ChannelSubscriptionService:
    """Service to strictly verify user membership in required Telegram channels."""

    @classmethod
    def clear_cache(cls):
        """Invalidate in-memory channels cache immediately."""
        global _CHANNELS_CACHE, _CHANNELS_CACHE_TIME
        _CHANNELS_CACHE = None
        _CHANNELS_CACHE_TIME = 0.0

    @classmethod
    async def get_missing_channels(cls, bot, telegram_user_id: int):
        """Check all active mandatory channels and return ones the user has NOT joined."""
        global _CHANNELS_CACHE, _CHANNELS_CACHE_TIME
        import os
        from types import SimpleNamespace
        from aiogram.exceptions import TelegramBadRequest

        now = time.time()
        if _CHANNELS_CACHE is not None and (now - _CHANNELS_CACHE_TIME < 20.0):
            db_channels = _CHANNELS_CACHE
        else:
            try:
                db_channels = await sync_to_async(list)(
                    RequiredChannel.objects.filter(is_mandatory=True, is_active=True)
                )
            except Exception as db_err:
                logger.warning(f"Could not load required channels from DB: {db_err}")
                db_channels = []
            _CHANNELS_CACHE = db_channels
            _CHANNELS_CACHE_TIME = now

        # Also incorporate channels configured in .env (قناة المتجر وقناة التفعيلات)
        env_channels_config = [
            {
                'id': (getattr(settings, 'REQUIRED_CHANNEL_ID', '') or os.getenv('REQUIRED_CHANNEL_ID', '')).strip(),
                'url': (getattr(settings, 'REQUIRED_CHANNEL_URL', '') or os.getenv('REQUIRED_CHANNEL_URL', '')).strip(),
                'title': (getattr(settings, 'REQUIRED_CHANNEL_TITLE', '') or os.getenv('REQUIRED_CHANNEL_TITLE', 'قناة المتجر الرسمية')).strip() or 'قناة المتجر الرسمية'
            },
            {
                'id': (getattr(settings, 'SUCCESS_CHANNEL_ID', '') or os.getenv('SUCCESS_CHANNEL_ID', '')).strip(),
                'url': (getattr(settings, 'SUCCESS_CHANNEL_URL', '') or os.getenv('SUCCESS_CHANNEL_URL', '')).strip(),
                'title': (getattr(settings, 'SUCCESS_CHANNEL_TITLE', '') or os.getenv('SUCCESS_CHANNEL_TITLE', 'قناة التفعيلات المباشرة')).strip() or 'قناة التفعيلات المباشرة'
            }
        ]

        all_channels = list(db_channels)

        for cfg in env_channels_config:
            cid = cfg['id']
            if cid and cid.lower() not in ('@yourchannel', '@your_channel', 'your_channel_id', '@yourstore', 'none', ''):
                already_in_list = any(str(getattr(c, 'channel_id', '')).lower() == cid.lower() for c in all_channels)
                invite = cfg['url'] or (f"https://t.me/{cid.lstrip('@')}" if cid.startswith('@') else "")
                
                if not already_in_list:
                    env_obj = SimpleNamespace(
                        id=f'env_{cid}',
                        channel_id=cid,
                        channel_title=cfg['title'],
                        invite_link=invite,
                        is_mandatory=True,
                        is_active=True
                    )
                    all_channels.append(env_obj)

                # Auto-sync/upsert to DB so it persists and is visible in admin dashboard
                try:
                    def _sync_env_to_db(ch_id=cid, ch_title=cfg['title'], ch_link=invite):
                        RequiredChannel.objects.update_or_create(
                            channel_id=ch_id,
                            defaults={
                                'channel_title': ch_title,
                                'invite_link': ch_link or f"https://t.me/{ch_id.lstrip('@')}",
                                'is_mandatory': True,
                                'is_active': True,
                            }
                        )
                    await sync_to_async(_sync_env_to_db)()
                except Exception as sync_e:
                    logger.debug(f"Could not auto-sync channel {cid} to DB: {sync_e}")

        if not all_channels:
            return []

        missing = []
        for ch in all_channels:
            raw_cid = ch.channel_id
            # Support numeric supergroup/channel IDs (e.g. -100...)
            cid = int(raw_cid) if (isinstance(raw_cid, str) and (raw_cid.startswith('-') or raw_cid.isdigit())) else raw_cid
            try:
                member = await bot.get_chat_member(chat_id=cid, user_id=telegram_user_id)
                # Valid subscribed statuses: member, administrator, creator, restricted
                if member.status not in ('member', 'administrator', 'creator', 'restricted'):
                    missing.append(ch)
            except TelegramBadRequest as e:
                err_msg = str(e).lower()
                # User is NOT in the channel
                if "user not found" in err_msg or "participant" in err_msg or "not a member" in err_msg:
                    missing.append(ch)
                elif "chat not found" in err_msg or "member list is inaccessible" in err_msg or "admin" in err_msg:
                    logger.error(
                        f"⚠️ خطأ في فحص الاشتراك بالقناة '{ch.channel_title}' ({ch.channel_id}): "
                        f"البوت ليس مشرفاً (Admin) في القناة أو المعرف غير صحيح! "
                        f"يرجى إضافة البوت مشرفاً في القناة أولاً لكي يتمكن من فحص الأعضاء. تفاصيل الخطأ: {e}"
                    )
                    # Fail closed: if membership cannot be verified, do not
                    # grant access. Otherwise a user could bypass a mandatory
                    # channel simply because the bot lost admin permissions.
                    missing.append(ch)
                else:
                    logger.warning(f"TelegramBadRequest for user {telegram_user_id} in {ch.channel_id}: {e}")
                    missing.append(ch)
            except Exception as e:
                logger.warning(f"Unexpected error checking membership for {telegram_user_id} in {ch.channel_id}: {e}")
                missing.append(ch)

        return missing



class SuccessChannelService:
    """Publish sanitized receipts to the public success channel."""

    @staticmethod
    def _extract_broadcast_data(order: Order):
        items = list(order.items.all())
        if items:
            total_qty = sum(it.quantity for it in items)
            if len(items) == 1:
                prod_name = items[0].product_name_snapshot
            else:
                prod_name = f"{items[0].product_name_snapshot} (+{len(items)-1} منتجات)"
        else:
            total_qty = 1
            prod_name = "منتج رقمي"

        raw_id_str = str(order.user.telegram_id)
        masked_id = f"***{raw_id_str[-4:]}" if len(raw_id_str) >= 4 else "***"
        return prod_name, total_qty, masked_id

    @classmethod
    def broadcast_order(cls, bot_or_order, maybe_order=None):
        """Send anonymized successful purchase receipt with quantity to public channel. Supports sync & async."""
        import asyncio
        if maybe_order is not None:
            bot = bot_or_order
            order = maybe_order
        else:
            order = bot_or_order
            from apps.telegram_bot.common.bot_instances import get_customer_bot
            bot = get_customer_bot()

        async def _do_broadcast():
            if not bot or not order:
                return

            channel_id = getattr(settings, 'SUCCESS_CHANNEL_ID', '')
            if not channel_id or channel_id.startswith('@YourStore'):
                return

            prod_name, total_qty, masked_id = await sync_to_async(cls._extract_broadcast_data)(order)

            import html
            esc_prod = html.escape(prod_name)
            text = (
                f"🎉 <b>عملية شراء وتسليم ناجحة!</b> ⚡\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔖 <b>رقم الطلب:</b> <code>{order.order_number}</code>\n"
                f"🛍 <b>المنتج:</b> <b>{esc_prod}</b>\n"
                f"🔢 <b>الكمية:</b> <b>{total_qty} قطعة</b>\n"
                f"💰 <b>الإجمالي:</b> <b>{order.total_amount_yer:,.0f} YER</b>\n"
                f"👤 <b>المشتري:</b> العميل <code>{masked_id}</code>\n"
                f"⚡ <b>حالة التسليم:</b> فوري ومباشر وآلي ✅\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🌟 <i>شكراً لثقتكم واختياركم متجرنا الرقمي!</i>"
            )

            plain_text = (
                f"🎉 عملية شراء وتسليم ناجحة! ⚡\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔖 رقم الطلب: {order.order_number}\n"
                f"🛍 المنتج: {prod_name}\n"
                f"🔢 الكمية: {total_qty} قطعة\n"
                f"💰 الإجمالي: {order.total_amount_yer:,.0f} YER\n"
                f"👤 المشتري: العميل {masked_id}\n"
                f"⚡ حالة التسليم: فوري ومباشر وآلي ✅\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🌟 شكراً لثقتكم واختياركم متجرنا الرقمي!"
            )

            try:
                await bot.send_message(chat_id=channel_id, text=text, parse_mode='HTML')
            except Exception:
                try:
                    await bot.send_message(chat_id=channel_id, text=plain_text, parse_mode=None)
                except Exception as e:
                    logger.error(f"Failed to post to success channel {channel_id}: {e}")

        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(_do_broadcast())
        except RuntimeError:
            return asyncio.run(_do_broadcast())



class AdminGroupNotifierService:
    """Send interactive approval cards and critical alerts to the super admin and admin group."""

    @staticmethod
    def _prepare_card_data(payment_request: PaymentRequest):
        import html
        raw_user_name = payment_request.user.full_name or "عميل"
        user_name = html.escape(raw_user_name)
        telegram_id = payment_request.user.telegram_id
        username = payment_request.user.username
        method_name = html.escape(payment_request.payment_method.name)
        raw_tx = payment_request.tx_number or 'لا يوجد'
        tx_no = html.escape(raw_tx)
        status_display = html.escape(payment_request.get_status_display())

        # Customer identity with clickable link via ID or Username
        user_mention = f'<a href="tg://user?id={telegram_id}">{user_name}</a>'
        if username:
            clean_username = username.lstrip('@')
            user_field_html = (
                f"👤 <b>العميل:</b> {user_mention}\n"
                f"🔗 <b>اسم المستخدم:</b> @{html.escape(clean_username)} (<a href=\"https://t.me/{clean_username}\">مراسلة</a>)\n"
                f"🆔 <b>آيدي العميل:</b> <code>{telegram_id}</code>"
            )
            user_field_plain = (
                f"👤 العميل: {raw_user_name}\n"
                f"🔗 اسم المستخدم: @{clean_username} (https://t.me/{clean_username})\n"
                f"🆔 آيدي العميل: {telegram_id}"
            )
        else:
            user_field_html = (
                f"👤 <b>العميل:</b> {user_mention}\n"
                f"🆔 <b>آيدي العميل:</b> <code>{telegram_id}</code> (<a href=\"tg://user?id={telegram_id}\">رابط الحساب</a>)"
            )
            user_field_plain = (
                f"👤 العميل: {raw_user_name}\n"
                f"🆔 آيدي العميل: {telegram_id} (tg://user?id={telegram_id})"
            )

        text_html = (
            f"💳 <b>طلب شحن رصيد جديد</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{user_field_html}\n"
            f"💰 <b>المبلغ:</b> <b>{payment_request.amount_yer:,.0f} YER</b>\n"
            f"🏦 <b>طريقة الدفع:</b> {method_name}\n"
            f"🔢 <b>رقم العملية:</b> <code>{tx_no}</code>\n"
            f"⏱ <b>الحالة:</b> {status_display}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"يرجى مطابقة رقم العملية واتخاذ الإجراء:"
        )

        plain_text = (
            f"💳 طلب شحن رصيد جديد\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{user_field_plain}\n"
            f"💰 المبلغ: {payment_request.amount_yer:,.0f} YER\n"
            f"🏦 طريقة الدفع: {payment_request.payment_method.name}\n"
            f"🔢 رقم العملية: {raw_tx}\n"
            f"⏱ الحالة: {payment_request.get_status_display()}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"يرجى مطابقة رقم العملية واتخاذ الإجراء:"
        )

        return {
            'text': text_html,
            'plain_text': plain_text,
            'photo_id': payment_request.proof_image_file_id,
            'photo_url': payment_request.proof_image_url,
            'id': str(payment_request.id),
            'username': username.lstrip('@') if username else None,
            'telegram_id': telegram_id
        }

    @classmethod
    async def send_payment_request_card(cls, bot, payment_request: PaymentRequest):
        """Send top-up verification card to both Super Admin private chat and Admin Group."""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
        from apps.telegram_bot.common.bot_instances import get_admin_bot, get_customer_bot

        admin_bot = get_admin_bot() or bot
        cust_bot = get_customer_bot() or bot

        card_data = await sync_to_async(cls._prepare_card_data)(payment_request)

        contact_btn = (
            InlineKeyboardButton(text="👤 مراسلة العميل", url=f"https://t.me/{card_data['username']}")
            if card_data.get('username')
            else InlineKeyboardButton(text="👤 مراسلة العميل", callback_data=f"adm_contact:{card_data['telegram_id']}")
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ قبول وإيداع الرصيد", callback_data=f"adm_pay_approve:{card_data['id']}"),
                InlineKeyboardButton(text="❌ رفض الطلب", callback_data=f"adm_pay_reject:{card_data['id']}")
            ],
            [
                contact_btn
            ]
        ])

        # 1. Download photo bytes from Telegram directly into RAM so any bot can send it reliably
        photo_bytes = None
        file_id = payment_request.proof_image_file_id
        if file_id:
            for dl_bot in [bot, cust_bot, admin_bot]:
                if not dl_bot:
                    continue
                try:
                    stream = await dl_bot.download(file_id)
                    if stream:
                        photo_bytes = stream.read()
                        if photo_bytes:
                            break
                except Exception as dl_err:
                    logger.debug(f"Could not download receipt image using {dl_bot}: {dl_err}")

        # Helper to extract migrated supergroup ID
        import re
        from pathlib import Path

        def extract_migrated_chat_id(err: Exception):
            params = getattr(err, 'parameters', None)
            if params and getattr(params, 'migrate_to_chat_id', None):
                return params.migrate_to_chat_id
            msg = str(err)
            match = re.search(r'migrated to a supergroup with id\s*(-?\d+)', msg, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
            match2 = re.search(r'migrate_to_chat_id\s*=\s*(-?\d+)', msg, re.IGNORECASE)
            if match2:
                try:
                    return int(match2.group(1))
                except ValueError:
                    pass
            return None

        def update_env_group_id(new_id: str):
            try:
                env_path = Path(settings.BASE_DIR) / '.env'
                if not env_path.exists():
                    return
                content = env_path.read_text(encoding='utf-8')
                if 'ADMIN_GROUP_ID=' in content:
                    new_content = re.sub(r'ADMIN_GROUP_ID=[^\r\n]*', f'ADMIN_GROUP_ID={new_id}', content)
                else:
                    new_content = content + f"\nADMIN_GROUP_ID={new_id}\n"
                env_path.write_text(new_content, encoding='utf-8')
                logger.info(f"✅ Auto-updated ADMIN_GROUP_ID={new_id} in .env file.")
            except Exception as env_err:
                logger.warning(f"Could not persist ADMIN_GROUP_ID in .env: {env_err}")

        # Delivery helper with complete multi-tier fallback and automatic supergroup migration handling
        async def _deliver(sender, target_chat_id):
            if not sender:
                return None

            current_target = target_chat_id
            for attempt in range(2):
                try:
                    # Try 1: Send photo as BufferedInputFile with HTML
                    if photo_bytes:
                        try:
                            return await sender.send_photo(
                                chat_id=current_target,
                                photo=BufferedInputFile(photo_bytes, filename=f"payment_{payment_request.id}.jpg"),
                                caption=card_data['text'],
                                reply_markup=keyboard,
                                parse_mode='HTML'
                            )
                        except Exception as ex1:
                            migrated = extract_migrated_chat_id(ex1)
                            if migrated:
                                raise ex1
                            logger.debug(f"Send photo HTML failed: {ex1}")

                        # Try 2: Send photo as BufferedInputFile with plain text
                        try:
                            return await sender.send_photo(
                                chat_id=current_target,
                                photo=BufferedInputFile(photo_bytes, filename=f"payment_{payment_request.id}.jpg"),
                                caption=card_data['plain_text'],
                                reply_markup=keyboard
                            )
                        except Exception as ex2:
                            migrated = extract_migrated_chat_id(ex2)
                            if migrated:
                                raise ex2
                            logger.warning(f"Send photo plain failed: {ex2}")

                    # Try 3: Direct file_id if sender is the bot that received the photo
                    if file_id:
                        try:
                            return await sender.send_photo(
                                chat_id=current_target,
                                photo=file_id,
                                caption=card_data['text'],
                                reply_markup=keyboard,
                                parse_mode='HTML'
                            )
                        except Exception as ex3:
                            migrated = extract_migrated_chat_id(ex3)
                            if migrated:
                                raise ex3

                    # Try 4: Send text message with HTML
                    try:
                        return await sender.send_message(
                            chat_id=current_target,
                            text=card_data['text'],
                            reply_markup=keyboard,
                            parse_mode='HTML'
                        )
                    except Exception as ex4:
                        migrated = extract_migrated_chat_id(ex4)
                        if migrated:
                            raise ex4

                    # Try 5: Send plain text message
                    return await sender.send_message(
                        chat_id=current_target,
                        text=card_data['plain_text'],
                        reply_markup=keyboard
                    )

                except Exception as err:
                    migrated_id = extract_migrated_chat_id(err)
                    if migrated_id and str(current_target) != str(migrated_id):
                        logger.info(f"🔄 Group was migrated to supergroup {migrated_id} from {current_target}. Auto-updating and retrying...")
                        current_target = str(migrated_id)
                        setattr(settings, 'ADMIN_GROUP_ID', str(migrated_id))
                        update_env_group_id(str(migrated_id))
                        continue
                    raise err

            return None

        # 2. Deliver exclusively to Admin Group / Channel if configured
        admin_group_id = getattr(settings, 'ADMIN_GROUP_ID', '')
        delivered_to_group = False

        if admin_group_id:
            senders = [admin_bot] if admin_bot else ([bot] if bot else [])
            for sender in senders:
                try:
                    msg = await _deliver(sender, admin_group_id)
                    if msg:
                        delivered_to_group = True
                        def save_admin_msg_id():
                            payment_request.admin_message_id = msg.message_id
                            payment_request.save(update_fields=['admin_message_id'])

                        await sync_to_async(save_admin_msg_id)()
                        break
                except Exception as e:
                    logger.warning(f"Could not send payment card to admin group via {sender}: {e}")

        # 3. Only fallback to Super Admin private chat if Admin Group is NOT configured or failed
        if not delivered_to_group:
            super_admin_id = getattr(settings, 'SUPER_ADMIN_TELEGRAM_ID', 0)
            if super_admin_id:
                for sender in [admin_bot, bot]:
                    if not sender:
                        continue
                    try:
                        res = await _deliver(sender, super_admin_id)
                        if res:
                            break
                    except Exception as e:
                        logger.warning(f"Could not send payment notification to Super Admin {super_admin_id} via {sender}: {e}")

    @classmethod
    def send_order_issue_alert(cls, order: Order, reason: str = ""):
        """Alert super admin and admin group about order fulfillment failure."""
        from asgiref.sync import async_to_sync
        from apps.telegram_bot.common.bot_instances import get_admin_bot
        from apps.core.utils import escape_md

        admin_bot = get_admin_bot()
        if not admin_bot:
            return

        item = order.items.first()
        prod_name = escape_md(item.product_name_snapshot if item else "منتج رقمي")
        u_name = escape_md(order.user.full_name)
        clean_reason = escape_md(reason or "فشل غير محدد")

        text = (
            f"⚠️ *تنبيه: فشل تسليم طلب رقمي*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔖 *رقم الطلب:* `{order.order_number}`\n"
            f"👤 *العميل:* {u_name} (`{order.user.telegram_id}`)\n"
            f"🛍 *المنتج:* {prod_name}\n"
            f"💰 *المبلغ المسترجع:* *{order.total_amount_yer:,.0f} YER*\n"
            f"❌ *سبب الفشل:* {clean_reason}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"ℹ️ تم استرجاع المبلغ لمحفظة العميل تلقائياً وتسجيل المشكلة في لوحة الإدارة."
        )

        async def _deliver():
            super_admin_id = getattr(settings, 'SUPER_ADMIN_TELEGRAM_ID', 0)
            if super_admin_id:
                try:
                    await admin_bot.send_message(chat_id=super_admin_id, text=text, parse_mode='Markdown')
                except Exception as ex:
                    logger.warning(f"Could not send order issue alert to super admin: {ex}")

            admin_group_id = getattr(settings, 'ADMIN_GROUP_ID', '')
            if admin_group_id:
                try:
                    await admin_bot.send_message(chat_id=admin_group_id, text=text, parse_mode='Markdown')
                except Exception as ex:
                    migrated = extract_migrated_chat_id(ex)
                    if migrated:
                        setattr(settings, 'ADMIN_GROUP_ID', str(migrated))
                        update_env_group_id(str(migrated))
                        try:
                            await admin_bot.send_message(chat_id=migrated, text=text, parse_mode='Markdown')
                        except Exception:
                            pass
                    else:
                        logger.warning(f"Could not send order issue alert to admin group: {ex}")

        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                asyncio.create_task(_deliver())
            else:
                async_to_sync(_deliver)()
        except Exception as e:
            logger.error(f"Error dispatching order issue alert: {e}")


class RestockNotifierService:
    """Service to notify waiting customers when out-of-stock products are replenished."""

    @classmethod
    async def notify_subscribers(cls, product) -> int:
        """Alert all registered users waiting for this product restock."""
        from apps.telegram_bot.common.bot_instances import get_customer_bot
        from apps.inventory.services import InventoryService
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        customer_bot = get_customer_bot()
        if not customer_bot:
            return 0

        users = await sync_to_async(InventoryService.get_pending_restock_subscribers)(product)
        if not users:
            return 0

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 شراء المنتج الآن", callback_data=f"buy:{product.id}")],
            [InlineKeyboardButton(text="🛍 عرض تفاصيل المنتج", callback_data=f"prod:{product.id}")]
        ])

        text = (
            f"🔔 *بشرى سارة! توفر المنتج مجدداً في المتجر* 🎉\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"عزيزي العميل، لقد طلبت تنبيهك فور توفر:\n"
            f"🏷 *{product.name}*\n\n"
            f"💰 السعر: *{product.price:,.0f} {product.base_currency}*\n"
            f"📦 أصبح المنتج متوفراً الآن في المخزون وبإمكانك شراؤه فوراً!"
        )

        sent_count = 0
        for user in users:
            try:
                await customer_bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send restock notification to {user.telegram_id}: {e}")

        return sent_count


class CustomerNotifierService:
    """Delivers automated order updates and notifications directly to customers."""

    @classmethod
    def send_order_delivered(cls, order: Order):
        """Notify customer that digital item has been successfully delivered."""
        from asgiref.sync import async_to_sync
        from apps.telegram_bot.common.bot_instances import get_customer_bot
        from apps.core.utils import escape_md

        customer_bot = get_customer_bot()
        if not customer_bot:
            return

        import html
        item = order.items.first()
        prod_name = html.escape(item.product_name_snapshot if item else "المنتج الرقمي")
        raw_info = order.delivered_data or "تم التفعيل والتسليم بنجاح."
        delivered_info = html.escape(raw_info)

        text_html = (
            f"🎉 <b>مبروك! تم تسليم طلبك بنجاح</b> 📦✨\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔖 <b>رقم الطلب:</b> <code>{order.order_number}</code>\n"
            f"🛍 <b>المنتج:</b> {prod_name}\n"
            f"💰 <b>المبلغ:</b> <b>{order.total_amount_yer:,.0f} YER</b>\n\n"
            f"🔑 <b>بيانات الاستلام والتفعيل:</b>\n"
            f"<code>{delivered_info}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"يمكنك دائماً مراجعة هذا الطلب من زر <b>📦 طلباتي</b>.\n"
            f"شكراً لتسوقك وثقتك بمتجرنا! 🌟"
        )

        plain_text = (
            f"🎉 مبروك! تم تسليم طلبك بنجاح 📦✨\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔖 رقم الطلب: {order.order_number}\n"
            f"🛍 المنتج: {item.product_name_snapshot if item else 'المنتج الرقمي'}\n"
            f"💰 المبلغ: {order.total_amount_yer:,.0f} YER\n\n"
            f"🔑 بيانات الاستلام والتفعيل:\n"
            f"{raw_info}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"يمكنك دائماً مراجعة هذا الطلب من زر طلباتي.\n"
            f"شكراً لتسوقك وثقتك بمتجرنا! 🌟"
        )

        async def _deliver():
            try:
                await customer_bot.send_message(
                    chat_id=order.user.telegram_id,
                    text=text_html,
                    parse_mode='HTML'
                )
            except Exception:
                try:
                    await customer_bot.send_message(
                        chat_id=order.user.telegram_id,
                        text=plain_text
                    )
                except Exception as e:
                    logger.warning(f"Failed to deliver order completed message to {order.user.telegram_id}: {e}")

        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                asyncio.create_task(_deliver())
            else:
                async_to_sync(_deliver)()
        except Exception as ex:
            logger.error(f"Error dispatching customer order delivered alert: {ex}")

    @classmethod
    def send_order_failed_refunded(cls, order: Order, reason: str = ""):
        """Notify customer that automated order failed and balance was refunded."""
        from asgiref.sync import async_to_sync
        from apps.telegram_bot.common.bot_instances import get_customer_bot
        import html

        customer_bot = get_customer_bot()
        if not customer_bot:
            return

        item = order.items.first()
        prod_name = html.escape(item.product_name_snapshot if item else "المنتج")
        clean_reason = html.escape(reason or "تعذر المعالجة من المزود")

        text_html = (
            f"⚠️ <b>تنبيه بخصوص طلبك #{order.order_number}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🛍 <b>المنتج:</b> {prod_name}\n"
            f"نعتذر منك، تعذر إتمام تسليم الطلب تلقائياً في الوقت الحالي.\n"
            f"السبب: {clean_reason}\n\n"
            f"💰 <b>تم استرجاع كامل المبلغ (+{order.total_amount_yer:,.0f} YER) إلى محفظتك بنجاح!</b> ✅\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"يمكنك استخدام رصيدك في أي وقت لشراء منتج آخر أو التواصل مع الدعم الفني."
        )

        plain_text = (
            f"⚠️ تنبيه بخصوص طلبك #{order.order_number}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🛍 المنتج: {item.product_name_snapshot if item else 'المنتج'}\n"
            f"نعتذر منك، تعذر إتمام تسليم الطلب تلقائياً في الوقت الحالي.\n"
            f"السبب: {reason or 'تعذر المعالجة من المزود'}\n\n"
            f"💰 تم استرجاع كامل المبلغ (+{order.total_amount_yer:,.0f} YER) إلى محفظتك بنجاح! ✅\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"يمكنك استخدام رصيدك في أي وقت لشراء منتج آخر أو التواصل مع الدعم الفني."
        )

        async def _deliver():
            try:
                await customer_bot.send_message(
                    chat_id=order.user.telegram_id,
                    text=text_html,
                    parse_mode='HTML'
                )
            except Exception:
                try:
                    await customer_bot.send_message(
                        chat_id=order.user.telegram_id,
                        text=plain_text
                    )
                except Exception as e:
                    logger.warning(f"Failed to deliver refund message to {order.user.telegram_id}: {e}")

        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                asyncio.create_task(_deliver())
            else:
                async_to_sync(_deliver)()
        except Exception as ex:
            logger.error(f"Error dispatching customer refund alert: {ex}")
