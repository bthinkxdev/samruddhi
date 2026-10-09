"""CMS management: homepage sections, hero slides, blog, pages, FAQs, policies."""

from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from cms.models import BlogPost, FAQItem, HeroSlide, HomepageSection, Page, PolicyDocument
from cms.services import reorder_homepage_sections
from dashboard import forms
from dashboard.access import dashboard_required
from dashboard.views.base import (
    DashboardCreateView,
    DashboardDeleteView,
    DashboardListView,
    DashboardUpdateView,
)


class HomepageSectionListView(DashboardListView):
    """Every section on one page so it can be rearranged by drag and drop."""

    model = HomepageSection
    template_name = "dashboard/cms/homepagesection_list.html"
    nav_section = "homepage"
    url_basename = "homepagesection"
    singular_name = "Section"
    plural_name = "Homepage Sections"
    paginate_by = None


@dashboard_required
@require_POST
def homepage_section_reorder(request: HttpRequest) -> JsonResponse:
    """Apply the drag-and-drop order posted as ``{"order": [section ids...]}``."""
    try:
        payload = json.loads(request.body)
        ordered_ids = [int(pk) for pk in payload["order"]]
        reorder_homepage_sections(ordered_ids=ordered_ids)
    except (ValueError, KeyError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"ok": True})


class HomepageSectionCreateView(DashboardCreateView):
    model = HomepageSection
    form_class = forms.HomepageSectionForm
    nav_section = "homepage"
    url_basename = "homepagesection"
    singular_name = "Section"


class HomepageSectionUpdateView(DashboardUpdateView):
    model = HomepageSection
    form_class = forms.HomepageSectionForm
    nav_section = "homepage"
    url_basename = "homepagesection"
    singular_name = "Section"


class HomepageSectionDeleteView(DashboardDeleteView):
    model = HomepageSection
    nav_section = "homepage"
    url_basename = "homepagesection"
    singular_name = "Section"


class HeroSlideListView(DashboardListView):
    model = HeroSlide
    nav_section = "heroslides"
    url_basename = "heroslide"
    singular_name = "Hero Slide"
    plural_name = "Hero Slides"
    columns = [
        {"label": "Image", "name": "image", "type": "image"},
        {"label": "Title", "name": "title"},
        {"label": "Order", "name": "display_order"},
        {"label": "Active", "name": "is_active", "type": "bool"},
    ]


class HeroSlideCreateView(DashboardCreateView):
    model = HeroSlide
    form_class = forms.HeroSlideForm
    nav_section = "heroslides"
    url_basename = "heroslide"
    singular_name = "Hero Slide"


class HeroSlideUpdateView(DashboardUpdateView):
    model = HeroSlide
    form_class = forms.HeroSlideForm
    nav_section = "heroslides"
    url_basename = "heroslide"
    singular_name = "Hero Slide"


class HeroSlideDeleteView(DashboardDeleteView):
    model = HeroSlide
    nav_section = "heroslides"
    url_basename = "heroslide"
    singular_name = "Hero Slide"


class BlogPostListView(DashboardListView):
    model = BlogPost
    nav_section = "blog"
    url_basename = "blogpost"
    singular_name = "Blog Post"
    plural_name = "Blog Posts"
    search_fields = ["title", "slug"]
    columns = [
        {"label": "Title", "name": "title"},
        {"label": "Slug", "name": "slug"},
        {"label": "Published", "name": "is_published", "type": "bool"},
        {"label": "Publish at", "name": "publish_at", "type": "datetime"},
    ]


class BlogPostCreateView(DashboardCreateView):
    model = BlogPost
    form_class = forms.BlogPostForm
    nav_section = "blog"
    url_basename = "blogpost"
    singular_name = "Blog Post"


class BlogPostUpdateView(DashboardUpdateView):
    model = BlogPost
    form_class = forms.BlogPostForm
    nav_section = "blog"
    url_basename = "blogpost"
    singular_name = "Blog Post"


class BlogPostDeleteView(DashboardDeleteView):
    model = BlogPost
    nav_section = "blog"
    url_basename = "blogpost"
    singular_name = "Blog Post"


class PageListView(DashboardListView):
    model = Page
    nav_section = "pages"
    url_basename = "page"
    singular_name = "Page"
    plural_name = "Pages"
    search_fields = ["title", "slug"]
    columns = [
        {"label": "Title", "name": "title"},
        {"label": "Slug", "name": "slug"},
        {"label": "Published", "name": "is_published", "type": "bool"},
    ]


class PageCreateView(DashboardCreateView):
    model = Page
    form_class = forms.PageForm
    nav_section = "pages"
    url_basename = "page"
    singular_name = "Page"


class PageUpdateView(DashboardUpdateView):
    model = Page
    form_class = forms.PageForm
    nav_section = "pages"
    url_basename = "page"
    singular_name = "Page"


class PageDeleteView(DashboardDeleteView):
    model = Page
    nav_section = "pages"
    url_basename = "page"
    singular_name = "Page"


class FAQItemListView(DashboardListView):
    model = FAQItem
    nav_section = "faqs"
    url_basename = "faq"
    singular_name = "FAQ"
    plural_name = "FAQs"
    search_fields = ["question"]
    columns = [
        {"label": "Question", "name": "question"},
        {"label": "Order", "name": "display_order"},
        {"label": "Published", "name": "is_published", "type": "bool"},
    ]


class FAQItemCreateView(DashboardCreateView):
    model = FAQItem
    name_object_in_messages = False
    form_class = forms.FAQItemForm
    nav_section = "faqs"
    url_basename = "faq"
    singular_name = "FAQ"


class FAQItemUpdateView(DashboardUpdateView):
    model = FAQItem
    name_object_in_messages = False
    form_class = forms.FAQItemForm
    nav_section = "faqs"
    url_basename = "faq"
    singular_name = "FAQ"


class FAQItemDeleteView(DashboardDeleteView):
    model = FAQItem
    name_object_in_messages = False
    nav_section = "faqs"
    url_basename = "faq"
    singular_name = "FAQ"


class PolicyDocumentListView(DashboardListView):
    model = PolicyDocument
    nav_section = "pages"
    url_basename = "policy"
    singular_name = "Policy"
    plural_name = "Policy Documents"
    search_fields = ["title", "slug"]
    columns = [
        {"label": "Title", "name": "title"},
        {"label": "Type", "name": "policy_type"},
        {"label": "Published", "name": "is_published", "type": "bool"},
    ]


class PolicyDocumentCreateView(DashboardCreateView):
    model = PolicyDocument
    form_class = forms.PolicyDocumentForm
    nav_section = "pages"
    url_basename = "policy"
    singular_name = "Policy"


class PolicyDocumentUpdateView(DashboardUpdateView):
    model = PolicyDocument
    form_class = forms.PolicyDocumentForm
    nav_section = "pages"
    url_basename = "policy"
    singular_name = "Policy"


class PolicyDocumentDeleteView(DashboardDeleteView):
    model = PolicyDocument
    nav_section = "pages"
    url_basename = "policy"
    singular_name = "Policy"
