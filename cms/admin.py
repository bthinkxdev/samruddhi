"""Django admin registrations for the cms app."""

from __future__ import annotations

from django.contrib import admin

from cms.forms import HomepageSectionAdminForm
from cms.models import (
    BlogPost,
    FAQItem,
    HeroSlide,
    HomepageSection,
    Page,
    PolicyDocument,
)


@admin.register(HomepageSection)
class HomepageSectionAdmin(admin.ModelAdmin):
    """
    Homepage builder admin with structured per-type config forms.

    Ordering uses list_editable display_order (no extra dependency) — admins
    set numeric order and drag-sort can be added later via django-admin-sortable2
    if product owners need visual reordering at scale.
    """

    form = HomepageSectionAdminForm
    list_display = ("section_type", "title", "display_order", "is_active", "updated_at")
    list_filter = ("section_type", "is_active")
    search_fields = ("title", "section_type")
    ordering = ("display_order", "id")
    list_editable = ("display_order", "is_active")
    fieldsets = ((None, {"fields": ("section_type", "title", "display_order", "is_active")}),)


@admin.register(HeroSlide)
class HeroSlideAdmin(admin.ModelAdmin):
    """Upload photo or video hero slides; ordering via list_editable display_order."""

    list_display = ("__str__", "media_type", "display_order", "is_active", "updated_at")
    list_filter = ("is_active",)
    list_editable = ("display_order", "is_active")
    ordering = ("display_order", "id")
    fields = ("title", "image", "video", "poster", "display_order", "is_active")

    @admin.display(description="Media")
    def media_type(self, obj: HeroSlide) -> str:
        return obj.media_type


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_published", "publish_at")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "slug")


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_published", "publish_at")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "slug")


@admin.register(FAQItem)
class FAQItemAdmin(admin.ModelAdmin):
    list_display = ("question", "display_order", "is_published")
    list_editable = ("display_order", "is_published")
    ordering = ("display_order",)


@admin.register(PolicyDocument)
class PolicyDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "policy_type", "slug", "is_published")
    prepopulated_fields = {"slug": ("title",)}
    list_filter = ("policy_type", "is_published")
