from decimal import Decimal

from django.test import TestCase

from apps.payments.models import PaymentMethod
from apps.payments.services import PaymentService
from apps.users.models import TelegramProfile


class PaymentReceiptTests(TestCase):
    def setUp(self):
        self.user = TelegramProfile.objects.create(telegram_id=987654321)
        self.method = PaymentMethod.objects.create(
            name="Test Wallet",
            account_number="0000",
            instructions="Test instructions",
            min_deposit_yer=Decimal("1000"),
            max_deposit_yer=Decimal("500000"),
        )

    def test_receipt_uses_telegram_file_id(self):
        request = PaymentService.create_payment_request(
            user=self.user,
            payment_method=self.method,
            amount_yer=Decimal("10000"),
            tx_number="TX-12345",
            proof_image_file_id="AgACAgQAAxTelegramFileId",
        )

        self.assertEqual(request.proof_image_file_id, "AgACAgQAAxTelegramFileId")
        self.assertEqual(request.proof_image_url, "")
        self.assertEqual(request.status, "PENDING")
