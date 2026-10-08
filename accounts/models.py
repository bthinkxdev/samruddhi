"""Data layer for the accounts app — models only, no business logic."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class OTPPurpose(models.TextChoices):
    """Allowed purposes for a one-time password request."""

    LOGIN = "login", "Login"
    SIGNUP = "signup", "Sign Up"
    PASSWORD_RESET = "password_reset", "Password Reset"



class CustomerProfile(TimeStampedModel):
    """Extended profile for a registered retail customer."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
        verbose_name="User",
        help_text="Linked Django auth user.",
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
        verbose_name="Phone number",
        help_text="Customer mobile number used for OTP login.",
    )
    phone_verified = models.BooleanField(
        default=False,
        verbose_name="Phone verified",
        help_text="True after a successful OTP verification for this phone.",
    )
    preferred_language = models.CharField(
        max_length=5,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        verbose_name="Preferred language",
        help_text="Customer's preferred storefront language.",
    )
    preferred_currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="customer_profiles",
        verbose_name="Preferred currency",
        help_text="Currency used to display prices for this customer.",
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date of birth",
        help_text="Optional date of birth for personalization.",
    )
    default_address = models.ForeignKey(
        "accounts.Address",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Default address",
        help_text="Customer's primary delivery address.",
    )
    notify_via_email = models.BooleanField(
        default=True,
        verbose_name="Email notifications",
        help_text="Receive order updates via email.",
    )
    notify_via_sms = models.BooleanField(
        default=False,
        verbose_name="SMS notifications",
        help_text="Receive order updates via SMS.",
    )
    notify_via_whatsapp = models.BooleanField(
        default=False,
        verbose_name="WhatsApp notifications",
        help_text="Receive order updates via WhatsApp.",
    )

    class Meta:
        verbose_name = "Customer profile"
        verbose_name_plural = "Customer profiles"
        indexes = [
            models.Index(fields=["phone"], name="accounts_profile_phone_idx"),
        ]

    def __str__(self) -> str:
        return self.user.get_full_name() or self.user.email or str(self.pk)

    @property
    def get_customer_type_label(self) -> str:
        return "Retail"

    @property
    def get_phone(self) -> str:
        return self.phone or ""


class Address(TimeStampedModel):
    """Saved delivery address belonging to a customer profile."""

    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name="Customer profile",
        help_text="Owner of this address.",
    )
    label = models.CharField(
        max_length=50,
        verbose_name="Label",
        help_text="Short label, e.g. Home or Office.",
    )
    line1 = models.CharField(
        max_length=255,
        verbose_name="Address line 1",
        help_text="Street address or building name.",
    )
    line2 = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Address line 2",
        help_text="Apartment, floor, or additional directions.",
    )
    city = models.CharField(
        max_length=120,
        verbose_name="City",
        help_text="Deliverable city for this address.",
    )
    state = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="State / Province",
    )
    pincode = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="PIN / Postal code",
        help_text="6-digit PIN code for shipping.",
    )
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Is default",
        help_text="When True, this is the customer's primary delivery address.",
    )

    class Meta:
        verbose_name = "Address"
        verbose_name_plural = "Addresses"
        indexes = [
            models.Index(
                fields=["customer_profile", "is_default"],
                name="accounts_address_default_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["customer_profile"],
                condition=models.Q(is_default=True),
                name="accounts_one_default_address_per_customer",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.label}: {self.line1}"


class SavedPaymentMethod(TimeStampedModel):
    """Tokenized payment method — never stores raw card data."""

    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="saved_payment_methods",
        verbose_name="Customer profile",
        help_text="Owner of this saved payment method.",
    )
    gateway_token = models.CharField(
        max_length=255,
        verbose_name="Gateway token",
        help_text="Opaque token returned by the payment gateway.",
    )
    card_brand = models.CharField(
        max_length=30,
        verbose_name="Card brand",
        help_text="Card network, e.g. Visa or Mastercard.",
    )
    last4 = models.CharField(
        max_length=4,
        verbose_name="Last four digits",
        help_text="Last four digits of the card number for display.",
    )
    expiry_month = models.PositiveSmallIntegerField(
        verbose_name="Expiry month",
        help_text="Card expiry month (1–12).",
    )
    expiry_year = models.PositiveSmallIntegerField(
        verbose_name="Expiry year",
        help_text="Card expiry four-digit year.",
    )
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Is default",
        help_text="When True, this card is pre-selected at checkout.",
    )

    class Meta:
        verbose_name = "Saved payment method"
        verbose_name_plural = "Saved payment methods"
        constraints = [
            models.UniqueConstraint(
                fields=["customer_profile"],
                condition=models.Q(is_default=True),
                name="accounts_one_default_payment_per_customer",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.card_brand} •••• {self.last4}"



class OTPRequest(TimeStampedModel):
    """Hashed one-time password issued for phone-based authentication."""

    phone = models.CharField(
        max_length=20,
        db_index=True,
        verbose_name="Phone number",
        help_text="Phone number the OTP was sent to.",
    )
    otp_hash = models.CharField(
        max_length=128,
        verbose_name="OTP hash",
        help_text="Hashed OTP value — plaintext is never stored.",
    )
    purpose = models.CharField(
        max_length=20,
        choices=OTPPurpose.choices,
        db_index=True,
        verbose_name="Purpose",
        help_text="Reason this OTP was issued.",
    )
    expires_at = models.DateTimeField(
        db_index=True,
        verbose_name="Expires at",
        help_text="Timestamp after which this OTP is invalid.",
    )
    is_used = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Is used",
        help_text="True once the OTP has been successfully verified.",
    )
    attempt_count = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Attempt count",
        help_text="Number of failed verification attempts.",
    )

    class Meta:
        verbose_name = "OTP request"
        verbose_name_plural = "OTP requests"
        indexes = [
            models.Index(
                fields=["phone", "purpose", "is_used"],
                name="accounts_otp_phone_purpose_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"OTP {self.purpose} for {self.phone}"


class SubscriptionStatus(models.TextChoices):
    """Customer-facing subscription lifecycle (mirrors recurring schedule)."""

    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    CANCELLED = "cancelled", "Cancelled"


class Subscription(TimeStampedModel):
    """Customer product subscription, e.g. weekly flowers."""

    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="subscriptions",
        verbose_name="Customer profile",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="subscriptions",
        verbose_name="Product",
    )
    recurring_schedule = models.OneToOneField(
        "recurring.RecurringSchedule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription",
        verbose_name="Recurring schedule",
    )
    delivery_address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        related_name="subscriptions",
        verbose_name="Delivery address",
    )
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
        db_index=True,
        verbose_name="Status",
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Quantity")

    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"
        indexes = [
            models.Index(fields=["customer_profile", "status"], name="acct_sub_customer_idx"),
        ]

    def __str__(self) -> str:
        return f"Subscription #{self.pk} — {self.product.name}"


