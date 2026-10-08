"""Payment gateway registry — checkout selects by string key only."""

from __future__ import annotations

from typing import TYPE_CHECKING

from payments.adapters.concrete import (
    ApplePayAdapter,
    CardGatewayAdapter,
    GooglePayAdapter,
    CashOnDeliveryAdapter,
    RazorpayAdapter,
    RazorpayUPIAdapter,
    RazorpayCardAdapter,
    RazorpayNetbankingAdapter,
    RazorpayWalletAdapter,
)

if TYPE_CHECKING:
    from payments.adapters.base import PaymentGatewayAdapter

PAYMENT_GATEWAYS: dict[str, PaymentGatewayAdapter] = {
    RazorpayUPIAdapter.key: RazorpayUPIAdapter(),
    RazorpayCardAdapter.key: RazorpayCardAdapter(),
    RazorpayNetbankingAdapter.key: RazorpayNetbankingAdapter(),
    RazorpayWalletAdapter.key: RazorpayWalletAdapter(),
    CashOnDeliveryAdapter.key: CashOnDeliveryAdapter(),
}


def get_payment_adapter(*, gateway_key: str) -> PaymentGatewayAdapter:
    """Look up a registered adapter by key."""
    adapter = PAYMENT_GATEWAYS.get(gateway_key)
    if adapter is None:
        raise KeyError(f"Unknown payment gateway: {gateway_key}")
    return adapter


def register_payment_adapter(*, adapter: PaymentGatewayAdapter) -> None:
    """
    Register an adapter at runtime (used by tests and future plugins).

    Adding a gateway requires only registry registration — zero checkout view edits.
    """
    PAYMENT_GATEWAYS[adapter.key] = adapter
