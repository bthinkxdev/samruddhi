"""Abstract base model mixins and shared core domain models for config."""

from __future__ import annotations

from typing import Any

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Abstract mixin adding indexed created_at / updated_at audit columns."""

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Created at",
        help_text="Timestamp when this record was first created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_index=True,
        verbose_name="Updated at",
        help_text="Timestamp when this record was last modified.",
    )

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that performs soft deletes by flagging rows instead of removing them."""

    def delete(self) -> tuple[int, dict[str, int]]:
        """Soft-delete all rows in this queryset."""
        count = self.update(is_deleted=True, deleted_at=timezone.now())
        return count, {self.model._meta.label: count}

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        """Permanently remove rows from the database."""
        return super().delete()


class SoftDeleteManager(models.Manager):
    """Manager excluding soft-deleted rows; exposes all_with_deleted()."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        """Return only active (non-deleted) rows."""
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)

    def all_with_deleted(self) -> SoftDeleteQuerySet:
        """Return all rows including soft-deleted ones."""
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    """Abstract mixin adding soft-delete flags and a filtering manager."""

    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Is deleted",
        help_text="When True, this record is hidden from default queries.",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Deleted at",
        help_text="Timestamp when this record was soft-deleted.",
    )

    objects = SoftDeleteManager()

    class Meta:
        abstract = True

    def delete(
        self,
        using: str | None = None,
        keep_parents: bool = False,
    ) -> tuple[int, dict[str, int]]:
        """Soft-delete this instance."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        update_fields = ["is_deleted", "deleted_at"]
        if any(field.name == "updated_at" for field in self._meta.fields):
            update_fields.append("updated_at")
        self.save(update_fields=update_fields)
        return 1, {self._meta.label: 1}

    def hard_delete(
        self,
        using: str | None = None,
        keep_parents: bool = False,
    ) -> tuple[int, dict[str, int]]:
        """Permanently remove this instance from the database."""
        return super().delete(using=using, keep_parents=keep_parents)


class SEOModel(models.Model):
    """Abstract mixin for SEO metadata and a reusable slug field factory."""

    meta_title = models.CharField(
        max_length=70,
        blank=True,
        verbose_name="Meta title",
        help_text="HTML <title> tag content (max ~70 characters).",
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="Meta description",
        help_text="HTML meta description for search engines (max ~160 characters).",
    )
    og_image = models.ImageField(
        upload_to="seo/og/",
        blank=True,
        null=True,
        verbose_name="Open Graph image",
        help_text="Image used when this content is shared on social media.",
    )

    class Meta:
        abstract = True

    @staticmethod
    def slug_field(**kwargs: Any) -> models.SlugField:
        """
        Return a pre-configured SlugField for SEO-friendly URLs.

        Pass extra kwargs to override defaults (e.g. unique=False for drafts).
        """
        defaults: dict[str, Any] = {
            "max_length": 255,
            "unique": True,
            "db_index": True,
            "verbose_name": "Slug",
            "help_text": "URL-friendly identifier used in public-facing paths.",
        }
        defaults.update(kwargs)
        return models.SlugField(**defaults)


class State(TimeStampedModel):
    """Stores a list of states/provinces for checkout dropdown."""
    
    name = models.CharField(max_length=255, unique=True, verbose_name="State Name")
    is_active = models.BooleanField(default=True, help_text="Is this state active for delivery?")

    class Meta:
        verbose_name = "State"
        verbose_name_plural = "States"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

