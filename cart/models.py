"""Data layer for the cart app — models only, no business logic."""

from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel


class Cart(TimeStampedModel):
    """
    Persistent shopping cart for authenticated customers or guest sessions.

    Exactly one of ``customer_profile`` or ``session_key`` must be set.
    """

    customer_profile = models.ForeignKey(
        "accounts.CustomerProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="carts",
        verbose_name="Customer profile",
    )
    session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Session key",
        help_text="Django session key for guest carts.",
    )
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="carts",
        verbose_name="Currency",
    )
    coupon_code = models.CharField(max_length=40, blank=True, verbose_name="Coupon code")
    coupon_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Coupon discount",
    )
    delivery_charge = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Delivery charge",
    )

    class Meta:
        verbose_name = "Cart"
        verbose_name_plural = "Carts"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(customer_profile__isnull=False, session_key__isnull=True)
                    | models.Q(customer_profile__isnull=True, session_key__isnull=False)
                ),
                name="cart_owner_xor",
            ),
        ]
        indexes = [
            models.Index(fields=["session_key"], name="cart_session_key_idx"),
            models.Index(fields=["customer_profile"], name="cart_customer_idx"),
            models.Index(
                fields=["updated_at", "customer_profile"],
                name="cart_abandoned_scan_idx",
            ),
        ]

    def __str__(self) -> str:
        owner = self.customer_profile_id or self.session_key
        return f"Cart #{self.pk} ({owner})"


class CartItem(TimeStampedModel):
    """Line item in a cart with snapshotted unit price at add time."""

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Cart",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name="Product",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cart_items",
        verbose_name="Variant",
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Quantity")
    unit_price_at_add = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Unit price at add",
        help_text="Snapshotted price when the item entered the cart.",
    )

    class Meta:
        verbose_name = "Cart item"
        verbose_name_plural = "Cart items"
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product", "variant"],
                name="cart_item_unique_product_variant",
            ),
        ]
        indexes = [
            models.Index(fields=["cart"], name="cart_item_cart_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} x{self.quantity}"
