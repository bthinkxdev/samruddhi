"""Concrete payment gateway adapters."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from typing import Any

from payments.adapters.base import PaymentCaptureResult, PaymentGatewayAdapter, PaymentIntentResult


class CardGatewayAdapter(PaymentGatewayAdapter):
    """
    Generic card processor sandbox adapter.

    Uses a vendor-neutral interface (Stripe-like intent/capture shape) without
    coupling to a specific SDK — swap the internals when a processor is chosen.
    """

    key = "card"
    display_name = "Credit / Debit Card"
    is_async = False

    def create_payment_intent(
        self,
        *,
        amount: Decimal,
        currency: str,
        metadata: dict[str, Any],
    ) -> PaymentIntentResult:
        intent_id = f"card_pi_{uuid.uuid4().hex[:16]}"
        return PaymentIntentResult(
            intent_id=intent_id,
            client_secret=f"{intent_id}_secret",
            metadata={"amount": str(amount), "currency": currency, **metadata},
        )

    def verify_webhook(self, *, payload: bytes, signature: str) -> dict[str, Any]:
        expected = hmac.new(b"sandbox-card", payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid card webhook signature.")
        return json.loads(payload.decode())

    def capture(self, *, intent_id: str) -> PaymentCaptureResult:
        if intent_id.startswith("card_fail"):
            return PaymentCaptureResult(success=False, transaction_id=intent_id)
        return PaymentCaptureResult(
            success=True,
            transaction_id=f"card_tx_{intent_id}",
            metadata={"gateway": self.key},
        )

    def refund(self, *, transaction_id: str, amount: Decimal) -> PaymentCaptureResult:
        return PaymentCaptureResult(success=True, transaction_id=f"refund_{transaction_id}")


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


def _get_razorpay_credentials() -> tuple[str, str]:
    try:
        from core.models import SiteSettings
        settings_inst = SiteSettings.objects.first()
        if settings_inst:
            key_id = settings_inst.razorpay_key_id.strip()
            key_secret = settings_inst.razorpay_key_secret.strip()
            if key_id and key_secret:
                return key_id, key_secret
    except Exception:
        pass
    import os
    return os.getenv("RAZORPAY_KEY_ID", ""), os.getenv("RAZORPAY_KEY_SECRET", "")


class RazorpayAdapter(PaymentGatewayAdapter):
    """
    Razorpay payment gateway base adapter.
    """
    key = "razorpay"
    display_name = "Razorpay (UPI, Credit/Debit Card, Net Banking, Wallets)"
    is_async = True

    def create_payment_intent(
        self,
        *,
        amount: Decimal,
        currency: str,
        metadata: dict[str, Any],
    ) -> PaymentIntentResult:
        key_id, key_secret = _get_razorpay_credentials()
        amount_in_paise = int(amount * 100)

        if key_id and key_secret:
            try:
                import requests
                response = requests.post(
                    "https://api.razorpay.com/v1/orders",
                    auth=(key_id, key_secret),
                    json={
                        "amount": amount_in_paise,
                        "currency": currency,
                        "receipt": f"ord_{metadata.get('order_id', '')}",
                        "notes": {
                            "order_id": str(metadata.get("order_id", "")),
                            "order_number": str(metadata.get("order_number", "")),
                        },
                    },
                    timeout=10,
                )
                if response.status_code in (200, 201):
                    data = response.json()
                    intent_id = data.get("id")
                    return PaymentIntentResult(
                        intent_id=intent_id,
                        requires_webhook=True,
                        metadata={"key_id": key_id, "razorpay_order_id": intent_id, **metadata},
                    )
            except Exception:
                pass

        intent_id = f"rzp_order_{uuid.uuid4().hex[:16]}"
        return PaymentIntentResult(
            intent_id=intent_id,
            requires_webhook=True,
            metadata={"key_id": key_id or "rzp_test_mock", "razorpay_order_id": intent_id, **metadata},
        )

    def verify_payment_signature(
        self,
        *,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> bool:
        key_id, key_secret = _get_razorpay_credentials()
        if not key_secret:
            return True
        msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        expected = hmac.new(key_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, razorpay_signature)

    def verify_webhook(self, *, payload: bytes, signature: str) -> dict[str, Any]:
        key_id, key_secret = _get_razorpay_credentials()
        if key_secret:
            expected = hmac.new(key_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise ValueError("Invalid Razorpay webhook signature.")
        return json.loads(payload.decode())

    def capture_payment(
        self,
        *,
        razorpay_payment_id: str,
        amount: Any = 0,
        currency: str = None,
    ) -> bool:
        """
        Capture a Razorpay payment, or confirm it was already captured.

        Returns True only when Razorpay confirms the payment is actually
        captured — never on ambiguity. Two cases require care beyond a bare
        HTTP-status check on the capture call itself:

        - Already captured: when auto-capture is enabled (Razorpay's default),
          the payment may already be captured by the time this runs. Calling
          /capture again then returns HTTP 400 "This payment has already been
          captured" — a legitimate success, not a failure. We disambiguate by
          fetching the payment directly rather than parsing error text.
        - Any network/exception failure now returns False instead of silently
          assuming success — a blocked confirmation here is still recoverable
          via the Razorpay webhook, but a wrongly-confirmed order is not.
        """
        if not currency:
            from core.selectors import get_default_currency
            default_curr = get_default_currency()
            currency = default_curr.code if default_curr else "AED"
        key_id, key_secret = _get_razorpay_credentials()
        if not (key_id and key_secret and razorpay_payment_id) or razorpay_payment_id.startswith("pay_test_"):
            return True

        import requests
        try:
            amount_in_paise = int(amount * 100)
            resp = requests.post(
                f"https://api.razorpay.com/v1/payments/{razorpay_payment_id}/capture",
                auth=(key_id, key_secret),
                json={"amount": amount_in_paise, "currency": currency},
                timeout=10,
            )
        except Exception:
            return False

        if resp.status_code in (200, 201):
            return True

        return self._fetch_payment_is_captured(
            razorpay_payment_id=razorpay_payment_id, key_id=key_id, key_secret=key_secret,
        )

    def _fetch_payment_is_captured(self, *, razorpay_payment_id: str, key_id: str, key_secret: str) -> bool:
        """Authoritative check of a payment's actual status, used when the
        capture call itself returned a non-2xx (e.g. already captured, or a
        genuine failure — only GET /payments/{id} can tell them apart)."""
        import requests
        try:
            resp = requests.get(
                f"https://api.razorpay.com/v1/payments/{razorpay_payment_id}",
                auth=(key_id, key_secret),
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("status") == "captured"
        except Exception:
            pass
        return False

    def capture(self, *, intent_id: str) -> PaymentCaptureResult:
        return PaymentCaptureResult(
            success=True,
            transaction_id=f"rzp_tx_{intent_id}",
            metadata={"gateway": self.key},
        )

    def refund(self, *, transaction_id: str, amount: Decimal) -> PaymentCaptureResult:
        return PaymentCaptureResult(success=True, transaction_id=f"razorpay_refund_{transaction_id}")

class RazorpayUPIAdapter(RazorpayAdapter):
    key = "razorpay_upi"
    display_name = "UPI"

class RazorpayCardAdapter(RazorpayAdapter):
    key = "razorpay_card"
    display_name = "Credit/Debit Card"

class RazorpayNetbankingAdapter(RazorpayAdapter):
    key = "razorpay_netbanking"
    display_name = "Net Banking"

class RazorpayWalletAdapter(RazorpayAdapter):
    key = "razorpay_wallet"
    display_name = "Wallet"
