"""Read-only query functions for the marketing app."""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from marketing.models import FlashSale


def get_active_flash_sale_price(
    *, product_id: int, base_price: Decimal
) -> dict[str, Decimal | bool]:
    """
    Return flash-sale-adjusted price for a product if a sale is active now.

    Catalog PLP/PDP selectors call this — discount logic lives here exclusively.
    """
    discounts = get_flash_sale_discounts_for_products(
        product_prices={product_id: base_price},
    )
    discount_pct = discounts.get(product_id)
    if discount_pct is None:
        return {"price": base_price, "is_flash_sale": False, "discount_percentage": Decimal("0")}

    discount = (base_price * discount_pct / Decimal("100")).quantize(Decimal("0.01"))
    return {
        "price": base_price - discount,
        "is_flash_sale": True,
        "discount_percentage": discount_pct,
        "original_price": base_price,
    }


def get_flash_sale_discounts_for_products(
    *,
    product_prices: dict[int, Decimal],
) -> dict[int, Decimal]:
    """
    Return the highest active flash-sale discount percentage per product id.

    Used by PLP to resolve display prices in a single flash-sale query.
    """
    if not product_prices:
        return {}

    now = timezone.now()
    product_ids = list(product_prices.keys())
    rows = (
        FlashSale.objects.filter(
            is_active=True,
            starts_at__lte=now,
            ends_at__gte=now,
            products__id__in=product_ids,
        )
        .values("products__id", "discount_percentage")
        .order_by("products__id", "-discount_percentage")
    )
    best: dict[int, Decimal] = {}
    for row in rows:
        product_id = row["products__id"]
        if product_id not in best:
            best[product_id] = row["discount_percentage"]
    return best


def get_active_flash_sales() -> list[FlashSale]:
    """Return currently active flash sales. Query guarantee: 1 SELECT."""
    now = timezone.now()
    return list(
        FlashSale.objects.filter(
            is_active=True,
            starts_at__lte=now,
            ends_at__gte=now,
        ).prefetch_related("products")
    )

def has_any_active_coupons() -> bool:
    """Return True if there is at least one currently active coupon."""
    from django.db.models import Q
    from marketing.models import Coupon
    now = timezone.now()
    return Coupon.objects.filter(
        is_active=True
    ).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=now)
    ).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=now)
    ).exists()
