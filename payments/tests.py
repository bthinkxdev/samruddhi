"""Tests for the real Razorpay webhook and idempotent payment confirmation.

Object construction mirrors core.management.commands.audit_page_queries: build a
Currency, Cart/CartItem, checkout session, and a real Order via
checkout.services.place_order — then attach a PaymentTransaction directly (with a
known external_intent_id/amount/currency) rather than going through the real
Razorpay HTTP adapter, so these tests never make network calls.

Note on concurrency: the project's DATABASE_URL falls back to sqlite when unset,
and Django's sqlite backend silently no-ops select_for_update() (no real row
lock). The "idempotent under concurrent delivery" tests below therefore prove
sequential-call idempotency only — true concurrent-thread locking behavior only
manifests under Postgres, which these tests do not exercise.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.services import register_customer_email
from cart.models import Cart, CartItem
from catalog.models import Collection, Product
from checkout.services import create_checkout_session, place_order
from core.models import Currency
from orders.models import OrderStatus, OrderStatusHistory
from payments.adapters.concrete import RazorpayAdapter
from payments.models import (
    PaymentStatus,
    PaymentTransaction,
    RazorpayWebhookEvent,
    RazorpayWebhookEventStatus,
)
from payments.services import confirm_payment_success

WEBHOOK_SECRET = "test-razorpay-webhook-secret"


def _sign(payload: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _event(
    *,
    event_type: str = "payment.captured",
    razorpay_order_id: str,
    razorpay_payment_id: str,
    amount_paise: int,
    currency: str = "INR",
) -> dict:
    """Build a Razorpay webhook payload matching the real payload.payment.entity shape."""
    return {
        "entity": "event",
        "event": event_type,
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": razorpay_payment_id,
                    "order_id": razorpay_order_id,
                    "amount": amount_paise,
                    "currency": currency,
                    "status": "failed" if event_type == "payment.failed" else "captured",
                    "method": "upi",
                }
            }
        },
        "created_at": 1700000000,
    }


@override_settings(RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET)
class RazorpayWebhookTests(TestCase):
    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="webhook-test@example.com",
            password="testpass12345",
            name="Webhook Test",
        )
        collection = Collection.objects.create(name="Test Collection", slug="test-collection")
        self.product = Product.objects.create(
            name="Test Yarn",
            slug="test-yarn",
            sku="SKU-TEST-1",
            base_price="500.00",
            mrp="500.00",
            purchase_price="300.00",
            stock_quantity=100,
        )
        self.product.collections.add(collection)
        self.webhook_url = reverse("payments:razorpay-webhook")

        # These are real order-confirmation side effects (admin/plugin notifications) that
        # this test suite doesn't own — silence them so tests stay hermetic and fast.
        self._delhivery_patch = patch("delhivery.tasks.create_shipment_for_order.delay")
        self._delhivery_patch.start()
        self.addCleanup(self._delhivery_patch.stop)

    def _make_pending_order(self, order_number_suffix: str = "1"):
        cart = Cart.objects.create(customer_profile=self.profile, currency=self.currency)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=1,
            unit_price_at_add=self.product.base_price,
        )
        session = create_checkout_session(cart=cart, customer_profile=self.profile)
        order = place_order(
            checkout_session_id=session.pk,
            idempotency_key=f"webhook-test-order-{order_number_suffix}",
            gateway_key="razorpay_upi",
            customer_profile=self.profile,
        )
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        return order

    def _make_transaction(self, order, *, external_intent_id: str) -> PaymentTransaction:
        return PaymentTransaction.objects.create(
            order=order,
            gateway_key="razorpay_upi",
            amount=order.total_amount,
            currency=order.currency,
            status=PaymentStatus.PENDING,
            external_intent_id=external_intent_id,
        )

    def _post(self, event_data: dict, *, event_id: str = "evt_1", signature: str | None = None):
        body = json.dumps(event_data).encode("utf-8")
        sig = _sign(body) if signature is None else signature
        headers = {}
        if sig is not None:
            headers["HTTP_X_RAZORPAY_SIGNATURE"] = sig
        if event_id is not None:
            headers["HTTP_X_RAZORPAY_EVENT_ID"] = event_id
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.webhook_url, data=body, content_type="application/json", **headers
            )
        return response

    # ---- happy path -----------------------------------------------------

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_payment_captured_confirms_order_end_to_end(self, mock_delay):
        order = self._make_pending_order("captured")
        tx = self._make_transaction(order, external_intent_id="order_captured_1")
        amount_paise = int(order.total_amount * 100)

        response = self._post(
            _event(
                razorpay_order_id="order_captured_1",
                razorpay_payment_id="pay_captured_1",
                amount_paise=amount_paise,
                currency=order.currency.code,
            ),
            event_id="evt_captured_1",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        tx.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        self.assertEqual(tx.status, PaymentStatus.SUCCESS)
        self.assertEqual(tx.external_transaction_id, "pay_captured_1")
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)

        event = RazorpayWebhookEvent.objects.get(event_id="evt_captured_1")
        self.assertEqual(event.status, RazorpayWebhookEventStatus.PROCESSED)
        self.assertEqual(event.payment_transaction_id, tx.pk)

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_order_paid_confirms_order_end_to_end(self, mock_delay):
        order = self._make_pending_order("order-paid")
        self._make_transaction(order, external_intent_id="order_paid_1")
        amount_paise = int(order.total_amount * 100)

        response = self._post(
            _event(
                event_type="order.paid",
                razorpay_order_id="order_paid_1",
                razorpay_payment_id="pay_paid_1",
                amount_paise=amount_paise,
                currency=order.currency.code,
            ),
            event_id="evt_order_paid_1",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        mock_delay.assert_called_once_with(order_id=order.pk)

    # ---- security / parsing ---------------------------------------------

    def test_invalid_signature_rejected(self):
        order = self._make_pending_order("badsig")
        self._make_transaction(order, external_intent_id="order_badsig_1")
        response = self._post(
            _event(
                razorpay_order_id="order_badsig_1",
                razorpay_payment_id="pay_badsig_1",
                amount_paise=int(order.total_amount * 100),
            ),
            event_id="evt_badsig_1",
            signature="not-the-real-signature",
        )
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        self.assertFalse(RazorpayWebhookEvent.objects.filter(event_id="evt_badsig_1").exists())

    def test_missing_signature_rejected(self):
        response = self._post(
            _event(razorpay_order_id="order_x", razorpay_payment_id="pay_x", amount_paise=100),
            event_id="evt_nosig",
            signature="",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_event_id_rejected(self):
        response = self._post(
            _event(razorpay_order_id="order_x", razorpay_payment_id="pay_x", amount_paise=100),
            event_id="",
        )
        self.assertEqual(response.status_code, 400)

    def test_malformed_json_rejected(self):
        body = b"{not valid json"
        response = self.client.post(
            self.webhook_url,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=_sign(body),
            HTTP_X_RAZORPAY_EVENT_ID="evt_malformed",
        )
        self.assertEqual(response.status_code, 400)

    # ---- idempotency ------------------------------------------------------

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_duplicate_event_id_is_a_noop(self, mock_delay):
        order = self._make_pending_order("dup")
        self._make_transaction(order, external_intent_id="order_dup_1")
        event_data = _event(
            razorpay_order_id="order_dup_1",
            razorpay_payment_id="pay_dup_1",
            amount_paise=int(order.total_amount * 100),
        )

        first = self._post(event_data, event_id="evt_dup_1")
        second = self._post(event_data, event_id="evt_dup_1")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(json.loads(first.content)["duplicate"])
        self.assertTrue(json.loads(second.content)["duplicate"])
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)
        self.assertEqual(RazorpayWebhookEvent.objects.filter(event_id="evt_dup_1").count(), 1)

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_different_event_ids_same_payment_confirm_only_once(self, mock_delay):
        """Razorpay commonly fires both payment.captured and order.paid for one
        payment — two different event_ids. Only the PaymentTransaction-level
        guard in confirm_payment_success catches this, not event_id dedup."""
        order = self._make_pending_order("crosstype")
        self._make_transaction(order, external_intent_id="order_crosstype_1")
        amount_paise = int(order.total_amount * 100)

        self._post(
            _event(
                event_type="payment.captured",
                razorpay_order_id="order_crosstype_1",
                razorpay_payment_id="pay_crosstype_1",
                amount_paise=amount_paise,
            ),
            event_id="evt_crosstype_captured",
        )
        self._post(
            _event(
                event_type="order.paid",
                razorpay_order_id="order_crosstype_1",
                razorpay_payment_id="pay_crosstype_1",
                amount_paise=amount_paise,
            ),
            event_id="evt_crosstype_paid",
        )

        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)
        self.assertEqual(
            RazorpayWebhookEvent.objects.filter(
                event_id__in=["evt_crosstype_captured", "evt_crosstype_paid"],
                status=RazorpayWebhookEventStatus.PROCESSED,
            ).count(),
            2,
        )

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_conflicting_payment_id_is_not_overwritten_and_not_reconfirmed(self, mock_delay):
        """A later event referencing a *different* payment_id than the one that
        actually confirmed the order must not overwrite external_transaction_id
        and must not be silently treated as an ordinary processed event — it's
        recorded as PAYMENT_ID_MISMATCH so it surfaces for investigation."""
        order = self._make_pending_order("overwrite")
        tx = self._make_transaction(order, external_intent_id="order_overwrite_1")
        amount_paise = int(order.total_amount * 100)

        self._post(
            _event(
                razorpay_order_id="order_overwrite_1",
                razorpay_payment_id="pay_real_winner",
                amount_paise=amount_paise,
            ),
            event_id="evt_overwrite_first",
        )
        tx.refresh_from_db()
        self.assertEqual(tx.external_transaction_id, "pay_real_winner")

        self._post(
            _event(
                razorpay_order_id="order_overwrite_1",
                razorpay_payment_id="pay_stale_impostor",
                amount_paise=amount_paise,
            ),
            event_id="evt_overwrite_second",
        )

        tx.refresh_from_db()
        self.assertEqual(tx.external_transaction_id, "pay_real_winner")
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)
        second_event = RazorpayWebhookEvent.objects.get(event_id="evt_overwrite_second")
        self.assertEqual(second_event.status, RazorpayWebhookEventStatus.PAYMENT_ID_MISMATCH)

    def test_confirm_payment_success_called_twice_directly_is_idempotent(self):
        """Sequential proof of the transaction-level guard itself (see module
        docstring re: sqlite not exercising real row locking)."""
        order = self._make_pending_order("directcall")
        tx = self._make_transaction(order, external_intent_id="order_directcall_1")

        confirm_payment_success(payment_transaction=tx)
        confirm_payment_success(payment_transaction=tx)

        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_browser_callback_then_webhook_confirms_only_once(self, mock_delay):
        """confirm_payment_success(...) here stands in for razorpay_callback_view,
        which calls the exact same function — proving the two channels share
        one idempotent convergence point without needing a second HTTP round
        trip through the checkout app."""
        order = self._make_pending_order("cbthenwh")
        tx = self._make_transaction(order, external_intent_id="order_cbthenwh_1")
        amount_paise = int(order.total_amount * 100)

        with self.captureOnCommitCallbacks(execute=True):
            confirm_payment_success(payment_transaction=tx, external_transaction_id="pay_shared_1")

        response = self._post(
            _event(
                razorpay_order_id="order_cbthenwh_1",
                razorpay_payment_id="pay_shared_1",
                amount_paise=amount_paise,
            ),
            event_id="evt_cbthenwh_1",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        tx.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        self.assertEqual(tx.external_transaction_id, "pay_shared_1")
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)
        event = RazorpayWebhookEvent.objects.get(event_id="evt_cbthenwh_1")
        self.assertEqual(event.status, RazorpayWebhookEventStatus.PROCESSED)

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_webhook_then_browser_callback_confirms_only_once(self, mock_delay):
        order = self._make_pending_order("whthencb")
        tx = self._make_transaction(order, external_intent_id="order_whthencb_1")
        amount_paise = int(order.total_amount * 100)

        self._post(
            _event(
                razorpay_order_id="order_whthencb_1",
                razorpay_payment_id="pay_shared_2",
                amount_paise=amount_paise,
            ),
            event_id="evt_whthencb_1",
        )
        # Simulates razorpay_callback_view arriving second (slow browser redirect).
        confirm_payment_success(payment_transaction=tx, external_transaction_id="pay_shared_2")

        order.refresh_from_db()
        tx.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        self.assertEqual(tx.external_transaction_id, "pay_shared_2")
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)

    # ---- unresolved / mismatched events ------------------------------------

    def test_captured_event_missing_payment_id_is_rejected(self):
        order = self._make_pending_order("nopid")
        self._make_transaction(order, external_intent_id="order_nopid_1")

        response = self._post(
            _event(
                razorpay_order_id="order_nopid_1",
                razorpay_payment_id="",
                amount_paise=int(order.total_amount * 100),
            ),
            event_id="evt_nopid_1",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        event = RazorpayWebhookEvent.objects.get(event_id="evt_nopid_1")
        self.assertEqual(event.status, RazorpayWebhookEventStatus.ERROR)

    def test_unknown_transaction_is_recorded_and_acked(self):
        response = self._post(
            _event(razorpay_order_id="order_never_existed", razorpay_payment_id="pay_never", amount_paise=5000),
            event_id="evt_unknown_1",
        )
        self.assertEqual(response.status_code, 200)
        event = RazorpayWebhookEvent.objects.get(event_id="evt_unknown_1")
        self.assertEqual(event.status, RazorpayWebhookEventStatus.UNKNOWN_TRANSACTION)
        self.assertIsNone(event.payment_transaction)

    def test_amount_mismatch_does_not_confirm_order(self):
        order = self._make_pending_order("amtmismatch")
        self._make_transaction(order, external_intent_id="order_amt_1")

        response = self._post(
            _event(
                razorpay_order_id="order_amt_1",
                razorpay_payment_id="pay_amt_1",
                amount_paise=1,  # wrong on purpose
            ),
            event_id="evt_amt_1",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        event = RazorpayWebhookEvent.objects.get(event_id="evt_amt_1")
        self.assertEqual(event.status, RazorpayWebhookEventStatus.AMOUNT_MISMATCH)

    def test_currency_mismatch_does_not_confirm_order(self):
        order = self._make_pending_order("curmismatch")
        self._make_transaction(order, external_intent_id="order_cur_1")

        response = self._post(
            _event(
                razorpay_order_id="order_cur_1",
                razorpay_payment_id="pay_cur_1",
                amount_paise=int(order.total_amount * 100),
                currency="USD",  # order currency is INR
            ),
            event_id="evt_cur_1",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        event = RazorpayWebhookEvent.objects.get(event_id="evt_cur_1")
        self.assertEqual(event.status, RazorpayWebhookEventStatus.CURRENCY_MISMATCH)

    def test_payment_failed_does_not_downgrade_already_successful_transaction(self):
        order = self._make_pending_order("staleFailed")
        tx = self._make_transaction(order, external_intent_id="order_stale_1")
        confirm_payment_success(payment_transaction=tx)

        response = self._post(
            _event(
                event_type="payment.failed",
                razorpay_order_id="order_stale_1",
                razorpay_payment_id="pay_stale_1",
                amount_paise=int(order.total_amount * 100),
            ),
            event_id="evt_stale_failed_1",
        )

        self.assertEqual(response.status_code, 200)
        tx.refresh_from_db()
        self.assertEqual(tx.status, PaymentStatus.SUCCESS)

    def test_unrecognized_event_type_is_ignored(self):
        order = self._make_pending_order("ignoredtype")
        self._make_transaction(order, external_intent_id="order_ignored_1")

        response = self._post(
            _event(
                event_type="refund.processed",
                razorpay_order_id="order_ignored_1",
                razorpay_payment_id="pay_ignored_1",
                amount_paise=int(order.total_amount * 100),
            ),
            event_id="evt_ignored_1",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        event = RazorpayWebhookEvent.objects.get(event_id="evt_ignored_1")
        self.assertEqual(event.status, RazorpayWebhookEventStatus.IGNORED_EVENT_TYPE)


def _response(status_code: int, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


class RazorpayCapturePaymentTests(TestCase):
    """
    Unit tests for RazorpayAdapter.capture_payment's disambiguation between a
    genuine capture failure and a legitimate "already captured" outcome (the
    common case when Razorpay auto-capture is enabled) — isolated from the
    browser view and real network calls.
    """

    def setUp(self) -> None:
        self.adapter = RazorpayAdapter()
        creds_patch = patch(
            "payments.adapters.concrete._get_razorpay_credentials",
            return_value=("test_key_id", "test_key_secret"),
        )
        creds_patch.start()
        self.addCleanup(creds_patch.stop)

    @patch("requests.post")
    def test_successful_capture_returns_true(self, mock_post):
        mock_post.return_value = _response(200)
        result = self.adapter.capture_payment(
            razorpay_payment_id="pay_live_success", amount=Decimal("500.00"), currency="INR"
        )
        self.assertTrue(result)

    @patch("requests.get")
    @patch("requests.post")
    def test_already_captured_payment_is_treated_as_success(self, mock_post, mock_get):
        mock_post.return_value = _response(
            400, {"error": {"description": "This payment has already been captured"}}
        )
        mock_get.return_value = _response(200, {"status": "captured"})

        result = self.adapter.capture_payment(
            razorpay_payment_id="pay_live_already_captured", amount=Decimal("500.00"), currency="INR"
        )

        self.assertTrue(result)
        mock_get.assert_called_once()

    @patch("requests.get")
    @patch("requests.post")
    def test_genuine_capture_failure_returns_false(self, mock_post, mock_get):
        mock_post.return_value = _response(400, {"error": {"description": "Payment is not in authorized state."}})
        mock_get.return_value = _response(200, {"status": "failed"})

        result = self.adapter.capture_payment(
            razorpay_payment_id="pay_live_failed", amount=Decimal("500.00"), currency="INR"
        )

        self.assertFalse(result)

    @patch("requests.post", side_effect=Exception("simulated network failure"))
    def test_network_exception_returns_false_not_true(self, mock_post):
        result = self.adapter.capture_payment(
            razorpay_payment_id="pay_live_network_error", amount=Decimal("500.00"), currency="INR"
        )
        self.assertFalse(result)
