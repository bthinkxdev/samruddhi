"""HTTP views for the catalog app; thin request parsing delegating to selectors/services."""

from __future__ import annotations

import json

from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from catalog.models import Product
from catalog.forms import ReviewSubmissionForm
from catalog.services import submit_review

from catalog.selectors import (
    get_collection_by_slug,
    get_plp_filter_options,
    get_plp_products,
    get_product_detail,
    get_related_products,
    get_search_suggestions,
    get_variant_price,
    record_product_view,
)
from core import meta_pixel
from core.seo import build_plp_canonical_url, build_product_json_ld, seo_context
from core.services import get_site_settings


def _parse_plp_filters(request: HttpRequest) -> dict:
    """Parse shareable PLP filter query params into a selector filter dict."""
    filters: dict = {}
    collection_id = request.GET.get("collection")
    subcollection_id = request.GET.get("subcollection")
    if subcollection_id:
        filters["collection_id"] = int(subcollection_id)
        filters["subcollection_id"] = int(subcollection_id)
        if collection_id:
            filters["parent_collection_id"] = int(collection_id)
    elif collection_id:
        filters["collection_id"] = int(collection_id)

    if occasion_id := request.GET.get("occasion"):
        filters["occasion_id"] = int(occasion_id)
    if brand_id := request.GET.get("brand"):
        filters["brand_id"] = int(brand_id)
    if recipient_id := request.GET.get("recipient"):
        filters["recipient_id"] = int(recipient_id)
    if color := request.GET.get("color"):
        filters["color"] = color
    if label_slug := request.GET.get("label"):
        filters["label"] = label_slug
    if request.GET.get("in_stock") == "1":
        filters["in_stock"] = True
    if min_price := request.GET.get("min_price"):
        filters["min_price"] = min_price
    if max_price := request.GET.get("max_price"):
        filters["max_price"] = max_price
    return filters


def _plp_pixel_events(*, request: HttpRequest, plp_data: dict, active_collection) -> list[dict]:
    """ViewCollection for a listing; Search when the header search box sent ``?q=``."""
    products = plp_data["results"]
    prices = plp_data["display_prices"]
    content_ids = [meta_pixel.content_id(p) for p in products]
    base = {
        "content_type": "product",
        "content_ids": content_ids,
        "currency": meta_pixel.currency_code(),
        "num_results": plp_data["total_count"],
    }
    events = []
    query = request.GET.get("q", "").strip()
    if query:
        events.append(meta_pixel.event("Search", {**base, "search_string": query[:100]}))
    collection_params = {
        **base,
        "content_category": active_collection.name if active_collection else "All products",
        "collection_id": active_collection.pk if active_collection else "",
        "value": float(sum(prices.get(p.pk, 0) for p in products)),
    }
    events.append(meta_pixel.event("ViewCollection", collection_params, custom=True))
    return events


