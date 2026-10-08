"""Tests for the orders app."""

from __future__ import annotations

from django.test import TestCase

from accounts.services import register_customer_email
from catalog.models import Collection, Product
from core.models import Currency
from orders.models import Order, OrderItem, OrderStatus
from orders.services import transition_order_status


class RestockOnCancelRefundTests(TestCase):
    """
    adjust_stock is only ever called with a negative delta at order placement
    (checkout.services) or CHECKOUT_PENDING->CONFIRMED (orders.services) — so
    cancelling/refunding must give that same stock back exactly once, never
    for an order whose stock was never actually reserved.
    """

    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="restock-test@example.com", password="testpass12345", name="Restock Test"
        )
        collection = Collection.objects.create(name="Restock Collection", slug="restock-collection")
        self.product = Product.objects.create(
            name="Restock Yarn",
            slug="restock-yarn",
            sku="SKU-RESTOCK-1",
            base_price="500.00",
            mrp="500.00",
            purchase_price="300.00",
            stock_quantity=10,
        )
        self.product.collections.add(collection)

    def _make_order(self, *, status: str, suffix: str, quantity: int = 2) -> Order:
        order = Order.objects.create(
            customer_profile=self.profile,
            order_number=f"#RESTOCK-{suffix}",
            idempotency_key=f"restock-{suffix}",
            order_status=status,
            subtotal="1000.00",
            total_amount="1000.00",
            currency=self.currency,
        )
        OrderItem.objects.create(
            order=order, product=self.product, quantity=quantity, unit_price="500.00"
        )
        return order

    def test_cancel_from_placed_cod_restocks(self) -> None:
        self.product.stock_quantity = 8  # already decremented by 2 at placement
        self.product.save(update_fields=["stock_quantity"])
        order = self._make_order(status=OrderStatus.PLACED_COD, suffix="cod-cancel")

        transition_order_status(order=order, new_status=OrderStatus.CANCELLED, force=True)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)

    def test_cancel_from_checkout_pending_does_not_restock(self) -> None:
        #stock was never decremented for a still-pending order, so cancelling
        #it must not inflate stock.
        order = self._make_order(status=OrderStatus.CHECKOUT_PENDING, suffix="pending-cancel")

        transition_order_status(order=order, new_status=OrderStatus.CANCELLED, force=True)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)

    def test_refund_from_delivered_restocks(self) -> None:
        self.product.stock_quantity = 8
        self.product.save(update_fields=["stock_quantity"])
        order = self._make_order(status=OrderStatus.DELIVERED, suffix="delivered-refund")

        transition_order_status(order=order, new_status=OrderStatus.REFUNDED, force=True)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)

    def test_refund_after_cancel_does_not_double_restock(self) -> None:
        self.product.stock_quantity = 8
        self.product.save(update_fields=["stock_quantity"])
        order = self._make_order(status=OrderStatus.PLACED_COD, suffix="cancel-then-refund")

        transition_order_status(order=order, new_status=OrderStatus.CANCELLED, force=True)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)

        transition_order_status(order=order, new_status=OrderStatus.REFUNDED, force=True)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
