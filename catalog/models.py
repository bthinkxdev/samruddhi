"""Data layer for the catalog app — models only, no business logic."""

from __future__ import annotations

import json
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from core.models import TimeStampedModel


class Collection(TimeStampedModel):
    """
    A curated group of products (Shopify-style collection).

    Products and collections are many-to-many: one collection holds many products
    and a product can sit in several collections. Collections may be nested one
    level deep (parent/child) for navigation.
    """

    name = models.CharField(
        max_length=120,
        verbose_name="Name",
        help_text="Display name of the collection.",
    )
    slug = models.SlugField(
        max_length=120,
        unique=True,
        db_index=True,
        verbose_name="Slug",
        help_text="URL-friendly collection identifier.",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description",
        help_text="Shown on the collection page and used as the SEO description fallback.",
    )
    image = models.ImageField(
        upload_to="collections/images/",
        verbose_name="Image",
        help_text="Square-ish thumbnail shown in collection rails and navigation.",
    )
    banner_image = models.ImageField(
        upload_to="collections/banners/",
        verbose_name="Banner image",
        help_text="Wide banner shown at the top of the collection page and used for social sharing.",
    )
    meta_title = models.CharField(max_length=70, blank=True, verbose_name="Meta title")
    meta_description = models.CharField(max_length=160, blank=True, verbose_name="Meta description")
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Parent collection",
        help_text="Parent node in the collection tree; empty for top-level.",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        verbose_name="Display order",
        help_text="Lower values appear first in navigation.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Is active",
        help_text="When False, the collection is hidden from the storefront.",
    )
    show_on_homepage = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="List on home page",
        help_text="Show this collection as a product grid in the home page collection section.",
    )
    homepage_product_limit = models.PositiveSmallIntegerField(
        default=8,
        validators=[MinValueValidator(1), MaxValueValidator(48)],
        verbose_name="Products on home page",
        help_text="How many products of this collection to list on the home page.",
    )

    class Meta:
        verbose_name = "Collection"
        verbose_name_plural = "Collections"
        ordering = ["display_order", "name"]
        indexes = [
            models.Index(fields=["is_active"], name="cat_collection_is_active_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class Label(TimeStampedModel):
    """
    A badge shown in the corner of a product's image ("Bestseller", "New", ...).

    Labels are many-to-many with products: a product can carry several labels and
    one label can sit on many products.
    """

    name = models.CharField(
        max_length=40,
        verbose_name="Name",
        help_text="Text shown on the badge.",
    )
    slug = models.SlugField(
        max_length=50,
        unique=True,
        verbose_name="Slug",
        help_text="Used in shop filter links, e.g. /shop/?label=bestseller.",
    )
    background_color = models.CharField(
        max_length=7,
        default="#111827",
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Enter a hex colour such as #1A2B3C.")],
        verbose_name="Badge colour",
    )
    text_color = models.CharField(
        max_length=7,
        default="#FFFFFF",
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Enter a hex colour such as #1A2B3C.")],
        verbose_name="Text colour",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        verbose_name="Display order",
        help_text="Lower values appear first when a product has several labels.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Is active",
        help_text="Inactive labels are hidden from the storefront but stay assigned.",
    )

    class Meta:
        verbose_name = "Label"
        verbose_name_plural = "Labels"
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name


class Brand(TimeStampedModel):
    """Product brand for filtering and brand pages."""

    name = models.CharField(max_length=120, verbose_name="Name")
    slug = models.SlugField(
        max_length=120,
        unique=True,
        db_index=True,
        verbose_name="Slug",
    )
    logo = models.ImageField(
        upload_to="brands/logos/",
        blank=True,
        verbose_name="Logo",
    )
    is_featured = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Is featured",
        help_text="Featured brands appear on the homepage.",
    )

    class Meta:
        verbose_name = "Brand"
        verbose_name_plural = "Brands"
        indexes = [
            models.Index(fields=["is_featured"], name="cat_brand_is_featured_idx"),
        ]

    def __str__(self) -> str:
        return self.name



class SizeChart(TimeStampedModel):
    """Reusable size chart that can be assigned to multiple products."""

    name = models.CharField(
        max_length=120,
        verbose_name="Name",
        help_text="Internal name to identify the size chart (e.g., 'Men T-Shirts').",
    )
    content_html = models.TextField(
        blank=True,
        verbose_name="Content",
        help_text="Use the table tool to create your size chart grid.",
    )
    image = models.ImageField(
        upload_to="size_charts/",
        blank=True,
        null=True,
        verbose_name="Fallback Image",
        help_text="Optional fallback image. Used if no rich text content is provided.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Is active",
        help_text="When False, size chart is hidden from the product selection dropdown.",
    )

    class Meta:
        verbose_name = "Size Chart"
        verbose_name_plural = "Size Charts"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def has_content(self) -> bool:
        """
        True when the rich-text chart has something to show. An editor-emptied
        field ("<p><br></p>", "&nbsp;") or a table of blank cells counts as empty.
        """
        import re
        from django.utils.html import strip_tags

        html = self.content_html or ""
        if "<img" in html.lower():
            return True
        text = strip_tags(html).replace("&nbsp;", " ").replace("\xa0", " ")
        return bool(re.sub(r"\s+", "", text))

    @property
    def show_image(self) -> bool:
        """The image is a fallback: shown only when there is no chart content."""
        return bool(self.image) and not self.has_content

    @property
    def is_displayable(self) -> bool:
        """Active and has either chart content or a fallback image to show."""
        return self.is_active and (self.has_content or bool(self.image))



class Product(TimeStampedModel):
    """Core sellable product — highest read volume entity in the platform."""

    name = models.CharField(max_length=255, verbose_name="Name")
    slug = models.SlugField(
        max_length=255,
        unique=True,
        db_index=True,
        verbose_name="Slug",
    )
    sku = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="SKU",
        help_text="Stock keeping unit identifier.",
    )
    hsn_code = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="HSN Code",
        help_text="Harmonized System of Nomenclature code.",
    )
    collections = models.ManyToManyField(
        Collection,
        blank=True,
        related_name="products",
        verbose_name="Collections",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="Brand",
    )
    size_chart = models.ForeignKey(
        SizeChart,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="Size Chart",
    )
    base_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Base price",
        help_text="Default price before variant deltas.",
    )
    mrp = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="MRP")
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Purchase Price")
    is_rental = models.BooleanField(default=False, db_index=True, verbose_name="Is Rental Eligible")
    rental_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Rental Price")
    show_rental_storefront = models.BooleanField(default=True, db_index=True, verbose_name="Show Rental in Storefront")
    color = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        verbose_name="Color",
        help_text="Primary color for PLP color-filter chips.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Is active",
    )
    labels = models.ManyToManyField(
        Label,
        blank=True,
        related_name="products",
        verbose_name="Labels",
    )

    stock_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name="Stock quantity",
    )
    meta_title = models.CharField(max_length=70, blank=True, verbose_name="Meta title")
    meta_description = models.CharField(max_length=160, blank=True, verbose_name="Meta description")
    og_image = models.ImageField(
        upload_to="seo/products/",
        blank=True,
        null=True,
        verbose_name="Open Graph image",
    )
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        verbose_name="Low stock threshold",
        help_text="Triggers low-stock alerts when stock falls at or below this value.",
    )

    #shipping dimensions
    weight = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True, verbose_name="Weight (kg)", help_text="Weight in kilograms, used for courier booking.")
    length = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Length (cm)", help_text="Length in centimeters.")
    width = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Width (cm)", help_text="Width (breadth) in centimeters.")
    height = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Height (cm)", help_text="Height in centimeters.")

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("catalog:pdp", kwargs={"slug": self.slug})

    @property
    def is_in_stock(self) -> bool:
        """True when aggregate product stock is available."""
        return self.stock_quantity > 0

    @property
    def price(self):
        return self.base_price

    @price.setter
    def price(self, value):
        self.base_price = value

    @staticmethod
    def pick_display_variant(variants):
        """
        Choose the variant that represents the product on cards (PLP/Home),
        quick view and the initial PDP selection.

        Priority:
          1. the admin-marked default (primary) variant, if it is in stock;
          2. otherwise the first in-stock variant — a sold-out primary must not
             make the whole product look unavailable while siblings have stock;
          3. if every variant is sold out, the default variant;
          4. otherwise the first variant.
        """
        variants = list(variants)
        if not variants:
            return None
        default = next((v for v in variants if v.is_default), None)
        if default is not None and default.stock_quantity > 0:
            return default
        in_stock = next((v for v in variants if v.stock_quantity > 0), None)
        if in_stock is not None:
            return in_stock
        return default or variants[0]

    @property
    def display_variant(self):
        """See ``pick_display_variant`` for the selection rules."""
        variants = self.variant_list if hasattr(self, "variant_list") else list(self.variants.all())
        return self.pick_display_variant(variants)

    @property
    def effective_base_price(self):
        v = self.display_variant
        return v.base_price if (v and v.base_price is not None and v.base_price > 0) else self.base_price

    @property
    def effective_mrp(self):
        v = self.display_variant
        return v.mrp if (v and v.mrp is not None and v.mrp > 0) else self.mrp

    @property
    def effective_stock_quantity(self) -> int:
        """Stock shown on cards: the display variant's stock, or the product's own stock when it has no variants."""
        v = self.display_variant
        return v.stock_quantity if v is not None else self.stock_quantity

    @property
    def effective_low_stock_threshold(self) -> int:
        """Low-stock threshold matching ``effective_stock_quantity``."""
        v = self.display_variant
        return v.low_stock_threshold if v is not None else self.low_stock_threshold

    @property
    def quick_view_variants_json(self):
        variants = self.variant_list if hasattr(self, "variant_list") else list(self.variants.all())
        if not variants:
            return ""
        data = []
        for v in variants:
            eff_price = v.base_price if (v.base_price is not None and v.base_price > 0) else self.effective_base_price
            eff_mrp = v.mrp if (v.mrp is not None and v.mrp > 0) else self.effective_mrp
            discount = 0
            if eff_mrp and eff_mrp > eff_price:
                discount = int(((eff_mrp - eff_price) / eff_mrp) * 100)
            data.append({
                "id": str(v.pk),
                "name": v.name,
                "stock": v.stock_quantity,
                "thresh": getattr(v, "low_stock_threshold", self.low_stock_threshold),
                "price": str(eff_price),
                "mrp": str(eff_mrp) if (eff_mrp and eff_mrp > eff_price) else "",
                "discount": discount,
            })
        return json.dumps(data)


