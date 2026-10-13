"""Catalog management views: products, collections, brands, size charts, reviews."""

from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, F, Case, When, Value, IntegerField, Prefetch, ProtectedError, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from catalog.models import Brand, Collection, Label, Product, ProductImage, Review, HomePageProduct, SizeChart
from catalog.selectors import get_collection_family_ids, products_in_collections
from core.models import Currency
from dashboard import forms
from dashboard.access import dashboard_required
from dashboard.views.base import (
    DashboardCreateView,
    DashboardDeleteView,
    DashboardListView,
    DashboardUpdateView,
)


class ProductListView(DashboardListView):
    model = Product
    template_name = "dashboard/catalog/product_list.html"
    nav_section = "products"
    url_basename = "product"
    singular_name = "Product"
    plural_name = "Products"
    search_fields = ["name", "sku"]
    select_related = ["brand", "homepage_featured"]
    prefetch_related = ["images", "collections", "labels"]
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.GET.get("status", "")
        top_product_ids = None
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)
        elif status == "low":
            qs = qs.filter(stock_quantity__lte=F("low_stock_threshold"), stock_quantity__gt=0)
        elif status == "out":
            qs = qs.filter(stock_quantity=0)
        elif status == "top":
            from django.db.models import Sum
            from orders.models import OrderItem
            from orders.services import REVENUE_ORDER_STATUSES
            top_product_ids = list(
                OrderItem.objects.filter(order__order_status__in=REVENUE_ORDER_STATUSES)
                .values("product_id")
                .annotate(total_revenue=Sum(F("unit_price") * F("quantity")))
                .filter(total_revenue__gt=0)
                .order_by("-total_revenue")
                .values_list("product_id", flat=True)
            )
            if top_product_ids:
                qs = qs.filter(id__in=top_product_ids)
            else:
                qs = qs.none()

        collection = self.request.GET.get("collection", "")
        if collection.isdigit():
            qs = qs.filter(
                products_in_collections(get_collection_family_ids(collection_id=int(collection)))
            )
            
        if status == "top" and top_product_ids:
            preserved_order = Case(*[When(pk=pk, then=Value(pos)) for pos, pk in enumerate(top_product_ids)], output_field=IntegerField())
            return qs.order_by(preserved_order)
            
        #sort pinned products to the top, toggled-off to the bottom
        qs = qs.order_by(
            Case(
                When(homepage_featured__is_shown=True, then=Value(1)),
                When(homepage_featured__is_shown=False, then=Value(-1)),
                default=Value(0),
                output_field=IntegerField()
            ).desc(),
            Case(
                When(homepage_featured__is_shown=True, then=F("homepage_featured__updated_at")),
                default=None
            ).desc(nulls_last=True),
            Case(
                When(homepage_featured__is_shown=False, then=F("homepage_featured__updated_at")),
                default=None
            ).asc(nulls_last=True),
            "-created_at"
        )
        return qs

    STATUS_FILTER_LABELS = {
        "active": "Active",
        "inactive": "Inactive",
        "low": "Low Stock",
        "out": "Out of Stock",
        "top": "Top Selling",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        default_currency = Currency.objects.filter(is_default=True).first()
        context["currency_symbol"] = default_currency.symbol if default_currency else ""
        context["collections"] = Collection.objects.order_by("name")
        status_filter = self.request.GET.get("status", "")
        collection_filter = self.request.GET.get("collection", "")
        context["status_filter"] = status_filter
        context["collection_filter"] = collection_filter

        active_filters = []
        if status_filter:
            params = self.request.GET.copy()
            params.pop("status", None)
            active_filters.append({
                "label": self.STATUS_FILTER_LABELS.get(status_filter, status_filter),
                "clear_url": f"{self.request.path}?{params.urlencode()}" if params else self.request.path,
            })
        if collection_filter:
            collection = Collection.objects.filter(pk=collection_filter).first()
            params = self.request.GET.copy()
            params.pop("collection", None)
            active_filters.append({
                "label": collection.name if collection else "Collection",
                "clear_url": f"{self.request.path}?{params.urlencode()}" if params else self.request.path,
            })
        context["active_filters"] = active_filters
        return context


class ProductDeleteView(DashboardDeleteView):
    model = Product
    nav_section = "products"
    url_basename = "product"
    singular_name = "Product"


def _render_product_form(request, product, mode):
    if request.method == "POST":
        form = forms.ProductForm(request.POST, request.FILES, instance=product)
        variants = forms.ProductVariantFormSet(request.POST, instance=product, prefix="variants")
        images = forms.ProductImageFormSet(
            request.POST, request.FILES, instance=product, prefix="images"
        )
        specifications = forms.ProductSpecificationFormSet(
            request.POST, instance=product, prefix="specifications"
        )

        #evaluate all four eagerly (not via `and` short-circuit) so every
        #formset gets a chance to populate its own errors for re-display.
        form_valid = form.is_valid()
        variants_valid = variants.is_valid()
        images_valid = images.is_valid()
        specifications_valid = specifications.is_valid()

        #product-level base_price/mrp/purchase_price/stock_quantity are only
        #meaningful standalone when no variant exists to drive them (see the
        #sync below, and ProductForm.clean() which otherwise silently defaults
        #a blank of any of these to 0).
    
        has_surviving_variant = any(
            (vform.instance.pk or vform.has_changed())
            and not vform.data.get(vform.add_prefix("DELETE"))
            for vform in variants.forms
        )
        if form_valid and not has_surviving_variant:
            for field, label in (
                ("base_price", "Base price"),
                ("mrp", "MRP"),
                ("purchase_price", "Purchase price"),
                ("stock_quantity", "Stock quantity"),
            ):
                if form.data.get(form.add_prefix(field)) in (None, ""):
                    form.add_error(field, f"{label} is required when the product has no variants.")
                    form_valid = False
                elif field in ("base_price", "mrp") and form.cleaned_data.get(field, 0) <= 0:
                    form.add_error(field, f"{label} must be greater than 0.")
                    form_valid = False

        if form_valid and variants_valid and images_valid and specifications_valid:
            try:
                with transaction.atomic():
                    product = form.save()
                    variants.instance = product
                    variants.save()

                    if product.variants.exists():
                        from django.db.models import Sum
                        default_variant = (
                            product.variants.filter(is_default=True).first()
                            or next((v for v in product.variants.all() if v.stock_quantity > 0), None)
                            or product.variants.first()
                        )
                        total_stock = product.variants.aggregate(total=Sum("stock_quantity"))["total"] or 0

                        product.stock_quantity = total_stock
                        product.base_price = default_variant.base_price
                        product.mrp = default_variant.mrp
                        product.purchase_price = default_variant.purchase_price
                        product.save(update_fields=["stock_quantity", "base_price", "mrp", "purchase_price"])

                    images.instance = product
                    images.save()
                    specifications.instance = product
                    specifications.save()
            except ProtectedError:
                messages.error(
                    request,
                    "Cannot delete a variant that is included in an order. "
                    "Mark it out of stock instead, or remove it from the order first."
                )
                return redirect("dashboard:product-list")

            messages.success(request, f"Product '{product.name}' saved successfully.")
            return redirect("dashboard:product-list")


        form.retain_uploads()
        for iform in images.forms:
            iform.retain_uploads()

    else:
        form = forms.ProductForm(instance=product)
        variants = forms.ProductVariantFormSet(instance=product, prefix="variants")
        images = forms.ProductImageFormSet(instance=product, prefix="images")
        specifications = forms.ProductSpecificationFormSet(
            instance=product, prefix="specifications"
        )

    for f in [
        form,
        *variants.forms,
        variants.empty_form,
        *images.forms,
        images.empty_form,
        *specifications.forms,
        specifications.empty_form,
    ]:
        _style(f)

    context = {
        "nav_section": "products",
        "page_title": f"{'Add' if mode == 'create' else 'Edit'} Product",
        "form": form,
        "variants": variants,
        "images": images,
        "specifications": specifications,
        "form_mode": mode,
        "product": product,
        "cancel_url": reverse("dashboard:product-list"),
    }
    
    from catalog.models import ProductVariant
    context["existing_variant_types"] = ProductVariant.objects.exclude(variant_type="").values_list("variant_type", flat=True).distinct()
    
    return render(request, "dashboard/catalog/product_form.html", context)


def _style(form):
    """Apply Bootstrap classes to a form's widgets (shared with generic mixin)."""
    for field in form.fields.values():
        widget = field.widget
        css = widget.attrs.get("class", "")
        name = widget.__class__.__name__.lower()
        if "checkbox" in name:
            widget.attrs["class"] = (css + " form-check-input").strip()
        elif "select" in name:
            widget.attrs["class"] = (css + " form-select").strip()
        elif "file" in name:
            widget.attrs["class"] = (css + " form-control").strip()
        else:
            widget.attrs["class"] = (css + " form-control").strip()


@dashboard_required
@require_http_methods(["GET", "POST"])
def product_create(request):
    return _render_product_form(request, None, "create")


@dashboard_required
@require_http_methods(["GET", "POST"])
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return _render_product_form(request, product, "edit")


@dashboard_required
@require_http_methods(["POST"])
def product_home_toggle(request, pk):
    product = get_object_or_404(Product, pk=pk)
    home_prod, created = HomePageProduct.objects.get_or_create(product=product)
    
    #toggle the state
    home_prod.is_shown = not home_prod.is_shown
    home_prod.save()
    
    if home_prod.is_shown:
        messages.success(request, f"{product.name} order set as first.")
    else:
        messages.info(request, f"{product.name} order set as last.")
        
    return redirect("dashboard:product-list")


PICKER_RESULT_LIMIT = 50


def _picker_products(queryset) -> list[dict]:
    """Serialise products for the collection product picker (name, SKU, thumbnail)."""
    products = queryset.prefetch_related(
        Prefetch("images", queryset=ProductImage.objects.order_by("-is_primary", "display_order"))
    )
    payload = []
    for product in products:
        images = list(product.images.all())
        payload.append(
            {
                "id": product.pk,
                "name": product.name,
                "sku": product.sku,
                "image": images[0].image.url if images and images[0].image else "",
            }
        )
    return payload


@dashboard_required
@require_http_methods(["GET"])
def collection_product_search(request):
    """JSON product search backing the "add products" box on the collection form."""
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})
    #one extra row tells the picker whether there are more matches than shown
    matches = list(
        Product.objects.filter(Q(name__icontains=query) | Q(sku__icontains=query))
        .order_by("name")
        .values_list("pk", flat=True)[: PICKER_RESULT_LIMIT + 1]
    )
    has_more = len(matches) > PICKER_RESULT_LIMIT
    page = Product.objects.filter(pk__in=matches[:PICKER_RESULT_LIMIT]).order_by("name")
    return JsonResponse({"results": _picker_products(page), "has_more": has_more})


