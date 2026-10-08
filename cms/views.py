"""HTTP views for the cms app; thin request parsing delegating to selectors/services."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from cms.selectors import get_active_homepage_sections
from cms.services import get_section_render_context
from core import meta_pixel
from core.seo import seo_context
from core.services import get_site_settings


@require_GET
def homepage_view(request: HttpRequest) -> HttpResponse:
    """Render the CMS-driven homepage with zero DB reads for section config."""
    sections = get_active_homepage_sections()
    section_contexts = [
        {
            "section_type": section["section_type"],
            "partial": f"cms/sections/{section['section_type']}.html",
            "context": get_section_render_context(section=section),
        }
        for section in sections
    ]
    site = get_site_settings()
    context = seo_context(
        request=request,
        title=site.tagline or site.site_name,
        description=site.tagline or site.site_name,
    )
    context["section_contexts"] = section_contexts
    context["mpx_events"] = [meta_pixel.event("ViewHome", custom=True)]
    response = render(request, "cms/homepage.html", context)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response
