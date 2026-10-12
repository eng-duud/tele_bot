from typing import Tuple, Optional
from django.conf import settings
from apps.users.models import TelegramProfile, AdminProfile, AdminPermission, AdminRole

class UserService:
    """Service to handle customer onboarding and profile management."""

    @staticmethod
    def get_or_create_user(
        telegram_id: int, 
        username: str = "", 
        first_name: str = "", 
        last_name: str = "",
        referrer_id: Optional[int] = None
    ) -> Tuple[TelegramProfile, bool, dict]:
        """
        Fetch or create a user by their Telegram numeric ID, with strict referral linking:
        - Only completely new users (never interacted/registered before) can be referred.
        - Existing users can never accept any referral link and their status is locked.
        - Users cannot refer themselves.
        - Referrers receive an immediate notification upon valid new referral entry.
        """
        referral_info = {
            'status': None,
            'message': '',
            'referrer_name': '',
            'referrer_id': None
        }

        # Check if user already exists in DB before get_or_create
        already_existed = TelegramProfile.objects.filter(telegram_id=telegram_id).exists()

        from apps.core.services import CurrencyService
        base_curr = CurrencyService.get_base_currency()

        profile, created = TelegramProfile.objects.get_or_create(
            telegram_id=telegram_id,
            defaults={
                'username': username or "",
                'first_name': first_name or "",
                'last_name': last_name or "",
                'preferred_currency': base_curr,
            }
        )

        updated = False

        # Handle referral logic if a referral code/referrer_id was passed
        if referrer_id is not None:
            if referrer_id == telegram_id:
                # 1. User tried to refer themselves
                referral_info['status'] = 'SELF_REFERRAL'
                referral_info['message'] = 'لا يمكن دعوة نفسك عبر رابط الإحالة.'
            elif already_existed or not created:
                # 2. User already used the bot before / already registered
                referral_info['status'] = 'ALREADY_REGISTERED'
                referral_info['message'] = 'أنت مسجل في البوت مسبقاً، لذا لا يمكن احتساب رابط الإحالة للمستخدمين السابقين.'
            else:
                # 3. Brand new user registering via referral link!
                from apps.core.services import SystemSettingService
                if not SystemSettingService.get_bool('REFERRAL_ENABLED', True):
                    referral_info['status'] = 'DISABLED'
                    referral_info['message'] = 'نظام الإحالات معطل حالياً من إدارة المتجر.'
                else:
                    referrer = TelegramProfile.objects.filter(telegram_id=referrer_id, is_banned=False).first()
                    if not referrer:
                        referral_info['status'] = 'INVALID_REFERRER'
                        referral_info['message'] = 'المستخدم صاحب رابط الإحالة غير موجود أو محظور.'
                    else:
                        profile.referred_by = referrer
                        updated = True
                        ref_name = referrer.full_name or referrer.username or str(referrer.telegram_id)
                        referral_info['status'] = 'LINKED'
                        referral_info['referrer_name'] = ref_name
                        referral_info['referrer_id'] = referrer.telegram_id
                        referral_info['message'] = f'تم الانضمام عبر رابط إحالة الصديق: {ref_name}'

                        # Trigger immediate notification to the referrer!
                        ReferralService.notify_referrer_of_new_entry(referrer, profile)

        # Update user metadata if changed
        if username and profile.username != username:
            profile.username = username
            updated = True
        if first_name and profile.first_name != first_name:
            profile.first_name = first_name
            updated = True
        if last_name and profile.last_name != last_name:
            profile.last_name = last_name
            updated = True
        
        # Check if this user is the configured super admin
        super_admin_id = getattr(settings, 'SUPER_ADMIN_TELEGRAM_ID', 0)
        if super_admin_id and telegram_id == super_admin_id:
            if not profile.is_admin:
                profile.is_admin = True
                updated = True
            if created or not hasattr(profile, 'admin_details'):
                admin_prof, _ = AdminProfile.objects.get_or_create(
                    profile=profile,
                    defaults={'is_super_admin': True, 'is_active': True}
                )
                if not admin_prof.is_super_admin:
                    admin_prof.is_super_admin = True
                    admin_prof.save(update_fields=['is_super_admin'])

        if updated:
            profile.save()

        return profile, created, referral_info

    @staticmethod
    def set_preferred_currency(telegram_id: int, currency: str) -> Optional[TelegramProfile]:
        """Switch preferred display currency for user (YER or USD)."""
        if currency not in ('YER', 'USD'):
            return None
        profile = TelegramProfile.objects.filter(telegram_id=telegram_id).first()
        if profile:
            profile.preferred_currency = currency
            profile.save(update_fields=['preferred_currency', 'updated_at'])
        return profile