class CollectionListView(DashboardListView):
    model = Collection
    nav_section = "collections"
    url_basename = "collection"
    singular_name = "Collection"
    plural_name = "Collections"
    search_fields = ["name", "slug"]
    select_related = ["parent"]
    filter_by_active_status = True
    columns = [
        {"label": "Image", "name": "image", "type": "image"},
        {"label": "Name", "name": "name"},
        {"label": "Slug", "name": "slug"},
        {"label": "Parent", "name": "parent.name"},
        {"label": "Products", "name": "product_count"},
        {"label": "On home page", "name": "show_on_homepage", "type": "bool"},
        {"label": "Order", "name": "display_order"},
        {"label": "Active", "name": "is_active", "type": "bool"},
    ]

    def get_queryset(self):
        return super().get_queryset().annotate(product_count=Count("products"))


class _CollectionFormMixin:
    """Collection screens share one form template with the product picker."""

    model = Collection
    form_class = forms.CollectionForm
    template_name = "dashboard/catalog/collection_form.html"
    nav_section = "collections"
    url_basename = "collection"
    singular_name = "Collection"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        #bound forms re-show what was just posted; fresh forms show the saved membership
        raw_ids = context["form"]["products"].value() or []
        ids = [int(pk) for pk in raw_ids if str(pk).isdigit()]
        by_id = {p["id"]: p for p in _picker_products(Product.objects.filter(pk__in=ids))}
        context["selected_products"] = [by_id[pk] for pk in ids if pk in by_id]
        return context


