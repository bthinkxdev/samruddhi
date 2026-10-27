"""Tests for the WhatsApp integration — the Gupshup API is always mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.services import register_customer_email
from cart.models import Cart, CartItem
from catalog.models import Collection, Product
from checkout.services import create_checkout_session, place_order
from core.models import Currency
from whatsapp.client import GupshupClient
from whatsapp.exceptions import InvalidPhoneNumber, WhatsAppAPIError, WhatsAppRetryableError
from whatsapp.models import MessageDirection, MessageStatus, WhatsAppMessage, WhatsAppTemplate
from whatsapp.services import (
    deliver_message,
    normalize_phone,
    process_webhook_payload,
    queue_order_event,
)

WA_SETTINGS = dict(
    WHATSAPP_ENABLED=True,
    GUPSHUP_API_KEY="test-key",
    GUPSHUP_SOURCE_NUMBER="917834811114",
    GUPSHUP_APP_NAME="SammruddhiApp",
    GUPSHUP_WEBHOOK_SECRET="webhook-secret",
)


def _response(status_code: int, data: dict) -> MagicMock:
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = data
    return resp


class PhoneNormalisationTests(TestCase):
    def test_formats(self) -> None:
        self.assertEqual(normalize_phone("98765 43210"), "919876543210")
        self.assertEqual(normalize_phone("+91-98765-43210"), "919876543210")
        self.assertEqual(normalize_phone("098765 43210"), "919876543210")
        self.assertEqual(normalize_phone("919876543210"), "919876543210")
        self.assertEqual(normalize_phone("0044 7700 900123"), "447700900123")

    def test_invalid(self) -> None:
        for bad in ("", "12345", "abc"):
            with self.assertRaises(InvalidPhoneNumber):
                normalize_phone(bad)


class ClientTests(TestCase):
    def _client(self, response: MagicMock) -> GupshupClient:
        session = MagicMock()
        session.post.return_value = response
        return GupshupClient(
            api_key="k", source="917834811114", app_name="SammruddhiApp", session=session
        )

    def test_template_payload(self) -> None:
        client = self._client(_response(200, {"status": "submitted", "messageId": "x"}))
        payload = client.build_template_payload(
            to="919876543210",
            template_id="c6aecef6-bcb0-4fb1-8100-28c094e3bc6b",
            body_params=["Argue", "SAM-1"],
            button_url_param="AWB1",
        )
        self.assertEqual(payload["source"], "917834811114")
        self.assertEqual(payload["destination"], "919876543210")
        self.assertEqual(payload["src.name"], "SammruddhiApp")
        template = json.loads(payload["template"])
        self.assertEqual(template["id"], "c6aecef6-bcb0-4fb1-8100-28c094e3bc6b")
        self.assertEqual(template["params"], ["Argue", "SAM-1", "AWB1"])

    def test_text_payload_uses_msg_endpoint(self) -> None:
        client = self._client(_response(200, {"status": "submitted", "messageId": "y"}))
        payload = client.build_text_payload(to="919876543210", text="hi")
        self.assertNotIn("template", payload)
        self.assertEqual(json.loads(payload["message"]), {"type": "text", "text": "hi"})

    def test_success_returns_json(self) -> None:
        client = self._client(_response(200, {"status": "submitted", "messageId": "gs-1"}))
        self.assertEqual(client.send_text(to="919876543210", text="hi")["messageId"], "gs-1")

    def test_permanent_error(self) -> None:
        client = self._client(_response(400, {"status": "error", "message": "Invalid Destination"}))
        with self.assertRaises(WhatsAppAPIError) as ctx:
            client.send_text(to="919876543210", text="hi")
        self.assertNotIsInstance(ctx.exception, WhatsAppRetryableError)
        self.assertEqual(str(ctx.exception), "Invalid Destination")

    def test_rate_limit_is_retryable(self) -> None:
        client = self._client(_response(429, {"status": "error", "message": "Too many requests"}))
        with self.assertRaises(WhatsAppRetryableError):
            client.send_text(to="919876543210", text="hi")

    def test_server_error_is_retryable(self) -> None:
        client = self._client(_response(500, {"status": "error", "message": "Internal"}))
        with self.assertRaises(WhatsAppRetryableError):
            client.send_text(to="919876543210", text="hi")


class OrderFixtureMixin:
    def make_order(self):
        currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="wa-test@example.com", password="testpass12345", name="Argue Test"
        )
        self.profile.phone = "98765 43210"
        self.profile.notify_via_whatsapp = True
        self.profile.save()
        collection = Collection.objects.create(name="WA Collection", slug="wa-collection")
        product = Product.objects.create(
            name="Test Yarn",
            slug="wa-test-yarn",
            sku="SKU-WA-1",
            base_price="500.00",
            mrp="500.00",
            purchase_price="300.00",
            stock_quantity=100,
        )
        product.collections.add(collection)
        cart = Cart.objects.create(customer_profile=self.profile, currency=currency)
        CartItem.objects.create(
            cart=cart, product=product, quantity=1, unit_price_at_add=product.base_price
        )
        session = create_checkout_session(cart=cart, customer_profile=self.profile)
        return place_order(
            checkout_session_id=session.pk,
            idempotency_key="wa-test-order-1",
            gateway_key="razorpay_upi",
            customer_profile=self.profile,
        )


@override_settings(**WA_SETTINGS)
class QueueAndDeliverTests(OrderFixtureMixin, TestCase):
    def setUp(self) -> None:
        self.order = self.make_order()
        WhatsAppTemplate.objects.create(
            event="confirmed",
            template_id="c6aecef6-bcb0-4fb1-8100-28c094e3bc6b",
            body_variables=["customer_name", "order_number", "order_items"],
        )

    @override_settings(WHATSAPP_ENABLED=False)
    def test_disabled_sends_nothing(self) -> None:
        self.assertIsNone(queue_order_event(order=self.order, event="confirmed"))
        self.assertFalse(WhatsAppMessage.objects.exists())

    def test_no_template_sends_nothing(self) -> None:
        self.assertIsNone(queue_order_event(order=self.order, event="delivered"))

    @patch("whatsapp.tasks.send_message_task.delay")
    def test_queue_is_idempotent_and_enqueues_on_commit(self, mock_delay) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            message = queue_order_event(order=self.order, event="confirmed")
            again = queue_order_event(order=self.order, event="confirmed")
        self.assertEqual(message.pk, again.pk)
        self.assertEqual(WhatsAppMessage.objects.count(), 1)
        mock_delay.assert_called_once_with(message_id=message.pk)
        self.assertEqual(message.phone, "919876543210")
        self.assertEqual(message.body_params[0], "Argue")
        self.assertEqual(message.body_params[1], self.order.order_number)
        self.assertEqual(message.body_params[2], "Test Yarn")

    def _queued(self) -> WhatsAppMessage:
        with patch("whatsapp.tasks.send_message_task.delay"):
            return queue_order_event(order=self.order, event="confirmed")

    def test_deliver_success(self) -> None:
        message = self._queued()
        client = MagicMock()
        client.build_template_payload.return_value = {"template": "{}"}
        client.send_payload.return_value = {"status": "submitted", "messageId": "gs-ABC"}
        deliver_message(message.pk, client=client)
        message.refresh_from_db()
        self.assertEqual(message.status, MessageStatus.SENT)
        self.assertEqual(message.provider_message_id, "gs-ABC")
        self.assertEqual(message.attempts, 1)
        # A second run (duplicate task) must not resend.
        deliver_message(message.pk, client=client)
        client.send_payload.assert_called_once()

    def test_deliver_permanent_failure(self) -> None:
        message = self._queued()
        client = MagicMock()
        client.build_template_payload.return_value = {"template": "{}"}
        client.send_payload.side_effect = WhatsAppAPIError("Invalid Destination", status_code=400)
        deliver_message(message.pk, client=client)
        message.refresh_from_db()
        self.assertEqual(message.status, MessageStatus.FAILED)
        self.assertEqual(message.error_message, "Invalid Destination")

    def test_deliver_retryable_keeps_queued(self) -> None:
        message = self._queued()
        client = MagicMock()
        client.build_template_payload.return_value = {"template": "{}"}
        client.send_payload.side_effect = WhatsAppRetryableError("timeout")
        with self.assertRaises(WhatsAppRetryableError):
            deliver_message(message.pk, client=client)
        message.refresh_from_db()
        self.assertEqual(message.status, MessageStatus.QUEUED)
        self.assertEqual(message.attempts, 1)

    @patch("whatsapp.tasks.send_message_task.delay")
    def test_notifications_task_queues_whatsapp(self, mock_delay) -> None:
        from notifications.tasks import dispatch_order_status_notification

        dispatch_order_status_notification(
            order_id=self.order.pk, old_status="placed_cod", new_status="confirmed"
        )
        self.assertTrue(
            WhatsAppMessage.objects.filter(order=self.order, event="confirmed").exists()
        )


@override_settings(**WA_SETTINGS)
class WebhookTests(OrderFixtureMixin, TestCase):
    def setUp(self) -> None:
        self.url = reverse("whatsapp:webhook")
        self.message = WhatsAppMessage.objects.create(
            phone="919876543210",
            template_id="t",
            status=MessageStatus.SENT,
            provider_message_id="gs-X",
        )

    def _post(self, payload: dict, token: str = "webhook-secret"):
        body = json.dumps(payload).encode()
        return self.client.post(
            f"{self.url}?token={token}", data=body, content_type="application/json"
        )

    @staticmethod
    def _status_event(*, event_type: str, gs_id: str = "gs-X", ts: int = 1700000000000, **extra):
        return {
            "app": "DemoApp",
            "timestamp": ts,
            "version": 2,
            "type": "message-event",
            "payload": {
                "id": "gBEGkYaYVSEEAgnZxQ3JmKK6Wvg",
                "gsId": gs_id,
                "type": event_type,
                "destination": "919876543210",
                "payload": extra,
            },
        }

    @staticmethod
    def _message_event(*, msg_id: str, source: str, text: str):
        return {
            "app": "DemoApp",
            "timestamp": 1700000000000,
            "version": 2,
            "type": "message",
            "payload": {
                "id": msg_id,
                "source": source,
                "type": "text",
                "payload": {"text": text},
                "sender": {
                    "phone": source,
                    "name": "Andy",
                    "country_code": "91",
                    "dial_code": source,
                },
            },
        }

    def test_missing_token_rejected(self) -> None:
        resp = self.client.post(
            self.url, data=json.dumps({}).encode(), content_type="application/json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_wrong_token_rejected(self) -> None:
        resp = self._post(self._status_event(event_type="delivered"), token="wrong")
        self.assertEqual(resp.status_code, 403)

    def test_status_progression_never_goes_backwards(self) -> None:
        for event_type, ts in (("read", 1700000200000), ("delivered", 1700000100000)):
            resp = self._post(self._status_event(event_type=event_type, ts=ts))
            self.assertEqual(resp.status_code, 200)
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, MessageStatus.READ)
        self.assertIsNotNone(self.message.delivered_at)
        self.assertIsNotNone(self.message.read_at)

    def test_failed_status(self) -> None:
        self._post(
            self._status_event(event_type="failed", code=470, reason="24 hour window expired")
        )
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, MessageStatus.FAILED)
        self.assertEqual(self.message.error_code, "470")
        self.assertEqual(self.message.error_message, "24 hour window expired")

    def test_enqueued_event_is_ignored(self) -> None:
        resp = self._post(self._status_event(event_type="enqueued"))
        self.assertEqual(resp.status_code, 200)
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, MessageStatus.SENT)

    def test_inbound_stop_opts_out(self) -> None:
        self.make_order()
        payload = self._message_event(msg_id="gBEGk.IN1", source="919876543210", text="STOP")
        process_webhook_payload(payload)
        process_webhook_payload(payload)  # redelivery
        self.assertEqual(
            WhatsAppMessage.objects.filter(direction=MessageDirection.INBOUND).count(), 1
        )
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.notify_via_whatsapp)
