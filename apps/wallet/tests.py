from decimal import Decimal
from django.test import TestCase
from apps.users.models import TelegramProfile
from apps.wallet.models import Wallet, WalletTransaction
from apps.core.services import SystemSettingService
from apps.users.services import ReferralService


class ReferralServiceTestCase(TestCase):
    def setUp(self):
        SystemSettingService.clear_cache()
        SystemSettingService.set_setting("REFERRAL_ENABLED", "true")
        SystemSettingService.set_setting("REFERRAL_BONUS_YER", "50")

        self.referrer = TelegramProfile.objects.create(
            telegram_id=1001,
            full_name="المستخدم الداعي",
            username="referrer_user"
        )
        self.referrer_wallet, _ = Wallet.objects.get_or_create(profile=self.referrer)

        self.referee = TelegramProfile.objects.create(
            telegram_id=1002,
            full_name="المستخدم المدعو",
            username="referee_user",
            referred_by=self.referrer,
            referral_bonus_paid=False
        )
        self.referee_wallet, _ = Wallet.objects.get_or_create(profile=self.referee)

    def test_award_referral_bonus_success(self):
        initial_balance = self.referrer_wallet.balance_yer

        awarded = ReferralService.award_referral_bonus_if_eligible(self.referee)
        self.assertTrue(awarded)

        self.referee.refresh_from_db()
        self.assertTrue(self.referee.referral_bonus_paid)

        self.referrer_wallet.refresh_from_db()
        self.assertEqual(self.referrer_wallet.balance_yer, initial_balance + Decimal("50.00"))

        # Verify transaction record
        tx = WalletTransaction.objects.filter(
            wallet=self.referrer_wallet,
            reference_id=f"REF-{self.referee.telegram_id}"
        ).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal("50.00"))

    def test_award_referral_bonus_idempotency(self):
        # First call
        ReferralService.award_referral_bonus_if_eligible(self.referee)
        self.referrer_wallet.refresh_from_db()
        bal_after_first = self.referrer_wallet.balance_yer

        # Second call should not double pay
        awarded_again, _ = ReferralService.award_referral_bonus_if_eligible(self.referee)
        self.assertFalse(awarded_again)

        self.referrer_wallet.refresh_from_db()
        self.assertEqual(self.referrer_wallet.balance_yer, bal_after_first)

    def test_award_referral_bonus_disabled_in_settings(self):
        SystemSettingService.set_setting("REFERRAL_ENABLED", "false")
        awarded, _ = ReferralService.award_referral_bonus_if_eligible(self.referee)
        self.assertFalse(awarded)

        self.referee.refresh_from_db()
        self.assertFalse(self.referee.referral_bonus_paid)