class CollectionCreateView(_CollectionFormMixin, DashboardCreateView):
    pass


class CollectionUpdateView(_CollectionFormMixin, DashboardUpdateView):
    pass


class CollectionDeleteView(DashboardDeleteView):
    model = Collection
    nav_section = "collections"
    url_basename = "collection"
    singular_name = "Collection"



class LabelListView(DashboardListView):
    model = Label
    nav_section = "labels"
    url_basename = "label"
    singular_name = "Label"
    plural_name = "Labels"
    search_fields = ["name", "slug"]
    filter_by_active_status = True
    default_ordering = ["display_order", "name"]
    columns = [
        {"label": "Name", "name": "name"},
        {"label": "Slug", "name": "slug"},
        {"label": "Badge colour", "name": "background_color"},
        {"label": "Text colour", "name": "text_color"},
        {"label": "Order", "name": "display_order"},
        {"label": "Active", "name": "is_active", "type": "bool"},
    ]


class LabelCreateView(DashboardCreateView):
    model = Label
    form_class = forms.LabelForm
    nav_section = "labels"
    url_basename = "label"
    singular_name = "Label"


class LabelUpdateView(DashboardUpdateView):
    model = Label
    form_class = forms.LabelForm
    nav_section = "labels"
    url_basename = "label"
    singular_name = "Label"


