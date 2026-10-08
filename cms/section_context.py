"""Homepage section context builders — delegates to catalog selectors, never ORM."""

from __future__ import annotations

from typing import Any

from catalog.selectors import (
    get_featured_brands,
    get_homepage_collections,
    get_recent_approved_reviews,
    get_root_collections,
)
from cms.selectors import get_hero_slides


def build_section_context(*, section: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatch section_type to the appropriate data source.

    Every section pulls live catalog/cms config data — nothing is hardcoded in templates.
    """
    section_type = section["section_type"]
    config = section.get("config") or {}
    base = {
        "section": section,
        "title": section.get("title", ""),
        "config": config,
    }

    builders = {
        "hero_slider": _hero_slider,
        "shop_by_occasion": _empty,
        "shop_by_recipient": _empty,
        "shop_by_collection": _shop_by_collection,
        "featured_brands": _featured_brands,
        "corporate_gifts_banner": _empty,
        "subscription_banner": _banner,
        "marketing_features": _marketing_features,
        "reviews": _reviews,
        "instagram_gallery": _instagram,
        "newsletter": _newsletter,
        "collection_products": _collection_products,
    }
    builder = builders.get(section_type, _empty)
    base.update(builder(config))
    return base


def _collection_products(config: dict[str, Any]) -> dict[str, Any]:
    """One product grid per collection flagged "List on home page" in the dashboard."""
    return {"collection_sections": get_homepage_collections()}


def _hero_slider(config: dict[str, Any]) -> dict[str, Any]:
    """Prefer uploaded photo/video slides; fall back to legacy URL-based config."""
    slides = get_hero_slides()
    if slides:
        return {"slides": slides}

    legacy_slides = config.get("slides") or []
    fallback = [
        {
            "type": "image",
            "src": slide.get("image") or slide.get("src") or "",
            "poster": slide.get("poster") or "",
            "title": slide.get("title") or "",
        }
        for slide in legacy_slides
        if isinstance(slide, dict) and (slide.get("image") or slide.get("src"))
    ]
    return {"slides": fallback}


def _shop_by_occasion(config: dict[str, Any]) -> dict[str, Any]:
    return {}


def _shop_by_recipient(config: dict[str, Any]) -> dict[str, Any]:
    return {}


def _shop_by_collection(config: dict[str, Any]) -> dict[str, Any]:
    return {"collections": get_root_collections()}


def _featured_brands(config: dict[str, Any]) -> dict[str, Any]:
    brand_ids = config.get("brand_ids")
    return {"brands": get_featured_brands(brand_ids=brand_ids)}


def _banner(config: dict[str, Any]) -> dict[str, Any]:
    return {"banner": config}


def _marketing_features(config: dict[str, Any]) -> dict[str, Any]:
    return {"cards": config.get("cards", [])}


def _reviews(config: dict[str, Any]) -> dict[str, Any]:
    limit = config.get("limit", 6)
    return {"reviews": get_recent_approved_reviews(limit=limit)}


def _instagram(config: dict[str, Any]) -> dict[str, Any]:
    return {"images": config.get("images", [])}


def _newsletter(config: dict[str, Any]) -> dict[str, Any]:
    return {"placeholder": config.get("placeholder", "")}


def _empty(config: dict[str, Any]) -> dict[str, Any]:
    return {}
