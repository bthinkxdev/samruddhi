"""Write operations and business rules for the cms app."""

from __future__ import annotations

from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.db.models import Max

from cms.models import HomepageSection
from cms.selectors import HOMEPAGE_SECTIONS_CACHE_KEY, HOMEPAGE_SECTIONS_CACHE_TTL


def build_homepage_sections_snapshot() -> list[dict[str, Any]]:
    """
    Build a serializable snapshot of active homepage sections from the database.

    Query guarantee: exactly 1 SELECT on cms_homepagesection ordered by display_order.
    Returns:
        List of section dicts safe for Redis JSON serialization.
    """
    return [
        {
            "id": section.pk,
            "section_type": section.section_type,
            "title": section.title,
            "display_order": section.display_order,
            "config": section.config or {},
        }
        for section in HomepageSection.objects.filter(is_active=True).order_by(
            "display_order", "id"
        )
    ]


def refresh_homepage_cache() -> int:
    """
    Rebuild and store the homepage sections Redis snapshot.

    Returns:
        Number of sections written to cache.
    """
    snapshot = build_homepage_sections_snapshot()
    try:
        cache.set(HOMEPAGE_SECTIONS_CACHE_KEY, snapshot, timeout=HOMEPAGE_SECTIONS_CACHE_TTL)
    except Exception:
        pass
    return len(snapshot)


def next_homepage_section_order() -> int:
    """Display order that places a new section after every existing one."""
    last = HomepageSection.objects.aggregate(last=Max("display_order"))["last"]
    return 0 if last is None else last + 1


@transaction.atomic
def reorder_homepage_sections(*, ordered_ids: list[int]) -> None:
    """
    Persist a drag-and-drop arrangement of the homepage sections.

    ``ordered_ids`` must list every existing section exactly once, so a stale
    page (sections added/removed elsewhere) is rejected instead of half-applied.

    Raises:
        ValueError: ids are duplicated or do not match the current sections.
    """
    sections = {s.pk: s for s in HomepageSection.objects.select_for_update()}
    if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != set(sections):
        raise ValueError("Section list is out of date; reload the page and try again.")
    for position, section_id in enumerate(ordered_ids):
        sections[section_id].display_order = position
    HomepageSection.objects.bulk_update(sections.values(), ["display_order"])
    refresh_homepage_cache()


def get_section_render_context(*, section: dict[str, Any]) -> dict[str, Any]:
    """
    Build template context for a homepage section by dispatching to catalog selectors.

    Params:
        section: Serialized section dict from get_active_homepage_sections().
    Returns:
        Context dict passed to cms/sections/<section_type>.html partials.
    """
    from cms.section_context import build_section_context

    return build_section_context(section=section)
