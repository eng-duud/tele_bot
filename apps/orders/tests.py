from unittest.mock import patch

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings

from apps.catalog.models import Category, Product
from apps.core.encryption import decrypt_data, encrypt_data
from apps.orders.services import OrderService
from apps.users.models import TelegramProfile
from apps.wallet.models import Wallet
from apps.wallet.services import WalletService


class OrderRoutingTests(TestCase):
    def setUp(self):
        self.profile = TelegramProfile.objects.create(telegram_id=123456789)
        self.wallet = Wallet.objects.create(profile=self.profile)
        WalletService.deposit(self.wallet, 1000, idempotency_key="test-deposit")
        self.category = Category.objects.create(name="Test", slug="test")

    def product(self, fulfillment_type):
        product = Product.objects.create(
            name=f"Product {fulfillment_type}",
            price=100,
            fulfillment_type=fulfillment_type,
            stock_type="API_CAPACITY" if fulfillment_type == "API" else "UNLIMITED",
        )
        product.categories.add(self.category)
        return product

    def test_api_purchase_is_queued_after_commit(self):
        product = self.product("API")
        with patch("apps.fulfillment.services.FulfillmentService.queue_fulfillment") as queue:
            with self.captureOnCommitCallbacks(execute=True):
                order, delivered = OrderService.process_purchase(self.profile, product)

        self.assertEqual(order.status, "PROCESSING")
        self.assertEqual(delivered, [])
        queue.assert_called_once_with(order)

    def test_unimplemented_file_delivery_does_not_charge_wallet(self):
        product = self.product("FILE")
        with self.assertRaisesMessage(ValueError, "غير مدعوم حالياً"):
            OrderService.process_purchase(self.profile, product)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_yer, 1000)


class EncryptionTests(TestCase):
    @override_settings(DATA_ENCRYPTION_KEY=Fernet.generate_key().decode())
    def test_configured_key_round_trips(self):
        self.assertEqual(decrypt_data(encrypt_data("secret-value")), "secret-value")

    @override_settings(DATA_ENCRYPTION_KEY="")
    @patch.dict("os.environ", {"DATA_ENCRYPTION_KEY": ""})
    def test_missing_key_fails_loudly(self):
        with self.assertRaisesMessage(Exception, "DATA_ENCRYPTION_KEY"):
            encrypt_data("secret-value")