@require_GET
def plp_view(request: HttpRequest, collection_slug: str | None = None) -> HttpResponse:
    """Product listing page with HTMX partial support for the product grid."""
    filters = _parse_plp_filters(request)
    collection = None
    if collection_slug:
        collection = get_collection_by_slug(slug=collection_slug)
        if collection is None:
            raise Http404("Collection not found")

        if not filters.get("subcollection_id"):
            filters["collection_id"] = collection.pk

    active_collection = collection
    if not active_collection and (collection_id := filters.get("collection_id")):
        from catalog.models import Collection

        active_collection = Collection.objects.filter(pk=collection_id, is_active=True).first()

    subcollections = []
    if active_collection:
        if active_collection.parent_id:
            subcollections = list(active_collection.parent.children.filter(is_active=True))
            filters["subcollection_id"] = active_collection.pk
            filters["parent_collection_id"] = active_collection.parent_id
        else:
            subcollections = list(active_collection.children.filter(is_active=True))
            filters["parent_collection_id"] = active_collection.pk

    sort = request.GET.get("sort") or "featured"
    page = int(request.GET.get("page", 1))
    plp_data = get_plp_products(filters=filters, sort=sort, page=page, user=request.user)
    filter_options = get_plp_filter_options()

    title = "Shop All"
    description = (
        active_collection.description
        or f"Browse the {active_collection.name} collection."
        if active_collection
        else get_site_settings().tagline or "Browse our full collection."
    )

    context = seo_context(
        request=request,
        obj=active_collection,
        title=active_collection.name if active_collection else title,
        description=description,
        canonical_url=build_plp_canonical_url(request=request, collection_slug=collection_slug),
    )
    context.update(
        {
            "plp": plp_data,
            "filters": filters,
            "sort": sort,
            "collections": filter_options["collections"],
            "brands": filter_options["brands"],
            "labels": filter_options["labels"],
            "subcollections": subcollections,
            "subcollections_map": filter_options["subcollections_map"],
            "active_collection": active_collection,
        }
    )

    #the HTMX grid partial (filters / pagination) is not a new page view
    is_grid_partial = request.headers.get("HX-Request") and not request.headers.get("HX-History-Restore-Request")
    if not is_grid_partial:
        context["mpx_events"] = _plp_pixel_events(
            request=request, plp_data=plp_data, active_collection=active_collection
        )

    if request.headers.get("HX-Request") and not request.headers.get("HX-History-Restore-Request"):
        response = render(request, "catalog/partials/product_grid.html", context)
        response["HX-Push-Url"] = request.get_full_path()
    else:
        response = render(request, "catalog/plp.html", context)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@require_GET
def pdp_view(request: HttpRequest, slug: str) -> HttpResponse:
    """Product detail page with gallery, variants, reviews, and delivery estimate."""
    product = get_product_detail(slug=slug)
    if product is None:
        raise Http404("Product not found")

    viewer_key = str(request.session.session_key or request.user.pk or "anon")
    record_product_view(viewer_key=viewer_key, product_id=product.pk)


    site_settings = get_site_settings()

    from cart.models import CartItem
    from cart.selectors import get_cart_for_request

    cart = get_cart_for_request(request=request)
    variant_id = request.GET.get("variant_id")
    target_variant = None
    if variant_id and variant_id.isdigit():
        target_variant = product.variants.filter(pk=int(variant_id)).first()
    else:
        target_variant = product.display_variant

    cart_item = None
    if cart:
        if target_variant:
            cart_item = CartItem.objects.filter(cart=cart, product=product, variant=target_variant).first()
        else:
            cart_item = CartItem.objects.filter(cart=cart, product=product, variant__isnull=True).first()
    is_in_cart = cart_item is not None

    quantity = cart_item.quantity if cart_item else 1
    price_data = get_variant_price(product_id=product.pk, variant_id=target_variant.pk if target_variant else None, user=request.user, quantity=quantity)

    reviews = getattr(product, "approved_reviews", [])
    review_count = len(reviews)
    average_rating = None
    if review_count:
        average_rating = sum(r.rating for r in reviews) / review_count

    product.review_count = review_count
    product.average_rating = average_rating

    from accounts.models import WishlistItem
    from accounts.subscription_services import get_or_create_wishlist

    wishlist = get_or_create_wishlist(request=request)
    is_in_wishlist = WishlistItem.objects.filter(wishlist=wishlist, product_id=product.pk).exists()


    has_delivered_order = False
    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        from orders.models import OrderItem, OrderStatus
        has_delivered_order = OrderItem.objects.filter(
            product=product,
            order__customer_profile=request.user.customer_profile,
            order__order_status=OrderStatus.DELIVERED
        ).exists()

    context = seo_context(
        request=request,
        obj=product,
        title=product.name,
        description=f"{product.name} — {get_site_settings().site_name}",
    )
    context["mpx_events"] = [
        meta_pixel.event(
            "ViewContent",
            meta_pixel.product_params(
                product, price=price_data["price"], variant=target_variant
            ),
        )
    ]
    context.update(
        {
            "product": product,
            "price_data": price_data,

            "whatsapp_number": site_settings.whatsapp_number,
            "is_in_cart": is_in_cart,
            "cart_item": cart_item,
            "selected_variant_id": target_variant.pk if target_variant else "",
            "target_variant": target_variant,
            "is_in_wishlist": is_in_wishlist,
            "related_products": get_related_products(product=product, user=request.user),
            "has_delivered_order": has_delivered_order,
            "product_json_ld": json.dumps(
                build_product_json_ld(
                    product=product,
                    price=price_data["price"],
                    request=request,
                    average_rating=average_rating,
                    review_count=review_count,
                )
            ),
        }
    )
    response = render(request, "catalog/pdp.html", context)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@require_GET
