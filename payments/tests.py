"""Tests for the real Stripe webhook and idempotent payment confirmation.

Object construction mirrors core.management.commands.audit_page_queries: build a
Currency, Cart/CartItem, checkout session, and a real Order via
checkout.services.place_order — then attach a PaymentTransaction directly (with a
known external_intent_id/amount/currency) rather than going through the real
Stripe HTTP API, so these tests never make network calls. Webhook payloads are
signed with the same HMAC-SHA256 scheme Stripe itself uses
(stripe.Webhook.construct_event verifies it for real), built by hand here so
these tests don't depend on any Stripe test-mode credentials.

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
import time
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
from payments.adapters.concrete import StripeAdapter
from payments.models import (
    PaymentStatus,
    PaymentTransaction,
    StripeWebhookEvent,
    StripeWebhookEventStatus,
)
from payments.services import confirm_payment_success

WEBHOOK_SECRET = "whsec_test_stripe_webhook_secret"


def _sign(payload: bytes, *, timestamp: int | None = None) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _session_event(
    *,
    event_id: str,
    event_type: str = "checkout.session.completed",
    session_id: str,
    payment_intent_id: str = "",
    amount_total: int,
    currency: str = "aed",
    payment_status: str = "paid",
    order_id: str = "",
) -> dict:
    """Build a Stripe webhook payload matching a real checkout.session.* event's shape."""
    return {
        "id": event_id,
        "type": event_type,
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "payment_status": payment_status,
                "amount_total": amount_total,
                "currency": currency,
                "payment_intent": payment_intent_id,
                "metadata": {"order_id": str(order_id)},
            }
        },
    }


def _payment_intent_failed_event(
    *,
    event_id: str,
    payment_intent_id: str,
    amount: int,
    currency: str = "aed",
    order_id: str = "",
) -> dict:
    """Build a Stripe webhook payload matching a real payment_intent.payment_failed event."""
    return {
        "id": event_id,
        "type": "payment_intent.payment_failed",
        "data": {
            "object": {
                "id": payment_intent_id,
                "object": "payment_intent",
                "amount": amount,
                "currency": currency,
                "status": "requires_payment_method",
                "metadata": {"order_id": str(order_id)},
            }
        },
    }


