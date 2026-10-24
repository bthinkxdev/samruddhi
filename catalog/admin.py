"""Django admin registrations for the catalog app."""

from __future__ import annotations

from django.contrib import admin

from catalog.models import (
    Collection,
    Label,
    Product,
    ProductImage,
    ProductRelation,
    ProductVariant,
    ProductVideo,
    Review,
    ReviewPhoto,
    ProductSpecification,
    ProductDocument,
)


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    """Admin for collections."""

    list_display = (
        "name",
        "slug",
        "parent",
        "display_order",
        "is_active",
        "show_on_homepage",
        "updated_at",
    )
    list_filter = ("is_active", "show_on_homepage")
    search_fields = ("name", "slug")
    list_select_related = ("parent",)
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("display_order", "name")



@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    """Admin for product labels (corner badges)."""

    list_display = ("name", "slug", "background_color", "text_color", "display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("display_order", "name")


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


class ProductSpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 1


class ProductDocumentInline(admin.TabularInline):
    model = ProductDocument
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Admin for products — list_select_related prevents N+1 on list view."""

    list_display = (
        "name",
        "sku",
        "base_price",
        "is_active",
        "stock_quantity",
        "updated_at",
    )
    list_filter = (
        "is_active",
        "labels",
        "collections",
    )
    exclude = ("hsn_code",)
    search_fields = ("name", "slug", "sku")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("collections", "labels")
    inlines = [
        ProductVariantInline,
        ProductImageInline,
        ProductSpecificationInline,
        ProductDocumentInline,
    ]
    ordering = ("name",)


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    """Admin for product variants."""

    list_display = ("product", "variant_type", "name", "base_price", "stock_quantity")
    list_filter = ("variant_type",)
    search_fields = ("product__name", "product__sku", "name")
    list_select_related = ("product",)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """Admin for product images."""

    list_display = ("product", "display_order", "is_primary", "updated_at")
    list_filter = ("is_primary",)
    search_fields = ("product__name", "alt_text")
    list_select_related = ("product",)


@admin.register(ProductVideo)
class ProductVideoAdmin(admin.ModelAdmin):
    """Admin for product videos."""

    list_display = ("product", "video_url", "updated_at")
    search_fields = ("product__name",)
    list_select_related = ("product",)


@admin.register(ProductRelation)
class ProductRelationAdmin(admin.ModelAdmin):
    """Admin for product relationships."""

    list_display = ("product", "related_product", "relation_type", "updated_at")
    list_filter = ("relation_type",)
    search_fields = ("product__name", "related_product__name")
    list_select_related = ("product", "related_product")


class ReviewPhotoInline(admin.TabularInline):
    model = ReviewPhoto
    extra = 0


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Admin for customer reviews."""

    list_display = (
        "product",
        "customer",
        "rating",
        "moderation_status",
        "is_verified_purchase",
        "updated_at",
    )
    list_filter = ("moderation_status", "rating", "is_verified_purchase")
    search_fields = ("product__name", "customer__user__email", "title")
    list_select_related = ("product", "customer", "customer__user", "moderated_by")
    inlines = [ReviewPhotoInline]


@admin.register(ReviewPhoto)
class ReviewPhotoAdmin(admin.ModelAdmin):
    """Admin for review photos."""

    list_display = ("review", "updated_at")
    list_select_related = ("review", "review__product")