class VariantType(models.TextChoices):
    """Allowed product variant dimensions."""

    SIZE = "size", "Size"
    PACKAGING = "packaging", "Packaging"


class ProductVariant(TimeStampedModel):
    """Purchasable variant altering price and/or stock."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name="Product",
    )
    variant_type = models.CharField(
        max_length=50,
        verbose_name="Variant type",
    )
    name = models.CharField(max_length=120, verbose_name="Variant Name")
    base_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Base price",
    )
    mrp = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="MRP",
    )
    purchase_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Purchase Price",
    )
    sku_suffix = models.CharField(
        max_length=32,
        blank=True,
        verbose_name="SKU suffix",
        help_text="Appended to the parent product SKU.",
    )
    stock_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name="Stock quantity",
    )
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        verbose_name="Low stock threshold",
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name="Default variant",
        help_text="Drives the product's displayed price/stock when variants exist.",
    )

    class Meta:
        verbose_name = "Product variant"
        verbose_name_plural = "Product variants"
        unique_together = [("product", "variant_type", "name")]

    def __str__(self) -> str:
        return f"{self.product.sku}-{self.sku_suffix}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.product_id:
            total = self.product.variants.aggregate(total=models.Sum("stock_quantity"))["total"] or 0
            Product.objects.filter(pk=self.product_id).update(stock_quantity=total)

    def delete(self, *args, **kwargs):
        product_id = self.product_id
        res = super().delete(*args, **kwargs)
        if product_id:
            remaining = ProductVariant.objects.filter(product_id=product_id)
    
            if remaining.exists():
                total = remaining.aggregate(total=models.Sum("stock_quantity"))["total"] or 0
                Product.objects.filter(pk=product_id).update(stock_quantity=total)
        return res


class ProductImage(TimeStampedModel):
    """Gallery image for a product."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name="Product",
    )
    image = models.ImageField(
        upload_to="products/images/",
        verbose_name="Image",
    )
    alt_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Alt text",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        verbose_name="Display order",
    )
    is_primary = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Is primary",
        help_text="Primary image shown on PLP cards and homepage rails.",
    )

    class Meta:
        verbose_name = "Product image"
        verbose_name_plural = "Product images"
        ordering = ["display_order"]
        indexes = [
            models.Index(
                fields=["product", "is_primary"],
                name="cat_img_product_primary_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Image for {self.product.slug}"


class ProductVideo(TimeStampedModel):
    """Hosted or external video for a product detail page."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="videos",
        verbose_name="Product",
    )
    video_url = models.URLField(verbose_name="Video URL")
    thumbnail = models.ImageField(
        upload_to="products/video_thumbs/",
        blank=True,
        verbose_name="Thumbnail",
    )

    class Meta:
        verbose_name = "Product video"
        verbose_name_plural = "Product videos"

    def __str__(self) -> str:
        return f"Video for {self.product.slug}"


class RelationType(models.TextChoices):
    """Types of product-to-product relationships."""

    RELATED = "related", "Related"
    FREQUENTLY_BOUGHT_TOGETHER = "fbt", "Frequently Bought Together"


class ProductRelation(TimeStampedModel):
    """Directed relationship between two products."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="relations",
        verbose_name="Product",
    )
    related_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="related_from",
        verbose_name="Related product",
    )
    relation_type = models.CharField(
        max_length=20,
        choices=RelationType.choices,
        verbose_name="Relation type",
    )

    class Meta:
        verbose_name = "Product relation"
        verbose_name_plural = "Product relations"
        unique_together = [("product", "related_product", "relation_type")]

    def __str__(self) -> str:
        return f"{self.product.slug} -> {self.related_product.slug} ({self.relation_type})"


