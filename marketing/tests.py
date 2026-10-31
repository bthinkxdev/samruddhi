"""Tests for coupon validation, redemption limits and flash-sale form rules."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.services import register_customer_email
from cart.models import Cart
from catalog.models import Collection
from core.models import Currency
from marketing.exceptions import InvalidCouponError
from marketing.models import Coupon, CouponDiscountType, CouponRedemption
from marketing.services import record_coupon_redemption, validate_coupon_for_cart
from orders.models import Order, OrderStatus


def _validate(code="SAVE", subtotal="1000.00", lines=None, **kwargs):
    return validate_coupon_for_cart(
        code=code,
        cart_subtotal=Decimal(subtotal),
        cart_lines=lines if lines is not None else [(Decimal(subtotal), set())],
        **kwargs,
    )


class CouponValidationTests(TestCase):
    def test_percentage_discount(self) -> None:
        Coupon.objects.create(code="SAVE", discount_value="10")
        self.assertEqual(_validate()["discount_amount"], Decimal("100.00"))

    def test_fixed_discount_is_capped_at_subtotal(self) -> None:
        Coupon.objects.create(code="SAVE", discount_type=CouponDiscountType.FIXED, discount_value="5000")
        self.assertEqual(_validate()["discount_amount"], Decimal("1000.00"))

    def test_collection_scope_discounts_only_eligible_lines(self) -> None:
        scoped = Collection.objects.create(name="A", slug="a")
        other = Collection.objects.create(name="B", slug="b")
        coupon = Coupon.objects.create(code="SAVE", discount_value="10")
        coupon.applicable_collections.add(scoped)
        lines = [(Decimal("400.00"), {scoped.pk}), (Decimal("600.00"), {other.pk})]
        self.assertEqual(_validate(lines=lines)["discount_amount"], Decimal("40.00"))

    def test_collection_scope_rejects_cart_without_eligible_lines(self) -> None:
        scoped = Collection.objects.create(name="A", slug="a")
        coupon = Coupon.objects.create(code="SAVE", discount_value="10")
        coupon.applicable_collections.add(scoped)
        with self.assertRaises(InvalidCouponError):
            _validate(lines=[(Decimal("1000.00"), set())])

    def test_expired_coupon_rejected(self) -> None:
        Coupon.objects.create(
            code="SAVE", discount_value="10", valid_until=timezone.now() - timedelta(days=1)
        )
        with self.assertRaises(InvalidCouponError):
            _validate()


class CouponRedemptionLimitTests(TestCase):
    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.coupon = Coupon.objects.create(code="SAVE", discount_value="10", max_uses=1)
        self.profile = register_customer_email(
            email="limit@example.com", password="testpass12345", name="Limit"
        )

    def _order(self, status=OrderStatus.PLACED_COD) -> Order:
        cart = Cart.objects.create(currency=self.currency, session_key=f"s{Cart.objects.count()}")
        return Order.objects.create(
            cart=cart,
            order_number=f"ORD-{Order.objects.count()}",
            idempotency_key=f"key-{Order.objects.count()}",
            order_status=status,
            subtotal="1000.00",
            total_amount="900.00",
            currency=self.currency,
        )

    def _redeem(self, order: Order, profile_id=None) -> CouponRedemption:
        return record_coupon_redemption(
            code="SAVE", customer_profile_id=profile_id, order_id=order.pk, cart_id=order.cart_id
        )

    def test_guest_redemption_counts_toward_max_uses(self) -> None:
        self._redeem(self._order())
        with self.assertRaises(InvalidCouponError):
            _validate()

    def test_redemption_blocked_once_limit_reached(self) -> None:
        self._redeem(self._order())
        with self.assertRaises(InvalidCouponError):
            self._redeem(self._order())

    def test_cancelled_order_releases_use(self) -> None:
        order = self._order()
        self._redeem(order)
        Order.objects.filter(pk=order.pk).update(order_status=OrderStatus.CANCELLED)
        self.assertEqual(_validate()["discount_amount"], Decimal("100.00"))

    def test_stale_unpaid_order_releases_use(self) -> None:
        order = self._order(OrderStatus.CHECKOUT_PENDING)
        self._redeem(order)
        with self.assertRaises(InvalidCouponError):
            _validate()
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(_validate()["discount_amount"], Decimal("100.00"))

    def test_own_pending_order_does_not_block_its_cart(self) -> None:
        order = self._order(OrderStatus.CHECKOUT_PENDING)
        self._redeem(order)
        result = _validate(cart_id=order.cart_id)
        self.assertEqual(result["discount_amount"], Decimal("100.00"))

    def test_per_customer_limit(self) -> None:
        Coupon.objects.filter(pk=self.coupon.pk).update(max_uses=None, max_uses_per_customer=1)
        self._redeem(self._order(), self.profile.pk)
        with self.assertRaises(InvalidCouponError):
            _validate(customer_profile_id=self.profile.pk)
