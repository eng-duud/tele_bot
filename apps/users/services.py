from typing import Tuple, Optional
from django.conf import settings
from apps.users.models import TelegramProfile, AdminProfile, AdminPermission, AdminRole

class UserService:
    """Service to handle customer onboarding and profile management."""

    @staticmethod
    def get_or_create_user(telegram_id: int, username: str = "", first_name: str = "", last_name: str = "") -> Tuple[TelegramProfile, bool]:
        """Fetch or create a user by their Telegram numeric ID."""
        profile, created = TelegramProfile.objects.get_or_create(
            telegram_id=telegram_id,
            defaults={
                'username': username or "",
                'first_name': first_name or "",
                'last_name': last_name or "",
                'preferred_currency': getattr(settings, 'BASE_CURRENCY', 'YER'),
            }
        )
        # Update user metadata if changed
        updated = False
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

        return profile, created

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
