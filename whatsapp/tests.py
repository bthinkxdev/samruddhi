"""Tests for the WhatsApp integration — Meta API is always mocked."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.services import register_customer_email
from cart.models import Cart, CartItem
from catalog.models import Collection, Product
from checkout.services import create_checkout_session, place_order
from core.models import Currency
from whatsapp.client import WhatsAppClient
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
    WHATSAPP_ACCESS_TOKEN="test-token",
    WHATSAPP_PHONE_NUMBER_ID="123456",
    WHATSAPP_APP_SECRET="app-secret",
    WHATSAPP_WEBHOOK_VERIFY_TOKEN="verify-me",
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
    def _client(self, response: MagicMock) -> WhatsAppClient:
        session = MagicMock()
        session.post.return_value = response
        return WhatsAppClient(access_token="t", phone_number_id="1", session=session)

    def test_template_payload(self) -> None:
        payload = WhatsAppClient.build_template_payload(
            to="919876543210",
            template_name="order_confirmed",
            language_code="en",
            body_params=["Argue", "SAM-1"],
            button_url_param="AWB1",
        )
        self.assertEqual(payload["template"]["name"], "order_confirmed")
        body, button = payload["template"]["components"]
        self.assertEqual([p["text"] for p in body["parameters"]], ["Argue", "SAM-1"])
        self.assertEqual(button["parameters"][0]["text"], "AWB1")

    def test_success_returns_json(self) -> None:
        client = self._client(_response(200, {"messages": [{"id": "wamid.1"}]}))
        self.assertEqual(client.send_text(to="91", text="hi")["messages"][0]["id"], "wamid.1")

    def test_permanent_error(self) -> None:
        client = self._client(
            _response(400, {"error": {"code": 132001, "message": "Template missing"}})
        )
        with self.assertRaises(WhatsAppAPIError) as ctx:
            client.send_text(to="91", text="hi")
        self.assertNotIsInstance(ctx.exception, WhatsAppRetryableError)
        self.assertEqual(ctx.exception.code, 132001)

    def test_rate_limit_is_retryable(self) -> None:
        client = self._client(_response(400, {"error": {"code": 130429, "message": "Rate limit"}}))
        with self.assertRaises(WhatsAppRetryableError):
            client.send_text(to="91", text="hi")


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
        patcher = patch("delhivery.tasks.create_shipment_for_order.delay")
        patcher.start()
        self.addCleanup(patcher.stop)
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
            template_name="order_confirmed",
            language_code="en",
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
        client.send_payload.return_value = {"messages": [{"id": "wamid.ABC"}]}
        deliver_message(message.pk, client=client)
        message.refresh_from_db()
        self.assertEqual(message.status, MessageStatus.SENT)
        self.assertEqual(message.wamid, "wamid.ABC")
        self.assertEqual(message.attempts, 1)
        # A second run (duplicate task) must not resend.
        deliver_message(message.pk, client=client)
        client.send_payload.assert_called_once()

    def test_deliver_permanent_failure(self) -> None:
        message = self._queued()
        client = MagicMock()
        client.send_payload.side_effect = WhatsAppAPIError("bad template", code=132001)
        deliver_message(message.pk, client=client)
        message.refresh_from_db()
        self.assertEqual(message.status, MessageStatus.FAILED)
        self.assertEqual(message.error_code, "132001")

    def test_deliver_retryable_keeps_queued(self) -> None:
        message = self._queued()
        client = MagicMock()
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
            phone="919876543210", template_name="t", status=MessageStatus.SENT, wamid="wamid.X"
        )

    def _post(self, payload: dict, secret: str = "app-secret"):
        body = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            self.url, data=body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig
        )

    @staticmethod
    def _envelope(value: dict) -> dict:
        return {
            "object": "whatsapp_business_account",
            "entry": [{"id": "1", "changes": [{"field": "messages", "value": value}]}],
        }

    def test_verify_handshake(self) -> None:
        ok = self.client.get(
            self.url,
            {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.content, b"42")
        bad = self.client.get(
            self.url, {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"}
        )
        self.assertEqual(bad.status_code, 403)

    def test_bad_signature_rejected(self) -> None:
        resp = self._post(self._envelope({"statuses": []}), secret="wrong")
        self.assertEqual(resp.status_code, 403)

    def test_status_progression_never_goes_backwards(self) -> None:
        for status, ts in (("read", "1700000200"), ("delivered", "1700000100")):
            resp = self._post(
                self._envelope({"statuses": [{"id": "wamid.X", "status": status, "timestamp": ts}]})
            )
            self.assertEqual(resp.status_code, 200)
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, MessageStatus.READ)
        self.assertIsNotNone(self.message.delivered_at)
        self.assertIsNotNone(self.message.read_at)

    def test_failed_status(self) -> None:
        self._post(
            self._envelope(
                {
                    "statuses": [
                        {
                            "id": "wamid.X",
                            "status": "failed",
                            "timestamp": "1700000000",
                            "errors": [{"code": 131026, "title": "Message undeliverable"}],
                        }
                    ]
                }
            )
        )
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, MessageStatus.FAILED)
        self.assertEqual(self.message.error_code, "131026")

    def test_inbound_stop_opts_out(self) -> None:
        self.make_order()
        msg = {"from": "919876543210", "id": "wamid.IN1", "type": "text", "text": {"body": "STOP"}}
        process_webhook_payload(self._envelope({"messages": [msg]}))
        process_webhook_payload(self._envelope({"messages": [msg]}))  # redelivery
        self.assertEqual(
            WhatsAppMessage.objects.filter(direction=MessageDirection.INBOUND).count(), 1
        )
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.notify_via_whatsapp)
