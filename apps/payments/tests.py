from decimal import Decimal

from django.test import TestCase

from apps.payments.models import PaymentMethod, PaymentRequest
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

    def test_pending_request_blocks_a_second_request(self):
        PaymentService.create_payment_request(
            user=self.user,
            payment_method=self.method,
            amount_yer=Decimal("10000"),
            tx_number="TX-PENDING",
            proof_image_file_id="telegram-file-1",
        )

        reason = PaymentService.get_top_up_block_reason(self.user)
        self.assertIn("قيد المراجعة", reason)

    def test_three_recent_requests_trigger_rate_limit(self):
        for index in range(3):
            request = PaymentService.create_payment_request(
                user=self.user,
                payment_method=self.method,
                amount_yer=Decimal("10000"),
                tx_number=f"TX-{index}",
                proof_image_file_id=f"telegram-file-{index}",
            )
            request.status = "APPROVED"
            request.save(update_fields=["status"])
        reason = PaymentService.get_top_up_block_reason(self.user)
        self.assertIn("3 طلبات خلال 10 دقائق", reason)
