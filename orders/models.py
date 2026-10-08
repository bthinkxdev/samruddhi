"""Data layer for the orders app — models only, no business logic."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class OrderStatus(models.TextChoices):
    """
    Lifecycle states for a customer order.

    CONFIRMED is the single trigger for Delhivery AWB creation (see
    orders.services.transition_order_status) — no other status creates a shipment.

    PICKED_UP / IN_TRANSIT / OUT_FOR_DELIVERY / DELIVERED are webhook-only: admins
    cannot set them manually (see orders.services.ALLOWED_STATUS_TRANSITIONS and
    delhivery.views.delhivery_webhook, which is the only caller that reaches them).
    """

    CHECKOUT_PENDING = "checkout_pending", "Payment Pending"
    PLACED_COD = "placed_cod", "COD Awaiting Confirmation"
    CONFIRMED = "confirmed", "Confirmed"
    READY_TO_SHIP = "ready_to_ship", "Ready to Ship"
    PICKED_UP = "picked_up", "Picked Up"
    IN_TRANSIT = "in_transit", "In Transit"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"


class Order(TimeStampedModel):
    """
    Customer order header.

    ``idempotency_key`` guarantees place_order is safe under double-submit and
    concurrent requests — a duplicate key returns the existing order.
    """

    customer_profile = models.ForeignKey(
        "accounts.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="orders",
        null=True,
        blank=True,
        verbose_name="Customer profile",
        help_text="Owner of this order; null for guest checkout.",
    )
    cart = models.ForeignKey(
        "cart.Cart",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Source cart",
    )
    order_number = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        verbose_name="Order number",
        help_text="Human-readable unique order reference.",
    )
    idempotency_key = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Idempotency key",
        help_text="Client-supplied key preventing duplicate order creation.",
    )
    order_status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.CHECKOUT_PENDING,
        db_index=True,
        verbose_name="Order status",
    )
    delivery_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Delivery date",
        db_index=True,
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    coupon_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Total amount",
        help_text="Order total in the customer's checkout currency.",
    )
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Currency",
    )
    delivery_address_snapshot = models.JSONField(
        default=dict,
        verbose_name="Delivery address snapshot",
    )
    invoice_details = models.JSONField(default=dict, verbose_name="Invoice details")
    success_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Order success at",
        help_text=(
            "When this order first became a real sale: online payment confirmed, or "
            "COD order placed. Null for CHECKOUT_PENDING orders that never succeeded. "
            "Set once in orders.services.transition_order_status (CONFIRMED/PLACED_COD) "
            "and at direct COD creation in checkout.services.place_order — never "
            "touched again, unlike updated_at, so later unrelated changes (a courier "
            "scan, an address edit) can't move an order's position by accident."
        ),
    )

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        indexes = [
            models.Index(
                fields=["customer_profile", "-success_at"],
                name="ord_customer_success_idx",
            ),
            models.Index(fields=["order_status"], name="orders_order_status_idx"),
            models.Index(fields=["idempotency_key"], name="orders_idempotency_key_idx"),
        ]
        #success_at, not updated_at: updated_at is bumped by every unrelated save
        #(a courier scan, an address edit), so sorting listings by it makes orders
        #jump around for reasons that have nothing to do with the order actually
        #succeeding. success_at is set exactly once, at the moment the order becomes
        #a real sale, and never touched again. CHECKOUT_PENDING orders have no
        #success_at yet — nulls_last keeps them from flooding the top of any listing
        #that falls back to this default, and the -created_at tiebreaker gives them a
        #sane relative order among themselves.
        ordering = [models.F("success_at").desc(nulls_last=True), "-created_at"]

    def __str__(self) -> str:
        return self.order_number

    @property
    def is_guest_order(self) -> bool:
        """
        True if the order wasn't placed by a signed-in customer.

        Captured at checkout time (``checkout.services.place_order``, from
        ``request.user.is_authenticated``) into ``invoice_details["is_guest_checkout"]``
        — this is the only reliable signal. There's deliberately no
        ``has_usable_password()`` fallback: this site's primary customer login is
        passwordless email OTP (``accounts.services.login_or_create_customer_by_email``),
        which sets an unusable password on every account it creates — so that check
        would report EVERY customer as a guest, logged in or not. Orders placed
        before this flag existed have no reliable signal at all; they default to
        guest rather than guess.
        """
        if self.invoice_details and "is_guest_checkout" in self.invoice_details:
            return self.invoice_details["is_guest_checkout"]
        return True

    @property
    def customer_display_name(self) -> str:
        """
        Best-effort customer name for admin display.

        Registered customers show their account name; guests show the name they
        typed at checkout (captured in delivery_address_snapshot), since their
        auto-created CustomerProfile/User often has no real name on it.
        """
        if not self.is_guest_order:
            return str(self.customer_profile)
        snapshot_name = (self.delivery_address_snapshot or {}).get("name")
        if snapshot_name:
            return snapshot_name
        return str(self.customer_profile) if self.customer_profile_id else "Guest"

    @property
    def payment_method_display(self) -> str:
        """Get the human-readable payment method name from the latest transaction."""
        tx = self.payment_transactions.filter(status="success").last()
        if not tx:
            tx = self.payment_transactions.last()
        if not tx:
            return "Unknown"
        
        try:
            from payments.registry import get_payment_adapter
            adapter = get_payment_adapter(gateway_key=tx.gateway_key)
            return adapter.display_name
        except KeyError:
            return tx.gateway_key.replace("_", " ").title()

    @property
    def payment_status_display(self) -> str:
        """Get the human-readable payment status from the latest transaction."""
        tx = self.payment_transactions.filter(status="success").last()
        if not tx:
            tx = self.payment_transactions.last()
        if not tx:
            return "Unknown"
        return tx.get_status_display()

    @property
    def confirmed_at(self):
        """Get the date the order was last confirmed."""
        history = self.status_history.filter(to_status=OrderStatus.CONFIRMED).last()
        if history:
            return history.changed_at
        return None


class OrderItem(TimeStampedModel):
    """Immutable purchased line on an order."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Order",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name="Product",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
        verbose_name="Variant",
    )
    variant_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Variant name (snapshot)",
        help_text="Captured at purchase time so history survives a later variant edit/delete.",
    )
    variant_sku = models.CharField(
        max_length=96,
        blank=True,
        default="",
        verbose_name="Variant SKU (snapshot)",
    )
    quantity = models.PositiveIntegerField(verbose_name="Quantity")
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Unit price",
    )

    class Meta:
        verbose_name = "Order item"
        verbose_name_plural = "Order items"
        db_table = "orders_orderlineitem"
        indexes = [
            models.Index(fields=["order"], name="order_line_item_order_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} x{self.quantity}"


OrderLineItem = OrderItem


class OrderStatusHistory(TimeStampedModel):
    """Audit trail of order status transitions."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name="Order",
    )
    from_status = models.CharField(max_length=20, verbose_name="From status")
    to_status = models.CharField(max_length=20, verbose_name="To status")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_changes",
        verbose_name="Changed by",
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Changed at")
    note = models.TextField(blank=True, verbose_name="Note")

    class Meta:
        verbose_name = "Order status history"
        verbose_name_plural = "Order status history"
        ordering = ["changed_at"]
        indexes = [
            models.Index(fields=["order", "changed_at"], name="order_status_hist_order_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.order_id}: {self.from_status} → {self.to_status}"


class ProofOfDelivery(TimeStampedModel):
    """Proof captured when an order is delivered."""

    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="proof_of_delivery",
        verbose_name="Order",
    )
    photo_url = models.URLField(blank=True, verbose_name="Photo URL")
    signature_url = models.URLField(blank=True, verbose_name="Signature URL")
    delivered_at = models.DateTimeField(verbose_name="Delivered at")
    recipient_name = models.CharField(max_length=120, verbose_name="Recipient name")

    class Meta:
        verbose_name = "Proof of delivery"
        verbose_name_plural = "Proof of delivery"

    def __str__(self) -> str:
        return f"POD for {self.order.order_number}"
