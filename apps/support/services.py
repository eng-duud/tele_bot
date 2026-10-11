import logging
import html
from typing import Tuple, Optional
from django.utils import timezone
from django.conf import settings
from asgiref.sync import sync_to_async
from apps.users.models import TelegramProfile
from apps.support.models import SupportTicket, TicketMessage

logger = logging.getLogger(__name__)

class SupportService:
    """Service handling support tickets, customer inquiries, and admin responses."""

    @classmethod
    def create_ticket(
        cls, 
        user: TelegramProfile, 
        text: str, 
        photo_file_id: str = "", 
        document_file_id: str = ""
    ) -> Tuple[SupportTicket, TicketMessage]:
        """Create a new support ticket with initial message."""
        clean_text = text.strip()
        subject = clean_text[:60] if clean_text else "استفسار ومرفق"

        ticket = SupportTicket.objects.create(
            user=user,
            subject=subject,
            status='OPEN'
        )

        msg = TicketMessage.objects.create(
            ticket=ticket,
            sender=user,
            is_from_admin=False,
            text=clean_text or "[مرفق صورة أو ملف]",
            photo_file_id=photo_file_id,
            document_file_id=document_file_id
        )

        return ticket, msg

    @classmethod
    def reply_to_ticket(
        cls, 
        ticket_id: str, 
        admin_profile: TelegramProfile, 
        reply_text: str
    ) -> Tuple[bool, str, Optional[SupportTicket]]:
        """Admin replies to customer ticket and dispatches response."""
        ticket = SupportTicket.objects.filter(id=ticket_id).select_related('user').first()
        if not ticket:
            return False, "التذكرة غير موجودة.", None

        if ticket.status == 'CLOSED':
            return False, "هذه التذكرة مغلقة بالفعل.", ticket

        clean_reply = reply_text.strip()
        if not clean_reply:
            return False, "نص الرد لا يمكن أن يكون فارغاً.", ticket

        # Record admin message
        TicketMessage.objects.create(
            ticket=ticket,
            sender=admin_profile,
            is_from_admin=True,
            text=clean_reply
        )

        now = timezone.now()
        ticket.status = 'ANSWERED'
        ticket.last_answered_by = admin_profile
        ticket.last_answered_at = now
        ticket.save(update_fields=['status', 'last_answered_by', 'last_answered_at', 'updated_at'])

        # Dispatch message to customer via Customer Bot
        try:
            from apps.telegram_bot.common.bot_instances import get_customer_bot
            customer_bot = get_customer_bot()
            if customer_bot:
                admin_name = html.escape(admin_profile.full_name or "فريق الدعم")
                esc_reply = html.escape(clean_reply)
                client_text = (
                    f"🎧 <b>رد جديد من فريق الدعم الفني</b> 💬\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🔖 <b>رقم التذكرة:</b> <code>{ticket.ticket_number}</code>\n"
                    f"👮‍♂️ <b>المشرف:</b> {admin_name}\n"
                    f"📅 <b>الوقت:</b> <code>{now.strftime('%Y-%m-%d %I:%M %p')}</code>\n\n"
                    f"📝 <b>الرد:</b>\n"
                    f"{esc_reply}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💡 <i>إذا كان لديك أي استفسار إضافي يمكنك مراسلتنا مجدداً من زر الدعم الفني.</i>"
                )

                import asyncio
                async def _send_cust():
                    try:
                        await customer_bot.send_message(
                            chat_id=ticket.user.telegram_id,
                            text=client_text,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logger.warning(f"Could not deliver support reply to customer {ticket.user.telegram_id}: {e}")

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_send_cust())
                except RuntimeError:
                    asyncio.run(_send_cust())
        except Exception as exc:
            logger.error(f"Error notifying customer about ticket reply: {exc}")

        return True, "تم إرسال الرد للعميل بنجاح.", ticket

    @classmethod
    def close_ticket(
        cls, 
        ticket_id: str, 
        admin_profile: TelegramProfile
    ) -> Tuple[bool, str, Optional[SupportTicket]]:
        """Close support ticket."""
        ticket = SupportTicket.objects.filter(id=ticket_id).first()
        if not ticket:
            return False, "التذكرة غير موجودة.", None

        ticket.status = 'CLOSED'
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=['status', 'closed_at', 'updated_at'])
        return True, "تم إغلاق التذكرة بنجاح.", ticket

    @classmethod
    async def send_ticket_card_to_admin_group(cls, bot, ticket: SupportTicket, msg: TicketMessage):
        """Send interactive ticket card to the Admin Group with action buttons."""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
        from apps.telegram_bot.common.bot_instances import get_admin_bot

        from apps.core.services import SystemSettingService
        from apps.notifications.models import RequiredChannel

        admin_bot = get_admin_bot() or bot

        def _get_support_target():
            # 1. DB Support Channel
            sup_ch = RequiredChannel.objects.filter(channel_type='SUPPORT', is_active=True).first()
            if sup_ch and sup_ch.channel_id:
                return str(sup_ch.channel_id).strip()
            # 2. SystemSetting SUPPORT_CHANNEL_ID
            val = SystemSettingService.get_setting('SUPPORT_CHANNEL_ID', '').strip()
            if val:
                return val
            # 3. settings.SUPPORT_CHANNEL_ID
            env_val = getattr(settings, 'SUPPORT_CHANNEL_ID', '').strip()
            if env_val:
                return env_val
            # 4. DB Admin Channel
            adm_ch = RequiredChannel.objects.filter(channel_type='ADMIN', is_active=True).first()
            if adm_ch and adm_ch.channel_id:
                return str(adm_ch.channel_id).strip()
            # 5. settings.ADMIN_GROUP_ID
            group_env = getattr(settings, 'ADMIN_GROUP_ID', '')
            if group_env:
                return str(group_env).strip()
            # 6. Fallback to Super Admin ID
            super_id = getattr(settings, 'SUPER_ADMIN_TELEGRAM_ID', 0)
            return str(super_id) if super_id else ""

        support_target = await sync_to_async(_get_support_target)()
        if not support_target:
            logger.warning("No support channel, admin group, or super admin configured to receive tickets.")
            return

        target_chat_id = int(support_target) if (support_target.startswith('-') or support_target.isdigit()) else support_target

        raw_user_name = ticket.user.full_name or "عميل"
        u_name = html.escape(raw_user_name)
        u_id = ticket.user.telegram_id
        username = ticket.user.username
        time_str = ticket.created_at.strftime("%Y-%m-%d %I:%M %p")

        user_mention = f'<a href="tg://user?id={u_id}">{u_name}</a>'
        user_line = (
            f"👤 <b>العميل:</b> {user_mention} (@{html.escape(username.lstrip('@'))})\n"
            if username else
            f"👤 <b>العميل:</b> {user_mention} (<code>{u_id}</code>)\n"
        )

        card_text = (
            f"🎧 <b>تذكرة دعم فني جديدة</b> 📩\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔖 <b>رقم التذكرة:</b> <code>{ticket.ticket_number}</code>\n"
            f"{user_line}"
            f"📅 <b>التاريخ:</b> <code>{time_str}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>نص رسالة العميل:</b>\n"
            f"<code>{html.escape(msg.text)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"يرجى الضغط على الزر أدناه للرد على العميل:"
        )

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✍️ الرد على العميل", callback_data=f"adm_ticket_reply:{ticket.id}"),
                InlineKeyboardButton(text="🔒 إغلاق التذكرة", callback_data=f"adm_ticket_close:{ticket.id}")
            ],
            [
                InlineKeyboardButton(text="👤 فتح محادثة العميل", url=f"tg://user?id={u_id}")
            ]
        ])

        try:
            # If photo attached
            if msg.photo_file_id:
                try:
                    sent = await admin_bot.send_photo(
                        chat_id=target_chat_id,
                        photo=msg.photo_file_id,
                        caption=card_text,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
                except Exception:
                    sent = await admin_bot.send_message(
                        chat_id=target_chat_id,
                        text=card_text,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
            else:
                sent = await admin_bot.send_message(
                    chat_id=target_chat_id,
                    text=card_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )

            if sent:
                def _save_msg_id():
                    ticket.admin_message_id = sent.message_id
                    ticket.save(update_fields=['admin_message_id'])
                await sync_to_async(_save_msg_id)()

        except Exception as e:
            logger.error(f"Failed to send support ticket card to admin group: {e}")
