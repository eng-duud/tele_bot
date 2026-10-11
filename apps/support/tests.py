from django.test import TestCase
from apps.users.models import TelegramProfile
from apps.support.models import SupportTicket, TicketMessage
from apps.support.services import SupportService


class SupportServiceTestCase(TestCase):
    def setUp(self):
        self.customer = TelegramProfile.objects.create(
            telegram_id=111222333,
            full_name="العميل التجريبي",
            username="test_customer"
        )
        self.admin = TelegramProfile.objects.create(
            telegram_id=999888777,
            full_name="المشرف التجريبي",
            username="test_admin"
        )

    def test_create_ticket(self):
        ticket, msg = SupportService.create_ticket(
            user=self.customer,
            text="عندي مشكلة في شحن الرصيد برقم العملية 12345"
        )
        self.assertIsNotNone(ticket.id)
        self.assertTrue(ticket.ticket_number.startswith("TK-"))
        self.assertEqual(ticket.status, "OPEN")
        self.assertEqual(msg.ticket, ticket)
        self.assertEqual(msg.sender, self.customer)
        self.assertFalse(msg.is_from_admin)
        self.assertIn("مشكلة", msg.text)

    def test_reply_to_ticket(self):
        ticket, _ = SupportService.create_ticket(
            user=self.customer,
            text="استفسار بخصوص خدمة نت"
        )
        success, resp_msg, updated_ticket = SupportService.reply_to_ticket(
            ticket_id=str(ticket.id),
            admin_profile=self.admin,
            reply_text="أهلاً بك تم التحقق وسيتم الشحن الآن"
        )
        self.assertTrue(success)
        self.assertEqual(updated_ticket.status, "ANSWERED")
        self.assertEqual(updated_ticket.last_answered_by, self.admin)

        # Check messages in ticket
        msgs = TicketMessage.objects.filter(ticket=ticket)
        self.assertEqual(msgs.count(), 2)
        admin_msg = msgs.filter(is_from_admin=True).first()
        self.assertIsNotNone(admin_msg)
        self.assertEqual(admin_msg.sender, self.admin)

    def test_close_ticket(self):
        ticket, _ = SupportService.create_ticket(
            user=self.customer,
            text="يرجى إغلاق طلبي"
        )
        success, resp_msg, closed_ticket = SupportService.close_ticket(
            ticket_id=str(ticket.id),
            admin_profile=self.admin
        )
        self.assertTrue(success)
        self.assertEqual(closed_ticket.status, "CLOSED")

        # Attempting to reply to closed ticket should fail
        fail_success, fail_msg, _ = SupportService.reply_to_ticket(
            ticket_id=str(ticket.id),
            admin_profile=self.admin,
            reply_text="محاولة رد بعد الإغلاق"
        )
        self.assertFalse(fail_success)
