"""Concrete payment gateway adapters."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings

from payments.adapters.base import PaymentCaptureResult, PaymentGatewayAdapter, PaymentIntentResult


class QatarLocalGatewayAdapter(PaymentGatewayAdapter):
    """Qatar local payment rails sandbox adapter (e.g. NAPS-style deferred confirm)."""

    key = "qatar_local"
    display_name = "Qatar Local Payment"
    is_async = True

    def create_payment_intent(
        self,
        *,
        amount: Decimal,
        currency: str,
        metadata: dict[str, Any],
    ) -> PaymentIntentResult:
        intent_id = f"qa_pi_{uuid.uuid4().hex[:16]}"
        return PaymentIntentResult(
            intent_id=intent_id,
            metadata={"amount": str(amount), "currency": currency, **metadata},
            requires_webhook=True,
        )

    def verify_webhook(self, *, payload: bytes, signature: str) -> dict[str, Any]:
        expected = hmac.new(b"sandbox-qatar", payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid Qatar local webhook signature.")
        return json.loads(payload.decode())

    def capture(self, *, intent_id: str) -> PaymentCaptureResult:
        return PaymentCaptureResult(success=True, transaction_id=f"qa_tx_{intent_id}")

    def refund(self, *, transaction_id: str, amount: Decimal) -> PaymentCaptureResult:
        return PaymentCaptureResult(success=True, transaction_id=f"qa_refund_{transaction_id}")


class ApplePayAdapter(PaymentGatewayAdapter):
    """Apple Pay wallet adapter — async webhook confirmation."""

    key = "apple_pay"
    display_name = "Apple Pay"
    is_async = True

    def create_payment_intent(
        self,
        *,
        amount: Decimal,
        currency: str,
        metadata: dict[str, Any],
    ) -> PaymentIntentResult:
        intent_id = f"ap_pi_{uuid.uuid4().hex[:16]}"
        return PaymentIntentResult(intent_id=intent_id, requires_webhook=True, metadata=metadata)

    def verify_webhook(self, *, payload: bytes, signature: str) -> dict[str, Any]:
        expected = hmac.new(b"sandbox-apple", payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid Apple Pay webhook signature.")
        return json.loads(payload.decode())

    def capture(self, *, intent_id: str) -> PaymentCaptureResult:
        return PaymentCaptureResult(success=True, transaction_id=f"ap_tx_{intent_id}")

    def refund(self, *, transaction_id: str, amount: Decimal) -> PaymentCaptureResult:
        return PaymentCaptureResult(success=True, transaction_id=f"ap_refund_{transaction_id}")


class GooglePayAdapter(PaymentGatewayAdapter):
    """Google Pay wallet adapter — async webhook confirmation."""

    key = "google_pay"
    display_name = "Google Pay"
    is_async = True

    def create_payment_intent(
        self,
        *,
        amount: Decimal,
        currency: str,
        metadata: dict[str, Any],
    ) -> PaymentIntentResult:
        intent_id = f"gp_pi_{uuid.uuid4().hex[:16]}"
        return PaymentIntentResult(intent_id=intent_id, requires_webhook=True, metadata=metadata)

    def verify_webhook(self, *, payload: bytes, signature: str) -> dict[str, Any]:
        expected = hmac.new(b"sandbox-google", payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid Google Pay webhook signature.")
        return json.loads(payload.decode())

    def capture(self, *, intent_id: str) -> PaymentCaptureResult:
        return PaymentCaptureResult(success=True, transaction_id=f"gp_tx_{intent_id}")

    def refund(self, *, transaction_id: str, amount: Decimal) -> PaymentCaptureResult:
        return PaymentCaptureResult(success=True, transaction_id=f"gp_refund_{transaction_id}")


class CashOnDeliveryAdapter(PaymentGatewayAdapter):
    """
    Cash on Delivery (COD) payment adapter.
    """

    key = "cod"
    display_name = "Cash on Delivery"
    is_async = False

    def create_payment_intent(
        self,
        *,
        amount: Decimal,
        currency: str,
        metadata: dict[str, Any],
    ) -> PaymentIntentResult:
        intent_id = f"cod_pi_{uuid.uuid4().hex[:16]}"
        return PaymentIntentResult(
            intent_id=intent_id,
            metadata={"amount": str(amount), "currency": currency, **metadata},
        )

    def verify_webhook(self, *, payload: bytes, signature: str) -> dict[str, Any]:
        raise NotImplementedError("Cash on Delivery does not use webhooks.")

    def capture(self, *, intent_id: str) -> PaymentCaptureResult:
        return PaymentCaptureResult(
            success=True,
            transaction_id=f"cod_tx_{intent_id}",
            metadata={"gateway": self.key},
        )

    def refund(self, *, transaction_id: str, amount: Decimal) -> PaymentCaptureResult:
        return PaymentCaptureResult(success=True, transaction_id=f"cod_refund_{transaction_id}")


def _get_stripe_credentials() -> tuple[str, str]:
    """
    Resolve Stripe (publishable_key, secret_key) — DB first (dashboard-editable
    SiteSettings fields), env var fallback. Mirrors the credential-resolution
    pattern the Razorpay adapter used.
    """
    try:
        from core.models import SiteSettings
        settings_inst = SiteSettings.objects.first()
        if settings_inst:
            pub_key = settings_inst.stripe_publishable_key.strip()
            secret_key = settings_inst.stripe_secret_key.strip()
            if pub_key and secret_key:
                return pub_key, secret_key
    except Exception:
        pass
    import os
    return os.getenv("STRIPE_PUBLISHABLE_KEY", ""), os.getenv("STRIPE_SECRET_KEY", "")


class StripeAdapter(PaymentGatewayAdapter):
    """
    Stripe Checkout (hosted) adapter.

    ``create_payment_intent`` creates a Stripe Checkout Session — the
    ``intent_id`` stored on PaymentTransaction.external_intent_id is the
    Session ID (``cs_...``), not a PaymentIntent ID, so checkout views can
    retrieve the session later (e.g. to redirect to its ``.url``) purely from
    that one stored value, the same way the old Razorpay adapter let
    razorpay_pay_view rebuild everything from just the Razorpay order ID.
    """

    key = "stripe"
    display_name = "Card, Apple Pay & Google Pay"
    is_async = True

    def is_configured(self) -> bool:
        _, secret_key = _get_stripe_credentials()
        return bool(secret_key)

    def create_payment_intent(
        self,
        *,
        amount: Decimal,
        currency: str,
        metadata: dict[str, Any],
    ) -> PaymentIntentResult:
        import stripe

        _, secret_key = _get_stripe_credentials()
        amount_in_minor_unit = int((amount * 100).to_integral_value())

        order_id = str(metadata.get("order_id", ""))
        order_number = str(metadata.get("order_number", ""))
        success_url = metadata.get("success_url", "")
        cancel_url = metadata.get("cancel_url", "")
        customer_email = metadata.get("customer_email") or None

        if not secret_key:
            #no live credentials configured — local mock id so checkout flow
            #doesn't crash in dev; is_configured() keeps this gateway hidden
            #from checkout_view until real keys are set.
            return PaymentIntentResult(
                intent_id=f"cs_mock_{uuid.uuid4().hex[:16]}",
                requires_webhook=True,
                metadata={"order_id": order_id, "order_number": order_number},
            )

        session = stripe.checkout.Session.create(
            api_key=secret_key,
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "unit_amount": amount_in_minor_unit,
                        "product_data": {"name": f"Order {order_number}" if order_number else "Order"},
                    },
                    "quantity": 1,
                }
            ],
            client_reference_id=order_id,
            customer_email=customer_email,
            success_url=success_url or "https://example.com/",
            cancel_url=cancel_url or "https://example.com/",
            metadata={"order_id": order_id, "order_number": order_number},
            payment_intent_data={"metadata": {"order_id": order_id, "order_number": order_number}},
            idempotency_key=f"checkout_{order_id}_{metadata.get('attempt', 1)}",
        )
        return PaymentIntentResult(
            intent_id=session.id,
            client_secret=session.get("client_secret") or "",
            requires_webhook=True,
            metadata={"order_id": order_id, "order_number": order_number, "checkout_url": session.get("url") or ""},
        )

    def verify_webhook(self, *, payload: bytes, signature: str) -> dict[str, Any]:
        import stripe

        secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        if not secret:
            raise ValueError("Stripe webhook secret is not configured.")
        try:
            event = stripe.Webhook.construct_event(payload, signature, secret)
        except stripe.error.SignatureVerificationError as exc:
            raise ValueError("Invalid Stripe webhook signature.") from exc
        return event.to_dict()

    def capture(self, *, intent_id: str) -> PaymentCaptureResult:
        return PaymentCaptureResult(
            success=True,
            transaction_id=f"stripe_tx_{intent_id}",
            metadata={"gateway": self.key},
        )

    def refund(self, *, transaction_id: str, amount: Decimal) -> PaymentCaptureResult:
        import stripe

        _, secret_key = _get_stripe_credentials()
        if not secret_key or not transaction_id:
            return PaymentCaptureResult(success=False, transaction_id=transaction_id)

        amount_in_minor_unit = int((amount * 100).to_integral_value())
        try:
            refund = stripe.Refund.create(
                api_key=secret_key,
                payment_intent=transaction_id,
                amount=amount_in_minor_unit,
            )
        except Exception:
            return PaymentCaptureResult(success=False, transaction_id=transaction_id)

        return PaymentCaptureResult(
            success=refund.status in ("succeeded", "pending"),
            transaction_id=refund.id,
            metadata={"gateway": self.key, "stripe_refund_status": refund.status},
        )
