"""Read-only query functions for the cms app; views must not call the ORM directly."""

from __future__ import annotations

from typing import Any

from django.core.cache import cache

HOMEPAGE_SECTIONS_CACHE_KEY = "cms:homepage_sections:active:v1"
HOMEPAGE_SECTIONS_CACHE_TTL = 300


def get_active_homepage_sections() -> list[dict[str, Any]]:
    """
    Return ordered active homepage sections from the Redis-cached snapshot.

    Query guarantee: 0 DB queries on cache hit. On cache miss the Celery task
    `cms.tasks.refresh_homepage_cache` repopulates the snapshot (1 SELECT).

    Cache key: cms:homepage_sections:active:v1
    TTL: 300 seconds (HOMEPAGE_SECTIONS_CACHE_TTL)

    Returns:
        List of section dicts with keys: id, section_type, title, display_order, config.
    """
    cached = cache.get(HOMEPAGE_SECTIONS_CACHE_KEY)
    if cached is not None:
        return cached

    from cms.services import build_homepage_sections_snapshot

    snapshot = build_homepage_sections_snapshot()
    try:
        cache.set(HOMEPAGE_SECTIONS_CACHE_KEY, snapshot, timeout=HOMEPAGE_SECTIONS_CACHE_TTL)
    except Exception:
        pass
    return snapshot


def get_hero_slides() -> list[dict[str, Any]]:
    """
    Return active hero slides (uploaded photos/videos) ordered for display.

    Query guarantee: exactly 1 SELECT on cms_heroslide.

    Returns:
        List of slide dicts with keys: type, src, poster, title.
        Slides without any media file are skipped.
    """
    from cms.models import HeroSlide

    slides: list[dict[str, Any]] = []
    for slide in HeroSlide.objects.filter(is_active=True).order_by("display_order", "id"):
        src = slide.media_src
        if not src:
            continue
        slides.append(
            {
                "type": slide.media_type,
                "src": src,
                "poster": slide.poster_src,
                "title": slide.title,
            }
        )
    return slides