class Wishlist(TimeStampedModel):
    """Persistent wishlist for a customer or guest session."""

    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="wishlists",
        verbose_name="Customer profile",
    )
    session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Session key",
    )
    share_token = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        verbose_name="Share token",
        help_text="Signed token for read-only shared access.",
    )

    class Meta:
        verbose_name = "Wishlist"
        verbose_name_plural = "Wishlists"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(customer_profile__isnull=False, session_key__isnull=True)
                    | models.Q(customer_profile__isnull=True, session_key__isnull=False)
                ),
                name="wishlist_owner_xor",
            ),
        ]

    def __str__(self) -> str:
        owner = self.customer_profile_id or self.session_key
        return f"Wishlist #{self.pk} ({owner})"


class WishlistItem(TimeStampedModel):
    """Product saved on a wishlist."""

    wishlist = models.ForeignKey(
        Wishlist,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Wishlist",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        verbose_name="Product",
    )

    class Meta:
        verbose_name = "Wishlist item"
        verbose_name_plural = "Wishlist items"
        constraints = [
            models.UniqueConstraint(fields=["wishlist", "product"], name="wishlist_item_unique"),
        ]

    def __str__(self) -> str:
        return f"Wishlist item {self.product_id}"



class EmailOTPRequest(TimeStampedModel):
    """Hashed one-time password issued for email-based passwordless authentication."""

    email = models.EmailField(db_index=True, verbose_name="Email address")
    otp_hash = models.CharField(max_length=128, verbose_name="OTP hash")
    purpose = models.CharField(
        max_length=20,
        choices=OTPPurpose.choices,
        db_index=True,
        verbose_name="Purpose",
    )
    expires_at = models.DateTimeField(db_index=True, verbose_name="Expires at")
    is_used = models.BooleanField(default=False, db_index=True, verbose_name="Is used")
    attempt_count = models.PositiveSmallIntegerField(default=0, verbose_name="Attempt count")

    class Meta:
        verbose_name = "Email OTP request"
        verbose_name_plural = "Email OTP requests"
        indexes = [
            models.Index(fields=["email", "purpose", "is_used"], name="acct_email_otp_idx"),
        ]

    def __str__(self) -> str:
        return f"Email OTP {self.purpose} for {self.email}"

