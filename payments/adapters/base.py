"""Payment gateway adapter base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class PaymentIntentResult:
    """Result from create_payment_intent."""

    intent_id: str
    client_secret: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    requires_webhook: bool = False


@dataclass
class PaymentCaptureResult:
    """Result from synchronous capture."""

    success: bool
    transaction_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class PaymentGatewayAdapter(ABC):
    """
    Abstract payment gateway — all concrete adapters implement this interface.

    Checkout selects adapters by registry key; it never imports concrete classes.
    """

    key: str = ""
    display_name: str = ""
    is_async: bool = False

    @abstractmethod
    def create_payment_intent(
        self,
        *,
        amount: Decimal,
        currency: str,
        metadata: dict[str, Any],
    ) -> PaymentIntentResult:
        """Create a payment intent with the external or internal processor."""

    @abstractmethod
    def verify_webhook(self, *, payload: bytes, signature: str) -> dict[str, Any]:
        """Verify and parse a webhook payload; raise on invalid signature."""

    @abstractmethod
    def capture(self, *, intent_id: str) -> PaymentCaptureResult:
        """Capture/finalize a previously created intent (sync gateways)."""

    @abstractmethod
    def refund(self, *, transaction_id: str, amount: Decimal) -> PaymentCaptureResult:
        """Refund all or part of a captured transaction."""