class ReferralService:
    """Service to handle referral bonus awards and statistics."""

    @classmethod
    def notify_referrer_of_new_entry(cls, referrer: TelegramProfile, new_user: TelegramProfile):
        """
        Immediately notify referrer when a new member joins via their referral link.
        Informs them that bonus will be credited once subscription/conditions are verified.
        """
        from decimal import Decimal
        from apps.core.services import SystemSettingService
        from apps.telegram_bot.common.bot_instances import get_customer_bot
        import asyncio
        import html
        import logging

        logger = logging.getLogger(__name__)

        bonus_amount = SystemSettingService.get_decimal('REFERRAL_BONUS_YER', Decimal('50.00'))
        raw_name = new_user.full_name or new_user.username or "عضو جديد"
        u_name = html.escape(raw_name)

        text = (
            f"👤 <b>انضمام عضو جديد عبر رابط إحالتك!</b> 🤝\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"انضم <b>{u_name}</b> إلى البوت عبر رابط الدعوة الخاص بك! 🔗\n\n"
            f"⏳ <i>ملاحظة: سيتم إيداع مكافأة الإحالة (<b>+{bonus_amount:,.0f} YER</b>) في محفظتك تلقائياً بمجرد إكماله الشروط والاشتراك في القنوات الإجبارية.</i>\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

        bot = get_customer_bot()
        if not bot:
            logger.warning("Customer bot instance not available to send referral join notification.")
            return

        async def _send():
            try:
                await bot.send_message(chat_id=referrer.telegram_id, text=text, parse_mode='HTML')
            except Exception as e:
                logger.warning(f"Could not deliver referral join notification to referrer {referrer.telegram_id}: {e}")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_send())
        except RuntimeError:
            try:
                asyncio.run(_send())
            except Exception as exc:
                logger.warning(f"Failed to run asyncio task for referral notification: {exc}")

    @classmethod
    def award_referral_bonus_if_eligible(cls, user: TelegramProfile) -> Tuple[bool, str]:
        """
        Awards fixed referral bonus to the referrer's ledger once the new user qualifies
        (e.g., completes channel subscription or registers).
        """
        from decimal import Decimal
        from django.db import transaction
        from apps.core.services import SystemSettingService
        from apps.wallet.services import WalletService

        if not user.referred_by_id:
            return False, "لا يوجد مستخدم داعٍ."

        if not SystemSettingService.get_bool('REFERRAL_ENABLED', True):
            return False, "نظام الإحالات معطل حالياً."

        bonus_amount = SystemSettingService.get_decimal('REFERRAL_BONUS_YER', Decimal('50.00'))
        if bonus_amount <= 0:
            return False, "مبلغ مكافأة الإحالة 0."

        with transaction.atomic():
            locked_user = TelegramProfile.objects.select_for_update().get(id=user.id)
            if locked_user.referral_bonus_paid:
                return False, "تم صرف مكافأة الإحالة مسبقاً."

            referrer = locked_user.referred_by
            if not referrer:
                return False, "المستخدم الداعي غير موجود."

            referrer_wallet = WalletService.get_or_create_wallet(referrer)
            idempotency_key = f"ref-bonus-{locked_user.id}"

            WalletService.deposit(
                wallet=referrer_wallet,
                amount=bonus_amount,
                reference_id=f"REF-{locked_user.telegram_id}",
                description=f"مكافأة دعوة صديق جديد ({locked_user.full_name})",
                idempotency_key=idempotency_key
            )

            locked_user.referral_bonus_paid = True
            locked_user.save(update_fields=['referral_bonus_paid', 'updated_at'])

        # Notify referrer via customer bot
        try:
            from apps.telegram_bot.common.bot_instances import get_customer_bot
            import asyncio
            bot = get_customer_bot()
            if bot:
                text = (
                    f"🎉 <b>مكافأة إحالة جديدة!</b> 🎁\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"انضم صديقك <b>{locked_user.full_name}</b> إلى المتجر عبر رابط الدعوة الخاص بك!\n"
                    f"💰 <b>تمت إضافة مكافأة:</b> <code>+{bonus_amount:,.0f} YER</code> إلى محفظتك بنجاح ✅\n"
                    f"💰 <b>رصيدك الجديد:</b> <code>{referrer_wallet.balance_yer:,.0f} YER</code>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"شارك رابطك مع المزيد من أصدقائك واكسب المزيد من الأرباح!"
                )
                async def _send():
                    try:
                        await bot.send_message(chat_id=referrer.telegram_id, text=text, parse_mode='HTML')
                    except Exception:
                        pass
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_send())
                except RuntimeError:
                    asyncio.run(_send())
        except Exception:
            pass

        return True, f"تمت إضافة {bonus_amount:,.0f} YER لحساب الداعي بنجاح."

    @classmethod
    def get_referral_stats(cls, user: TelegramProfile) -> dict:
        """Fetch count of successful referrals and total bonus earned."""
        from django.db.models import Count
        from apps.wallet.models import WalletTransaction
        total_invited = TelegramProfile.objects.filter(referred_by=user).count()
        bonus_transactions = WalletTransaction.objects.filter(
            wallet__profile=user,
            reference_id__startswith="REF-"
        )
        total_earned = sum(t.amount for t in bonus_transactions)
        return {
            'total_invited': total_invited,
            'total_earned_yer': total_earned
        }



