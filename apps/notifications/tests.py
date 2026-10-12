from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from django.test import TransactionTestCase
from apps.notifications.models import RequiredChannel
from apps.notifications.services import ChannelSubscriptionService
from apps.core.services import SystemSettingService


class ChannelSubscriptionTests(TransactionTestCase):
    def setUp(self):
        SystemSettingService.clear_cache()
        ChannelSubscriptionService.clear_cache()

    def tearDown(self):
        SystemSettingService.clear_cache()
        ChannelSubscriptionService.clear_cache()

    def test_support_and_admin_channels_excluded_from_mandatory_membership(self):
        """Verify SUPPORT and ADMIN channels are never checked for customer membership."""
        # Create SUPPORT channel
        RequiredChannel.objects.create(
            channel_id="-100999111",
            channel_title="قناة الدعم",
            channel_type="SUPPORT",
            is_mandatory=True,
            is_active=True
        )
        # Create ADMIN channel
        RequiredChannel.objects.create(
            channel_id="-100999222",
            channel_title="قروب الأدمن",
            channel_type="ADMIN",
            is_mandatory=True,
            is_active=True
        )

        mock_bot = AsyncMock()
        import asyncio
        missing = asyncio.run(ChannelSubscriptionService.get_missing_channels(mock_bot, 12345))
        # Since only SUPPORT and ADMIN exist, missing must be empty
        self.assertEqual(missing, [])
        # Bot should not have even attempted to check membership for support/admin
        mock_bot.get_chat_member.assert_not_called()

    def test_official_and_custom_channels_enforced_when_mandatory(self):
        """Verify OFFICIAL and CUSTOM channels are strictly checked when user is not a member."""
        RequiredChannel.objects.create(
            channel_id="@official_test",
            channel_title="قناة البوت الرسمية",
            channel_type="OFFICIAL",
            is_mandatory=True,
            is_active=True
        )
        RequiredChannel.objects.create(
            channel_id="@custom_test",
            channel_title="قناة إضافية",
            channel_type="CUSTOM",
            is_mandatory=True,
            is_active=True
        )

        mock_bot = AsyncMock()
        # Mock user as NOT a member
        mock_bot.get_chat_member.return_value = SimpleNamespace(status="left")

        import asyncio
        missing = asyncio.run(ChannelSubscriptionService.get_missing_channels(mock_bot, 555666))
        self.assertEqual(len(missing), 2)
        missing_ids = [ch.channel_id for ch in missing]
        self.assertIn("@official_test", missing_ids)
        self.assertIn("@custom_test", missing_ids)

    def test_global_mandatory_subscription_disabled(self):
        """When mandatory subscription is globally disabled, no channels block access."""
        SystemSettingService.set_setting('MANDATORY_SUBSCRIPTION_ENABLED', 'false')
        RequiredChannel.objects.create(
            channel_id="@mandatory_test",
            channel_title="قناة إلزامية",
            channel_type="CUSTOM",
            is_mandatory=True,
            is_active=True
        )

        mock_bot = AsyncMock()
        import asyncio
        missing = asyncio.run(ChannelSubscriptionService.get_missing_channels(mock_bot, 999))
        self.assertEqual(missing, [])
        mock_bot.get_chat_member.assert_not_called()