class Currency(TimeStampedModel):
    """Supported storefront currency with exchange rate relative to the base unit."""

    code = models.CharField(
        max_length=3,
        unique=True,
        db_index=True,
        verbose_name="Currency code",
        help_text="ISO 4217 currency code, e.g. QAR or USD.",
    )
    symbol = models.CharField(
        max_length=8,
        verbose_name="Symbol",
        help_text="Display symbol shown alongside prices, e.g. ر.ق or $.",
    )
    exchange_rate_to_base = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        verbose_name="Exchange rate to base",
        help_text="Multiplier to convert this currency into the platform base currency.",
    )
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Is default",
        help_text="When True, this currency is the storefront default.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Is active",
        help_text="When False, this currency is hidden/inactive on the storefront.",
    )

    class Meta:
        verbose_name = "Currency"
        verbose_name_plural = "Currencies"
        indexes = [
            models.Index(fields=["is_default"], name="core_currency_is_default_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.symbol})"


class SiteSettings(TimeStampedModel):
    """
    Singleton site configuration (fixed pk=1 via core.services.get_site_settings).

    Secret payment keys stay in environment variables — only public key names
    and template slugs are stored here.
    """

    site_name = models.CharField(max_length=120, default="Samruddhi")
    tagline = models.CharField(
        max_length=160,
        blank=True,
        help_text="Short line shown in the footer and used as the default page description.",
    )
    logo = models.ImageField(upload_to="site/", blank=True, null=True, verbose_name="Logo")
    favicon = models.ImageField(
        upload_to="site/",
        blank=True,
        null=True,
        help_text="Browser-tab icon. Falls back to the logo when empty.",
    )
    og_image = models.ImageField(
        upload_to="site/",
        blank=True,
        null=True,
        verbose_name="Social share image (OG)",
        help_text="Default image shown when pages are shared (recommended 1200x630). Falls back to the logo.",
    )
    contact_phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(
        blank=True,
        help_text="Store address shown in the footer / contact page. One line per row.",
    )
    primary_color = models.CharField(max_length=7, default="#0369A1")
    secondary_color = models.CharField(max_length=7, default="#0B1220")
    font_family = models.CharField(max_length=120, default="Inter, sans-serif")
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    whatsapp_number = models.CharField(max_length=20, blank=True)
    vendor_email = models.EmailField(
        blank=True,
        verbose_name="Vendor Email",
        help_text="Email address to receive quote requests and contact inquiries.",
    )
    order_notification_email = models.EmailField(
        blank=True,
        verbose_name="Order Notification Email",
        help_text="Email address to notify whenever a new order is placed. Leave blank to disable.",
    )
    default_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    default_language = models.CharField(max_length=5, default="en")
    tax_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cod_delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=50, verbose_name="COD Delivery Charge")
    card_gateway_public_key_env = models.CharField(
        max_length=80,
        default="CARD_GATEWAY_PUBLIC_KEY",
        help_text="Environment variable name for the card gateway public key.",
    )
    qatar_gateway_public_key_env = models.CharField(
        max_length=80,
        default="QATAR_GATEWAY_PUBLIC_KEY",
        blank=True,
    )
    order_email_template_slug = models.CharField(max_length=80, default="order-status")
    whatsapp_template_slug = models.CharField(max_length=80, default="order-whatsapp")
    razorpay_key_id = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Razorpay Key ID",
        help_text="Razorpay Key ID / Test Key ID for payment processing.",
    )
    razorpay_key_secret = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Razorpay Key Secret",
        help_text="Razorpay Key Secret / Test Key Secret for payment signature verification.",
    )

    meta_pixel_id = models.CharField(
        max_length=32,
        blank=True,
        verbose_name="Meta Pixel ID",
        help_text="Numeric Pixel / Dataset ID from Meta Events Manager. Leave blank to disable tracking (falls back to the META_PIXEL_ID env var).",
    )
    meta_capi_access_token = models.CharField(
        max_length=512,
        blank=True,
        verbose_name="Meta Conversions API access token",
        help_text="Enables server-side Purchase events. Falls back to the META_CAPI_ACCESS_TOKEN env var.",
    )

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self) -> str:
        return self.site_name

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> tuple[int, dict[str, int]]:
        raise RuntimeError("SiteSettings singleton cannot be deleted.")


class ContactInquiry(TimeStampedModel):
    """Stores contact form submissions and quote requests."""

    name = models.CharField(max_length=255, verbose_name="Name")
    email = models.EmailField(verbose_name="Email Address")
    message = models.TextField(verbose_name="Message")
    class Meta:
        verbose_name = "Contact Inquiry"
        verbose_name_plural = "Contact Inquiries"

    def __str__(self) -> str:
        return f"Inquiry from {self.name} ({self.email})"
