"""Data layer for the cms app — models only, no business logic."""

from __future__ import annotations

from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from core.models import SEOModel, TimeStampedModel


class HomepageSectionType(models.TextChoices):
    """Every homepage block type; add one enum value + one partial to extend."""

    HERO_SLIDER = "hero_slider", "Hero Slider"
    SHOP_BY_COLLECTION = "shop_by_collection", "Shop by Collection"
    FEATURED_BRANDS = "featured_brands", "Featured Brands"
    SUBSCRIPTION_BANNER = "subscription_banner", "Subscription Banner"
    MARKETING_FEATURES = "marketing_features", "Marketing Feature Cards"
    REVIEWS = "reviews", "Reviews"
    INSTAGRAM_GALLERY = "instagram_gallery", "Instagram Gallery"
    NEWSLETTER = "newsletter", "Newsletter"
    COLLECTION_PRODUCTS = "collection_products", "Collection Product Grids"


class PublishableModel(models.Model):
    """Mixin for scheduled publishing."""

    is_published = models.BooleanField(default=False, db_index=True, verbose_name="Is published")
    publish_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Publish at",
        help_text="Leave blank to publish immediately when is_published is checked.",
    )

    class Meta:
        abstract = True

    @staticmethod
    def live_q():

        from django.db.models import Q

        return Q(is_published=True) & (Q(publish_at__isnull=True) | Q(publish_at__lte=timezone.now()))

    @property
    def is_live(self) -> bool:
        if not self.is_published:
            return False
        if self.publish_at and self.publish_at > timezone.now():
            return False
        return True


class HomepageSection(TimeStampedModel):
    """Configurable homepage section rendered via cms/sections/<type>.html partials."""

    section_type = models.CharField(
        max_length=40,
        choices=HomepageSectionType.choices,
        db_index=True,
        verbose_name="Section type",
    )
    title = models.CharField(max_length=200, blank=True, verbose_name="Title")
    display_order = models.PositiveIntegerField(
        default=0, db_index=True, verbose_name="Display order"
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Is active")
    config = models.JSONField(default=dict, blank=True, verbose_name="Configuration")

    class Meta:
        verbose_name = "Homepage section"
        verbose_name_plural = "Homepage sections"
        ordering = ["display_order", "id"]
        indexes = [
            models.Index(
                fields=["is_active", "display_order"],
                name="cms_hp_section_active_ord_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_section_type_display()} (#{self.display_order})"


class HeroSlide(TimeStampedModel):
    """A single hero banner slide backed by an uploaded photo or video file."""

    title = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Title",
        help_text="Shown over the banner when set. Also used as media alt text.",
    )
    image = models.ImageField(
        upload_to="cms/hero/images/",
        blank=True,
        verbose_name="Photo",
        help_text="Photo slide. Ignored when a video is uploaded. Note: All banners should have the same resolution.",
    )
    video = models.FileField(
        upload_to="cms/hero/videos/",
        blank=True,
        verbose_name="Video",
        validators=[FileExtensionValidator(["mp4", "webm", "ogg", "mov"])],
        help_text="Video slide (mp4/webm). Takes priority over the photo.",
    )
    poster = models.ImageField(
        upload_to="cms/hero/posters/",
        blank=True,
        verbose_name="Video poster",
        help_text="Still image shown while the video loads.",
    )
    display_order = models.PositiveIntegerField(
        default=0, db_index=True, verbose_name="Display order"
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Is active")

    class Meta:
        ordering = ["display_order", "id"]
        verbose_name = "Hero slide"
        verbose_name_plural = "Hero slides"
        indexes = [
            models.Index(fields=["is_active", "display_order"], name="cms_hero_active_order_idx"),
        ]

    def __str__(self) -> str:
        return self.title or f"Hero slide #{self.pk}"

    @property
    def media_type(self) -> str:
        return "video" if self.video else "image"

    @property
    def media_src(self) -> str:
        if self.video:
            return self.video.url
        if self.image:
            return self.image.url
        return ""

    @property
    def poster_src(self) -> str:
        return self.poster.url if self.poster else ""


class BlogPost(TimeStampedModel, SEOModel, PublishableModel):
    """CMS blog article."""

    title = models.CharField(max_length=255)
    slug = SEOModel.slug_field()
    body = models.TextField()
    excerpt = models.TextField(blank=True)

    class Meta:
        ordering = ["-publish_at", "-created_at"]
        verbose_name = "Blog post"
        verbose_name_plural = "Blog posts"

    def get_absolute_url(self) -> str:
        # There's no individual blog-post detail page/route in this codebase yet
        # (core.urls only has a "blog" list view) — points at the list page so the
        # sitemap doesn't crash. Give each post its own URL once a detail view exists.
        from django.urls import reverse

        return reverse("core:blog")


class Page(TimeStampedModel, SEOModel, PublishableModel):
    """Static CMS page (About, Contact, etc.)."""

    title = models.CharField(max_length=255)
    slug = SEOModel.slug_field()
    body = models.TextField()

    class Meta:
        ordering = ["title"]
        verbose_name = "Page"
        verbose_name_plural = "Pages"

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("core:page", kwargs={"slug": self.slug})


class FAQItem(TimeStampedModel, PublishableModel):
    """Frequently asked question."""

    question = models.CharField(max_length=255)
    answer = models.TextField()
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["display_order", "id"]
        verbose_name = "FAQ item"
        verbose_name_plural = "FAQ items"

    def __str__(self) -> str:
        return self.question


class PolicyDocument(TimeStampedModel, SEOModel, PublishableModel):
    """Legal/policy document (privacy, terms, etc.)."""

    title = models.CharField(max_length=255)
    slug = SEOModel.slug_field()
    body = models.TextField()
    policy_type = models.CharField(max_length=40, db_index=True, default="general")

    class Meta:
        ordering = ["title"]
        verbose_name = "Policy document"
        verbose_name_plural = "Policy documents"
