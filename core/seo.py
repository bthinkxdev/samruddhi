"""SEO helpers — meta tags, canonical URLs, hreflang, and JSON-LD."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.conf import settings
from django.http import HttpRequest
from django.urls import translate_url
from django.utils.translation import get_language


def resolve_meta_title(*, obj: Any, fallback: str) -> str:
    """Return meta_title from an SEOModel-capable object or fallback."""
    title = (getattr(obj, "meta_title", None) or "").strip()
    return (title or fallback)[:70]


def resolve_meta_description(*, obj: Any, fallback: str) -> str:
    """Return meta_description from an SEOModel-capable object or fallback."""
    description = (getattr(obj, "meta_description", None) or "").strip()
    return (description or fallback)[:160]


def resolve_og_image_url(*, obj: Any, request: HttpRequest) -> str:
    """
    Return absolute OG image URL from an object.

    Priority: object's own `og_image`, then a collection's `banner_image`, then
    (for products) the first gallery image, else empty string.
    """
    for field in ("og_image", "banner_image"):
        image = getattr(obj, field, None)
        if image and getattr(image, "url", None):
            return request.build_absolute_uri(image.url)

    images = getattr(obj, "image_list", None) or getattr(obj, "images", None)
    if images:
        first = images[0] if isinstance(images, list) else images.first()
        if first and getattr(first, "image", None):
            return request.build_absolute_uri(first.image.url)

    return ""


def resolve_default_og_image_url(*, request: HttpRequest) -> str:
    """Absolute URL of the default OG image: settings OG image, then logo, then bundled fallback."""
    from django.templatetags.static import static

    from core.services import get_site_settings

    site = get_site_settings()
    for image in (site.og_image, site.logo):
        if image:
            return request.build_absolute_uri(image.url)
    return request.build_absolute_uri(static("dashboard/images/og-default.png"))


def build_hreflang_urls(*, request: HttpRequest) -> list[dict[str, str]]:
    """
    Build EN/AR alternate URLs for the current path.

    Uses Django's translate_url to swap locale prefix without duplicating routes.
    """
    alternates: list[dict[str, str]] = []
    current_path = request.get_full_path()
    for lang_code, _label in settings.LANGUAGES:
        localized = translate_url(current_path, lang_code)
        alternates.append(
            {
                "lang_code": lang_code,
                "url": request.build_absolute_uri(localized),
            }
        )
    alternates.append(
        {
            "lang_code": "x-default",
            "url": request.build_absolute_uri(translate_url(current_path, settings.LANGUAGE_CODE)),
        }
    )
    return alternates


def build_plp_canonical_url(
    *,
    request: HttpRequest,
    collection_slug: str | None = None,
) -> str:
    """
    Canonical URL for PLP — filtered query params canonicalize to collection or shop root.

    Prevents duplicate-content penalties from sort/filter query strings.
    """
    from django.urls import reverse

    if collection_slug:
        path = reverse("catalog:plp-collection", kwargs={"collection_slug": collection_slug})
    else:
        path = reverse("catalog:plp")
    return request.build_absolute_uri(path)


def build_product_json_ld(
    *,
    product: Any,
    price: Decimal | str,
    request: HttpRequest,
    average_rating: Optional[float] = None,
    review_count: int = 0,
) -> dict[str, Any]:
    """
    Build schema.org Product JSON-LD for Google Rich Results.

    Includes Offer (price/availability) and AggregateRating when reviews exist.
    """
    from django.urls import reverse
    from core.selectors import get_default_currency

    currency = get_default_currency()
    currency_code = currency.code if currency else ""

    availability = (
        "https://schema.org/InStock" if product.is_in_stock else "https://schema.org/OutOfStock"
    )
    image_url = ""
    images = getattr(product, "image_list", None) or getattr(product, "images", None)
    if images:
        first = images[0] if isinstance(images, list) else images.first()
        if first and getattr(first, "image", None):
            image_url = request.build_absolute_uri(first.image.url)

    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "sku": product.sku,
        "url": request.build_absolute_uri(reverse("catalog:pdp", kwargs={"slug": product.slug})),
        "offers": {
            "@type": "Offer",
            "priceCurrency": currency_code,
            "price": str(price),
            "availability": availability,
            "url": request.build_absolute_uri(
                reverse("catalog:pdp", kwargs={"slug": product.slug})
            ),
        },
    }
    if image_url:
        data["image"] = image_url

    description = resolve_meta_description(obj=product, fallback=product.name)
    if description:
        data["description"] = description

    if review_count > 0 and average_rating is not None:
        data["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": round(float(average_rating), 1),
            "reviewCount": review_count,
        }

    return data


def seo_context(
    *,
    request: HttpRequest,
    obj: Any | None = None,
    title: str,
    description: str,
    canonical_url: str | None = None,
) -> dict[str, Any]:
    """
    Assemble standard SEO template context for any page.

    ``title`` is the bare page title; the brand name from SiteSettings is appended
    here so no view hard-codes it. An object's own ``meta_title`` still wins.
    """
    from core.services import get_site_settings

    site_name = get_site_settings().site_name
    if title and title != site_name:
        title = f"{title} | {site_name}"
    if obj is not None:
        title = resolve_meta_title(obj=obj, fallback=title)
        description = resolve_meta_description(obj=obj, fallback=description)

    canonical = canonical_url or request.build_absolute_uri(request.path)

    og_image = resolve_og_image_url(obj=obj, request=request) if obj is not None else ""
    og_image_width = og_image_height = None
    if not og_image:
        og_image = resolve_default_og_image_url(request=request)
        og_image_width, og_image_height = 1200, 630

    return {
        "seo_title": title,
        "seo_description": description,
        "seo_canonical_url": canonical,
        "seo_og_image": og_image,
        "seo_og_image_width": og_image_width,
        "seo_og_image_height": og_image_height,
        "seo_hreflang_urls": build_hreflang_urls(request=request),
        "seo_lang": get_language() or settings.LANGUAGE_CODE,
    }