class ModerationStatus(models.TextChoices):
    """Review moderation workflow states."""

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Review(TimeStampedModel):
    """Customer product review subject to moderation."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Product",
    )
    customer = models.ForeignKey(
        "accounts.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Customer",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Rating",
    )
    title = models.CharField(max_length=200, verbose_name="Title")
    body = models.TextField(verbose_name="Body")
    is_verified_purchase = models.BooleanField(
        default=False,
        verbose_name="Verified purchase",
    )
    moderation_status = models.CharField(
        max_length=20,
        choices=ModerationStatus.choices,
        default=ModerationStatus.PENDING,
        db_index=True,
        verbose_name="Moderation status",
    )
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderated_reviews",
        verbose_name="Moderated by",
    )

    class Meta:
        verbose_name = "Review"
        verbose_name_plural = "Reviews"
        indexes = [
            models.Index(
                fields=["product", "moderation_status"],
                name="cat_review_product_mod_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.rating}★ — {self.product.slug}"


class ReviewPhoto(TimeStampedModel):
    """Photo attached to a customer review."""

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="photos",
        verbose_name="Review",
    )
    image = models.ImageField(
        upload_to="reviews/photos/",
        verbose_name="Image",
    )

    class Meta:
        verbose_name = "Review photo"
        verbose_name_plural = "Review photos"

    def __str__(self) -> str:
        return f"Photo for review {self.review_id}"


class ProductSpecification(TimeStampedModel):
    """Specification key-value pair for a product."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="specifications",
        verbose_name="Product",
    )
    name = models.CharField(
        max_length=120,
        verbose_name="Specification Name",
        help_text="e.g., Weight, Dimensions, Battery Life, Voltage",
    )
    value = models.CharField(
        max_length=1024,
        verbose_name="Specification Value",
        help_text="e.g., 2.5 kg, 12V, Lithium-Ion",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        verbose_name="Display order",
        help_text="Lower values appear first.",
    )

    class Meta:
        verbose_name = "Product Specification"
        verbose_name_plural = "Product Specifications"
        ordering = ["display_order", "name"]
        unique_together = [("product", "name")]

    def __str__(self) -> str:
        return f"{self.product.name} - {self.name}: {self.value}"


class ProductDocument(TimeStampedModel):
    """Downloadable document/manual for a product."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="Product",
    )
    title = models.CharField(
        max_length=150,
        verbose_name="Document Title",
        help_text="e.g., User Manual, Installation Guide, Warranty Details",
    )
    document_file = models.FileField(
        upload_to="products/documents/",
        verbose_name="Document File",
        help_text="PDF format manuals or brochures.",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        verbose_name="Display order",
        help_text="Lower values appear first.",
    )

    class Meta:
        verbose_name = "Product Document"
        verbose_name_plural = "Product Documents"
        ordering = ["display_order", "title"]

    @property
    def filename(self) -> str:
        import os
        return os.path.basename(self.document_file.name) if self.document_file else ""

    def __str__(self) -> str:
        return f"{self.product.name} - {self.title}"


class HomePageProduct(TimeStampedModel):
    """Tracks products toggled to appear on the homepage."""

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="homepage_featured",
        verbose_name="Product",
    )
    is_shown = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Is shown on home",
    )

    class Meta:
        verbose_name = "Home Page Product"
        verbose_name_plural = "Home Page Products"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.product.name} (Shown: {self.is_shown})"
