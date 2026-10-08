"""Data layer for the delivery app — models only, no business logic."""

from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel


class Country(TimeStampedModel):
    """Country used to group deliverable cities."""

    name = models.CharField(max_length=120, verbose_name="Country name")
    code = models.CharField(
        max_length=2,
        unique=True,
        db_index=True,
        verbose_name="ISO country code",
        help_text="Two-letter ISO code, e.g. QA.",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Is active")

    class Meta:
        verbose_name = "Country"
        verbose_name_plural = "Countries"
        indexes = [
            models.Index(fields=["is_active"], name="delivery_country_active_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class City(TimeStampedModel):
    """Deliverable city used for address validation and delivery zone routing."""

    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="cities",
        verbose_name="Country",
    )
    name = models.CharField(
        max_length=120,
        verbose_name="City name",
        help_text="Display name of the city, e.g. Doha.",
    )
    slug = models.SlugField(
        max_length=120,
        unique=True,
        db_index=True,
        verbose_name="Slug",
        help_text="URL-friendly identifier for this city.",
    )
    delivery_charge_base = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=25,
        verbose_name="Base delivery charge",
        help_text="Default delivery fee for this city in the store currency.",
    )
    same_day_cutoff_hour = models.PositiveSmallIntegerField(
        default=14,
        verbose_name="Same-day cutoff hour",
        help_text="Local hour (0–23) after which same-day delivery slots are hidden.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Is active",
        help_text="When False, this city is hidden from customer address forms.",
    )

    class Meta:
        verbose_name = "City"
        verbose_name_plural = "Cities"
        indexes = [
            models.Index(fields=["is_active"], name="delivery_city_is_active_idx"),
            models.Index(fields=["country", "is_active"], name="delivery_city_country_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class DeliveryZone(TimeStampedModel):
    """
    Service area within a city.

    Uses a simple radius-from-center or postcode list — no PostGIS dependency.
    """

    city = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        related_name="zones",
        verbose_name="City",
    )
    name = models.CharField(max_length=120, verbose_name="Zone name")
    center_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Center latitude",
    )
    center_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Center longitude",
    )
    radius_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Radius (km)",
        help_text="Used when postcodes list is empty.",
    )
    postcodes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Served postcodes",
        help_text="List of postcode strings served by this zone.",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Is active")

    class Meta:
        verbose_name = "Delivery zone"
        verbose_name_plural = "Delivery zones"
        indexes = [
            models.Index(fields=["city", "is_active"], name="delivery_zone_city_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.city.name} — {self.name}"