@override_settings(STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET)
class StripeWebhookTests(TestCase):
    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="AED",
            defaults={"symbol": "AED", "exchange_rate_to_base": "1.00000000", "is_default": True},
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
        self.webhook_url = reverse("payments:stripe-webhook")

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
            gateway_key="stripe",
            customer_profile=self.profile,
        )
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        return order

    def _make_transaction(self, order, *, external_intent_id: str) -> PaymentTransaction:
        return PaymentTransaction.objects.create(
            order=order,
            gateway_key="stripe",
            amount=order.total_amount,
            currency=order.currency,
            status=PaymentStatus.PENDING,
            external_intent_id=external_intent_id,
        )

    def _post(self, event_data: dict, *, signature: str | None = "__auto__"):
        body = json.dumps(event_data).encode("utf-8")
        sig_header = _sign(body) if signature == "__auto__" else signature
        headers = {}
        if sig_header:
            headers["HTTP_STRIPE_SIGNATURE"] = sig_header
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.webhook_url, data=body, content_type="application/json", **headers
            )
        return response

    # ---- happy path -----------------------------------------------------

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_checkout_session_completed_confirms_order_end_to_end(self, mock_delay):
        order = self._make_pending_order("completed")
        tx = self._make_transaction(order, external_intent_id="cs_completed_1")
        amount_minor = int(order.total_amount * 100)

        response = self._post(
            _session_event(
                event_id="evt_completed_1",
                session_id="cs_completed_1",
                payment_intent_id="pi_completed_1",
                amount_total=amount_minor,
                currency=order.currency.code.lower(),
                order_id=order.pk,
            )
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        tx.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        self.assertEqual(tx.status, PaymentStatus.SUCCESS)
        self.assertEqual(tx.external_transaction_id, "pi_completed_1")
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)

        event = StripeWebhookEvent.objects.get(event_id="evt_completed_1")
        self.assertEqual(event.status, StripeWebhookEventStatus.PROCESSED)
        self.assertEqual(event.payment_transaction_id, tx.pk)

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_async_payment_succeeded_confirms_order_end_to_end(self, mock_delay):
        order = self._make_pending_order("async-ok")
        self._make_transaction(order, external_intent_id="cs_async_ok_1")
        amount_minor = int(order.total_amount * 100)

        response = self._post(
            _session_event(
                event_id="evt_async_ok_1",
                event_type="checkout.session.async_payment_succeeded",
                session_id="cs_async_ok_1",
                payment_intent_id="pi_async_ok_1",
                amount_total=amount_minor,
                currency=order.currency.code.lower(),
                order_id=order.pk,
            )
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        mock_delay.assert_called_once_with(order_id=order.pk)

    # ---- security / parsing ---------------------------------------------

    def test_invalid_signature_rejected(self):
        order = self._make_pending_order("badsig")
        self._make_transaction(order, external_intent_id="cs_badsig_1")
        response = self._post(
            _session_event(
                event_id="evt_badsig_1",
                session_id="cs_badsig_1",
                amount_total=int(order.total_amount * 100),
                order_id=order.pk,
            ),
            signature="t=1700000000,v1=not-the-real-signature",
        )
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        self.assertFalse(StripeWebhookEvent.objects.filter(event_id="evt_badsig_1").exists())

    def test_missing_signature_rejected(self):
        response = self._post(
            _session_event(event_id="evt_nosig", session_id="cs_x", amount_total=100),
            signature="",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_event_id_rejected(self):
        body_dict = _session_event(event_id="evt_placeholder", session_id="cs_x", amount_total=100)
        body_dict["id"] = ""
        response = self._post(body_dict)
        self.assertEqual(response.status_code, 400)

    def test_malformed_json_rejected(self):
        body = b"{not valid json"
        response = self.client.post(
            self.webhook_url,
            data=body,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=_sign(body),
        )
        self.assertEqual(response.status_code, 400)

    # ---- idempotency ------------------------------------------------------

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_duplicate_event_id_is_a_noop(self, mock_delay):
        order = self._make_pending_order("dup")
        self._make_transaction(order, external_intent_id="cs_dup_1")
        event_data = _session_event(
            event_id="evt_dup_1",
            session_id="cs_dup_1",
            payment_intent_id="pi_dup_1",
            amount_total=int(order.total_amount * 100),
            order_id=order.pk,
        )

        first = self._post(event_data)
        second = self._post(event_data)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(json.loads(first.content)["duplicate"])
        self.assertTrue(json.loads(second.content)["duplicate"])
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)
        self.assertEqual(StripeWebhookEvent.objects.filter(event_id="evt_dup_1").count(), 1)

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_different_event_ids_same_payment_confirm_only_once(self, mock_delay):
        """Stripe can fire both checkout.session.completed and
        async_payment_succeeded for one session — two different event_ids.
        Only the PaymentTransaction-level guard in confirm_payment_success
        catches this, not event_id dedup."""
        order = self._make_pending_order("crosstype")
        self._make_transaction(order, external_intent_id="cs_crosstype_1")
        amount_minor = int(order.total_amount * 100)

        self._post(
            _session_event(
                event_id="evt_crosstype_completed",
                event_type="checkout.session.completed",
                session_id="cs_crosstype_1",
                payment_intent_id="pi_crosstype_1",
                amount_total=amount_minor,
                order_id=order.pk,
            )
        )
        self._post(
            _session_event(
                event_id="evt_crosstype_async",
                event_type="checkout.session.async_payment_succeeded",
                session_id="cs_crosstype_1",
                payment_intent_id="pi_crosstype_1",
                amount_total=amount_minor,
                order_id=order.pk,
            )
        )

        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)
        self.assertEqual(
            StripeWebhookEvent.objects.filter(
                event_id__in=["evt_crosstype_completed", "evt_crosstype_async"],
                status=StripeWebhookEventStatus.PROCESSED,
            ).count(),
            2,
        )

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_conflicting_intent_id_is_not_overwritten_and_not_reconfirmed(self, mock_delay):
        """A later event referencing a *different* PaymentIntent id than the one
        that actually confirmed the order must not overwrite
        external_transaction_id and must not be silently treated as an
        ordinary processed event — it's recorded as INTENT_ID_MISMATCH so it
        surfaces for investigation."""
        order = self._make_pending_order("overwrite")
        tx = self._make_transaction(order, external_intent_id="cs_overwrite_1")
        amount_minor = int(order.total_amount * 100)

        self._post(
            _session_event(
                event_id="evt_overwrite_first",
                session_id="cs_overwrite_1",
                payment_intent_id="pi_real_winner",
                amount_total=amount_minor,
                order_id=order.pk,
            )
        )
        tx.refresh_from_db()
        self.assertEqual(tx.external_transaction_id, "pi_real_winner")

        self._post(
            _session_event(
                event_id="evt_overwrite_second",
                session_id="cs_overwrite_1",
                payment_intent_id="pi_stale_impostor",
                amount_total=amount_minor,
                order_id=order.pk,
            )
        )

        tx.refresh_from_db()
        self.assertEqual(tx.external_transaction_id, "pi_real_winner")
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)
        second_event = StripeWebhookEvent.objects.get(event_id="evt_overwrite_second")
        self.assertEqual(second_event.status, StripeWebhookEventStatus.INTENT_ID_MISMATCH)

    def test_confirm_payment_success_called_twice_directly_is_idempotent(self):
        """Sequential proof of the transaction-level guard itself (see module
        docstring re: sqlite not exercising real row locking)."""
        order = self._make_pending_order("directcall")
        tx = self._make_transaction(order, external_intent_id="cs_directcall_1")

        confirm_payment_success(payment_transaction=tx)
        confirm_payment_success(payment_transaction=tx)

        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_browser_return_then_webhook_confirms_only_once(self, mock_delay):
        """confirm_payment_success(...) here stands in for stripe_return_view,
        which calls the exact same function — proving the two channels share
        one idempotent convergence point without needing a second HTTP round
        trip through the checkout app."""
        order = self._make_pending_order("cbthenwh")
        tx = self._make_transaction(order, external_intent_id="cs_cbthenwh_1")
        amount_minor = int(order.total_amount * 100)

        with self.captureOnCommitCallbacks(execute=True):
            confirm_payment_success(payment_transaction=tx, external_transaction_id="pi_shared_1")

        response = self._post(
            _session_event(
                event_id="evt_cbthenwh_1",
                session_id="cs_cbthenwh_1",
                payment_intent_id="pi_shared_1",
                amount_total=amount_minor,
                order_id=order.pk,
            )
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        tx.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        self.assertEqual(tx.external_transaction_id, "pi_shared_1")
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)
        event = StripeWebhookEvent.objects.get(event_id="evt_cbthenwh_1")
        self.assertEqual(event.status, StripeWebhookEventStatus.PROCESSED)

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_webhook_then_browser_return_confirms_only_once(self, mock_delay):
        order = self._make_pending_order("whthencb")
        tx = self._make_transaction(order, external_intent_id="cs_whthencb_1")
        amount_minor = int(order.total_amount * 100)

        self._post(
            _session_event(
                event_id="evt_whthencb_1",
                session_id="cs_whthencb_1",
                payment_intent_id="pi_shared_2",
                amount_total=amount_minor,
                order_id=order.pk,
            )
        )
        # Simulates stripe_return_view arriving second (slow browser redirect).
        confirm_payment_success(payment_transaction=tx, external_transaction_id="pi_shared_2")

        order.refresh_from_db()
        tx.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        self.assertEqual(tx.external_transaction_id, "pi_shared_2")
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
        mock_delay.assert_called_once_with(order_id=order.pk)

    # ---- unresolved / mismatched events ------------------------------------

    def test_completed_event_not_yet_paid_does_not_confirm(self):
        """checkout.session.completed can fire before an async payment method
        has actually settled — only a paid (or no-payment-required) session
        confirms the order."""
        order = self._make_pending_order("notpaidyet")
        self._make_transaction(order, external_intent_id="cs_notpaidyet_1")

        response = self._post(
            _session_event(
                event_id="evt_notpaidyet_1",
                session_id="cs_notpaidyet_1",
                payment_intent_id="pi_notpaidyet_1",
                amount_total=int(order.total_amount * 100),
                payment_status="unpaid",
                order_id=order.pk,
            )
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        event = StripeWebhookEvent.objects.get(event_id="evt_notpaidyet_1")
        self.assertEqual(event.status, StripeWebhookEventStatus.ERROR)

    def test_unknown_transaction_is_recorded_and_acked(self):
        response = self._post(
            _session_event(
                event_id="evt_unknown_1",
                session_id="cs_never_existed",
                amount_total=5000,
            )
        )
        self.assertEqual(response.status_code, 200)
        event = StripeWebhookEvent.objects.get(event_id="evt_unknown_1")
        self.assertEqual(event.status, StripeWebhookEventStatus.UNKNOWN_TRANSACTION)
        self.assertIsNone(event.payment_transaction)

    def test_amount_mismatch_does_not_confirm_order(self):
        order = self._make_pending_order("amtmismatch")
        self._make_transaction(order, external_intent_id="cs_amt_1")

        response = self._post(
            _session_event(
                event_id="evt_amt_1",
                session_id="cs_amt_1",
                payment_intent_id="pi_amt_1",
                amount_total=1,  # wrong on purpose
                order_id=order.pk,
            )
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        event = StripeWebhookEvent.objects.get(event_id="evt_amt_1")
        self.assertEqual(event.status, StripeWebhookEventStatus.AMOUNT_MISMATCH)

    def test_currency_mismatch_does_not_confirm_order(self):
        order = self._make_pending_order("curmismatch")
        self._make_transaction(order, external_intent_id="cs_cur_1")

        response = self._post(
            _session_event(
                event_id="evt_cur_1",
                session_id="cs_cur_1",
                payment_intent_id="pi_cur_1",
                amount_total=int(order.total_amount * 100),
                currency="usd",  # order currency is AED
                order_id=order.pk,
            )
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        event = StripeWebhookEvent.objects.get(event_id="evt_cur_1")
        self.assertEqual(event.status, StripeWebhookEventStatus.CURRENCY_MISMATCH)

    def test_payment_failed_does_not_downgrade_already_successful_transaction(self):
        order = self._make_pending_order("staleFailed")
        tx = self._make_transaction(order, external_intent_id="cs_stale_1")
        confirm_payment_success(payment_transaction=tx)

        response = self._post(
            _payment_intent_failed_event(
                event_id="evt_stale_failed_1",
                payment_intent_id="pi_stale_1",
                amount=int(order.total_amount * 100),
                order_id=order.pk,
            )
        )

        self.assertEqual(response.status_code, 200)
        tx.refresh_from_db()
        self.assertEqual(tx.status, PaymentStatus.SUCCESS)

    @patch("notifications.tasks.dispatch_order_confirmation_notification.delay")
    def test_payment_intent_payment_failed_resolved_via_order_id_metadata(self, mock_delay):
        """payment_intent.payment_failed carries a PaymentIntent, not a
        Session — resolved via the order_id embedded in its own metadata,
        since there's no session id on this event at all."""
        order = self._make_pending_order("pifailed")
        tx = self._make_transaction(order, external_intent_id="cs_pifailed_1")

        response = self._post(
            _payment_intent_failed_event(
                event_id="evt_pifailed_1",
                payment_intent_id="pi_pifailed_1",
                amount=int(order.total_amount * 100),
                order_id=order.pk,
            )
        )

        self.assertEqual(response.status_code, 200)
        tx.refresh_from_db()
        self.assertEqual(tx.status, PaymentStatus.FAILED)
        mock_delay.assert_not_called()
        event = StripeWebhookEvent.objects.get(event_id="evt_pifailed_1")
        self.assertEqual(event.status, StripeWebhookEventStatus.PROCESSED)
        self.assertEqual(event.payment_transaction_id, tx.pk)

    def test_unrecognized_event_type_is_ignored(self):
        order = self._make_pending_order("ignoredtype")
        self._make_transaction(order, external_intent_id="cs_ignored_1")

        response = self._post(
            _session_event(
                event_id="evt_ignored_1",
                event_type="checkout.session.expired",
                session_id="cs_ignored_1",
                amount_total=int(order.total_amount * 100),
                order_id=order.pk,
            )
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        event = StripeWebhookEvent.objects.get(event_id="evt_ignored_1")
        self.assertEqual(event.status, StripeWebhookEventStatus.IGNORED_EVENT_TYPE)


class StripeRefundTests(TestCase):
    """Unit tests for StripeAdapter.refund — isolated from real network calls."""

    def setUp(self) -> None:
        self.adapter = StripeAdapter()
        creds_patch = patch(
            "payments.adapters.concrete._get_stripe_credentials",
            return_value=("pk_test", "sk_test"),
        )
        creds_patch.start()
        self.addCleanup(creds_patch.stop)

    @patch("stripe.Refund.create")
    def test_successful_refund_returns_success(self, mock_create):
        mock_create.return_value = MagicMock(status="succeeded", id="re_1")
        result = self.adapter.refund(transaction_id="pi_1", amount=Decimal("500.00"))
        self.assertTrue(result.success)
        self.assertEqual(result.transaction_id, "re_1")

    @patch("stripe.Refund.create")
    def test_pending_refund_is_treated_as_success(self, mock_create):
        mock_create.return_value = MagicMock(status="pending", id="re_2")
        result = self.adapter.refund(transaction_id="pi_2", amount=Decimal("500.00"))
        self.assertTrue(result.success)

    @patch("stripe.Refund.create")
    def test_failed_refund_returns_failure(self, mock_create):
        mock_create.return_value = MagicMock(status="failed", id="re_3")
        result = self.adapter.refund(transaction_id="pi_3", amount=Decimal("500.00"))
        self.assertFalse(result.success)

    @patch("stripe.Refund.create", side_effect=Exception("simulated network failure"))
    def test_network_exception_returns_failure_not_success(self, mock_create):
        result = self.adapter.refund(transaction_id="pi_4", amount=Decimal("500.00"))
        self.assertFalse(result.success)

    def test_refund_without_credentials_returns_failure(self):
        with patch(
            "payments.adapters.concrete._get_stripe_credentials",
            return_value=("", ""),
        ):
            result = self.adapter.refund(transaction_id="pi_5", amount=Decimal("500.00"))
        self.assertFalse(result.success)