def search_suggestions_view(request: HttpRequest) -> HttpResponse:
    """HTMX live search suggestions partial."""
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        response = render(
            request,
            "catalog/partials/search_suggestions.html",
            {
                "products": [],
                "brands": [],
                "collections": [],
                "query": "",
            },
        )
        response.content = response.content.strip()
        return response
    suggestions = get_search_suggestions(query=query)
    context = {
        "products": suggestions.get("products", []),
        "brands": suggestions.get("brands", []),
        "collections": suggestions.get("collections", []),
        "query": query,
    }
    response = render(
        request,
        "catalog/partials/search_suggestions.html",
        context,
    )
    response.content = response.content.strip()
    return response


@require_GET
def variant_price_view(request: HttpRequest, product_id: int) -> JsonResponse:
    """JSON endpoint for variant price updates on PDP."""
    variant_id = request.GET.get("variant_id")
    quantity_str = request.GET.get("quantity", "1")
    try:
        quantity = int(quantity_str)
    except ValueError:
        quantity = 1
    parsed_variant = int(variant_id) if variant_id else None
    data = get_variant_price(product_id=product_id, variant_id=parsed_variant, user=request.user, quantity=quantity)
    
    from cart.models import CartItem
    from cart.selectors import get_cart_for_request
    
    cart = get_cart_for_request(request=request)
    cart_item = None
    if cart:
        if parsed_variant:
            cart_item = CartItem.objects.filter(cart=cart, product_id=product_id, variant_id=parsed_variant).first()
        else:
            cart_item = CartItem.objects.filter(cart=cart, product_id=product_id, variant__isnull=True).first()
    data["is_in_cart"] = cart_item is not None

    from core.selectors import get_currency_by_code, get_default_currency
    from core.templatetags.storefront_tags import money_label

    session_currency = request.session.get("storefront_currency", "")
    display_currency = (
        get_currency_by_code(code=session_currency) if session_currency else get_default_currency()
    )
    if "price" in data:
        data["formatted_price"] = money_label(data["price"], display_currency)
    if data.get("mrp"):
        data["formatted_mrp"] = money_label(data["mrp"], display_currency)
    if data.get("original_price"):
        data["formatted_original_price"] = money_label(data["original_price"], display_currency)

    return JsonResponse(data)


@require_GET


@require_GET
def rental_list_view(request: HttpRequest) -> HttpResponse:
    from catalog.selectors import _primary_image_prefetch, PLP_CARD_FIELDS
    products = (
        Product.objects.filter(is_active=True, is_rental=True, show_rental_storefront=True)
        .select_related("brand")
        .prefetch_related(_primary_image_prefetch())
        .only(*PLP_CARD_FIELDS)
    )
    return render(request, "catalog/rentals.html", {"products": list(products)})

@require_POST
@login_required
def submit_review_view(request, product_id: int):
    """Handle product review submission from the customer order details page."""
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    from catalog.forms import ReviewSubmissionForm
    form = ReviewSubmissionForm(request.POST)
    
    if not hasattr(request.user, "customer_profile"):
        messages.error(request, "Only customers can submit reviews.")
        return redirect(request.META.get('HTTP_REFERER', '/'))
        
    if form.is_valid():
        from catalog.services import submit_review
        submit_review(
            product=product,
            customer=request.user.customer_profile,
            rating=form.cleaned_data["rating"],
            title=form.cleaned_data["title"],
            body=form.cleaned_data["body"],
            is_verified_purchase=True,
        )
        messages.success(request, "Thank you for your valuable review!")
    else:
        messages.error(request, "There was an error with your review submission. Please check your inputs.")
        
    return redirect(request.META.get('HTTP_REFERER', '/'))
