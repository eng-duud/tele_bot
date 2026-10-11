from decimal import Decimal
from django.test import TestCase
from apps.users.models import TelegramProfile
from apps.users.services import UserService, ReferralService
from apps.core.services import SystemSettingService


class ReferralLifecycleTestCase(TestCase):
    def setUp(self):
        SystemSettingService.clear_cache()
        SystemSettingService.set_setting("REFERRAL_ENABLED", "true")
        SystemSettingService.set_setting("REFERRAL_BONUS_YER", "50")

        # Existing referrer
        self.referrer = TelegramProfile.objects.create(
            telegram_id=5001,
            full_name="المستخدم الداعي",
            username="referrer_5001"
        )

        # Existing regular user (registered prior to this test)
        self.old_user = TelegramProfile.objects.create(
            telegram_id=5002,
            full_name="مستخدم قديم",
            username="old_user_5002"
        )

    def test_new_user_successful_referral_linking(self):
        """A brand new user entering with a valid referrer link is successfully bound."""
        new_profile, created, ref_info = UserService.get_or_create_user(
            telegram_id=7001,
            username="brand_new_user",
            first_name="أحمد",
            last_name="علي",
            referrer_id=self.referrer.telegram_id
        )

        self.assertTrue(created)
        self.assertEqual(ref_info['status'], 'LINKED')
        self.assertEqual(ref_info['referrer_id'], self.referrer.telegram_id)
        self.assertEqual(new_profile.referred_by, self.referrer)
        self.assertFalse(new_profile.referral_bonus_paid)

    def test_existing_user_cannot_accept_referral(self):
        """An existing user who previously used/started the bot cannot accept any referral."""
        profile, created, ref_info = UserService.get_or_create_user(
            telegram_id=self.old_user.telegram_id,
            username="old_user_5002",
            first_name="مستخدم",
            last_name="قديم",
            referrer_id=self.referrer.telegram_id
        )

        self.assertFalse(created)
        self.assertEqual(ref_info['status'], 'ALREADY_REGISTERED')
        self.old_user.refresh_from_db()
        self.assertIsNone(self.old_user.referred_by)

    def test_self_referral_is_rejected(self):
        """A user attempting to use their own referral code is rejected."""
        profile, created, ref_info = UserService.get_or_create_user(
            telegram_id=7002,
            username="self_ref_user",
            referrer_id=7002
        )

        self.assertTrue(created)
        self.assertEqual(ref_info['status'], 'SELF_REFERRAL')
        self.assertIsNone(profile.referred_by)

    def test_referral_to_nonexistent_user(self):
        """Entering with a non-existent referrer ID does not link."""
        profile, created, ref_info = UserService.get_or_create_user(
            telegram_id=7003,
            username="no_referrer_user",
            referrer_id=999999999
        )

        self.assertTrue(created)
        self.assertEqual(ref_info['status'], 'INVALID_REFERRER')
        self.assertIsNone(profile.referred_by)

    def test_immutable_referrer_binding(self):
        """A user already referred by one person cannot be changed by entering another referral link."""
        # 1. First signup with referrer A
        profile, created, ref_info1 = UserService.get_or_create_user(
            telegram_id=7004,
            username="referred_once",
            referrer_id=self.referrer.telegram_id
        )
        self.assertEqual(ref_info1['status'], 'LINKED')
        self.assertEqual(profile.referred_by, self.referrer)

        # 2. Another referrer B
        referrer_b = TelegramProfile.objects.create(
            telegram_id=5003,
            full_name="داعي آخر",
            username="referrer_b"
        )

        # 3. User tries to use referrer B's link
        profile2, created2, ref_info2 = UserService.get_or_create_user(
            telegram_id=7004,
            username="referred_once",
            referrer_id=referrer_b.telegram_id
        )
        self.assertFalse(created2)
        self.assertEqual(ref_info2['status'], 'ALREADY_REGISTERED')
        profile2.refresh_from_db()
        # Referrer is still the original referrer A
        self.assertEqual(profile2.referred_by, self.referrer)