class AdminAuthService:
    """RBAC validation service for administrative operations."""

    @staticmethod
    def is_admin(telegram_id: int) -> bool:
        """Check if telegram ID belongs to an active administrator."""
        super_admin_id = getattr(settings, 'SUPER_ADMIN_TELEGRAM_ID', 0)
        if super_admin_id and telegram_id == super_admin_id:
            return True
        return AdminProfile.objects.filter(profile__telegram_id=telegram_id, is_active=True).exists()

    @staticmethod
    def has_permission(telegram_id: int, permission_codename: str) -> bool:
        """Check if admin holds the given permission."""
        super_admin_id = getattr(settings, 'SUPER_ADMIN_TELEGRAM_ID', 0)
        if super_admin_id and telegram_id == super_admin_id:
            return True

        admin_profile = AdminProfile.objects.filter(
            profile__telegram_id=telegram_id, 
            is_active=True
        ).first()

        if not admin_profile:
            return False

        return admin_profile.has_permission(permission_codename)

    @staticmethod
    def required_permission(callback_data: str = '', message_text: str = '') -> Optional[str]:
        """Return the RBAC permission required by an admin-bot action.

        This is deliberately centralized so a forged callback cannot bypass
        the permission checks duplicated in individual handlers.
        """
        value = callback_data or message_text or ''
        rules = (
            (('adm_pay', 'adm_deposit'), 'MANAGE_PAYMENTS'),
            (('adm_prod', 'adm_cat'), 'MANAGE_PRODUCTS'),
            (('adm_stock', 'adm_add_stock'), 'MANAGE_INVENTORY'),
            (('adm_ord', 'adm_orders'), 'MANAGE_ORDERS'),
            (('adm_user', 'adm_wallet', 'adm_customer'), 'MANAGE_USERS'),
            (('adm_service', 'adm_quote'), 'MANAGE_SERVICES'),
            (('adm_prov', 'adm_map_api'), 'MANAGE_PROVIDERS'),
            (('adm_setting', 'adm_exchange', 'adm_channel', 'adm_backup'), 'MANAGE_SETTINGS'),
            (('adm_broadcast',), 'MANAGE_USERS'),
        )
        for prefixes, permission in rules:
            if any(value.startswith(prefix) or prefix in value for prefix in prefixes):
                return permission
        return None