class LabelDeleteView(DashboardDeleteView):
    model = Label
    nav_section = "labels"
    url_basename = "label"
    singular_name = "Label"


class BrandListView(DashboardListView):
    model = Brand
    nav_section = "brands"
    url_basename = "brand"
    singular_name = "Brand"
    plural_name = "Brands"
    search_fields = ["name", "slug"]
    filter_by_featured_status = True
    columns = [
        {"label": "Name", "name": "name"},
        {"label": "Slug", "name": "slug"},
        {"label": "Featured", "name": "is_featured", "type": "bool"},
    ]


class BrandCreateView(DashboardCreateView):
    model = Brand
    form_class = forms.BrandForm
    nav_section = "brands"
    url_basename = "brand"
    singular_name = "Brand"


class BrandUpdateView(DashboardUpdateView):
    model = Brand
    form_class = forms.BrandForm
    nav_section = "brands"
    url_basename = "brand"
    singular_name = "Brand"


class BrandDeleteView(DashboardDeleteView):
    model = Brand
    nav_section = "brands"
    url_basename = "brand"
    singular_name = "Brand"



class SizeChartListView(DashboardListView):
    model = SizeChart
    nav_section = "size_charts"
    url_basename = "sizechart"
    singular_name = "Size Chart"
    plural_name = "Size Charts"
    search_fields = ["name"]
    filter_by_active_status = True
    columns = [
        {"label": "Name", "name": "name"},
        {"label": "Created At", "name": "created_at", "type": "datetime"},
        {"label": "Active", "name": "is_active", "type": "bool"},
    ]


class SizeChartCreateView(DashboardCreateView):
    model = SizeChart
    form_class = forms.SizeChartForm
    nav_section = "size_charts"
    url_basename = "sizechart"
    singular_name = "Size Chart"
    template_name = "dashboard/catalog/sizechart_form.html"


class SizeChartUpdateView(DashboardUpdateView):
    model = SizeChart
    form_class = forms.SizeChartForm
    nav_section = "size_charts"
    url_basename = "sizechart"
    singular_name = "Size Chart"
    template_name = "dashboard/catalog/sizechart_form.html"


class SizeChartDeleteView(DashboardDeleteView):
    model = SizeChart
    nav_section = "size_charts"
    url_basename = "sizechart"
    singular_name = "Size Chart"



class ReviewListView(DashboardListView):
    model = Review
    nav_section = "reviews"
    url_basename = "review"
    singular_name = "Review"
    plural_name = "Reviews"
    select_related = ["product", "customer__user"]
    can_create = False
    columns = [
        {"label": "Product", "name": "product.name"},
        {"label": "Rating", "name": "rating"},
        {"label": "Title", "name": "title"},
        {"label": "Status", "name": "get_moderation_status_display", "type": "badge"},
        {"label": "Submitted", "name": "created_at", "type": "datetime"},
    ]


class ReviewUpdateView(DashboardUpdateView):
    model = Review
    form_class = forms.ReviewForm
    nav_section = "reviews"
    url_basename = "review"
    singular_name = "Review"

    def form_valid(self, form):
        form.instance.moderated_by = self.request.user
        
        #clear notification 
        original_review = self.get_object()
        from notifications.models import Notification
        body_text = f'Review "{original_review.title}" on {original_review.product.name} awaits approval.'
        Notification.objects.filter(
            title="Review pending moderation", 
            body=body_text,
            is_read=False
        ).update(is_read=True)
        
        return super().form_valid(form)


class ReviewDeleteView(DashboardDeleteView):
    model = Review
    nav_section = "reviews"
    url_basename = "review"
    singular_name = "Review"

    def form_valid(self, form):
        #clear notification 
        original_review = self.get_object()
        from notifications.models import Notification
        body_text = f'Review "{original_review.title}" on {original_review.product.name} awaits approval.'
        Notification.objects.filter(
            title="Review pending moderation", 
            body=body_text,
            is_read=False
        ).update(is_read=True)
        
        return super().form_valid(form)
