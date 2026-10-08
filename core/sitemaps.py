"""XML sitemap definitions for public storefront URLs."""

from __future__ import annotations

from django.contrib.sitemaps import Sitemap
from django.utils import timezone

from catalog.models import Collection, Product
from cms.models import BlogPost, Page


class ProductSitemap(Sitemap):
    """Active products for search engine indexing."""

    changefreq = "daily"
    priority = 0.8
    i18n = True

    def items(self):
        return Product.objects.filter(is_active=True).order_by("-updated_at")

    def lastmod(self, obj: Product):
        return obj.updated_at


class CollectionSitemap(Sitemap):
    """Active collection PLP URLs."""

    changefreq = "weekly"
    priority = 0.7
    i18n = True

    def items(self):
        return Collection.objects.filter(is_active=True).order_by("display_order", "name")

    def location(self, obj: Collection):
        from django.urls import reverse

        return reverse("catalog:plp-collection", kwargs={"collection_slug": obj.slug})



class BlogPostSitemap(Sitemap):
    """Published blog posts."""

    changefreq = "weekly"
    priority = 0.5
    i18n = True

    def items(self):
        now = timezone.now()
        return BlogPost.objects.filter(
            is_published=True,
            publish_at__lte=now,
        ).order_by("-publish_at")

    def lastmod(self, obj: BlogPost):
        return obj.updated_at


class PageSitemap(Sitemap):
    """Published CMS static pages."""

    changefreq = "monthly"
    priority = 0.5
    i18n = True

    def items(self):
        now = timezone.now()
        return Page.objects.filter(
            is_published=True,
            publish_at__lte=now,
        ).order_by("title")

    def lastmod(self, obj: Page):
        return obj.updated_at
