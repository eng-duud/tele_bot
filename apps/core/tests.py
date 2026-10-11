from decimal import Decimal
from django.test import TestCase
from apps.core.models import SystemSetting
from apps.core.services import SystemSettingService


class SystemSettingServiceTestCase(TestCase):
    def setUp(self):
        SystemSettingService.clear_cache()

    def test_get_setting_default(self):
        val = SystemSettingService.get_setting("UNKNOWN_KEY", "default_val")
        self.assertEqual(val, "default_val")

    def test_set_and_get_setting(self):
        SystemSettingService.set_setting("STORE_NAME", "سوق اليمن الرقمي", "اسم المتجر")
        val = SystemSettingService.get_setting("STORE_NAME")
        self.assertEqual(val, "سوق اليمن الرقمي")

    def test_get_bool(self):
        SystemSettingService.set_setting("REFERRAL_ENABLED", "true")
        self.assertTrue(SystemSettingService.get_bool("REFERRAL_ENABLED"))

        SystemSettingService.set_setting("REFERRAL_ENABLED", "false")
        self.assertFalse(SystemSettingService.get_bool("REFERRAL_ENABLED"))

    def test_get_decimal(self):
        SystemSettingService.set_setting("REFERRAL_BONUS_YER", "75.50")
        dec = SystemSettingService.get_decimal("REFERRAL_BONUS_YER")
        self.assertEqual(dec, Decimal("75.50"))

    def test_get_int(self):
        SystemSettingService.set_setting("MAX_LIMIT", "100")
        num = SystemSettingService.get_int("MAX_LIMIT")
        self.assertEqual(num, 100)
