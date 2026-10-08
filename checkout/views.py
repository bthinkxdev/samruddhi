"""HTTP views for the checkout app."""

from __future__ import annotations

import logging
import re

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from accounts.selectors import get_address_by_id, get_saved_addresses
from cart.selectors import get_cart_for_request, get_cart_summary
from cart.services import get_or_create_cart
from checkout.forms import CheckoutAddressForm, CheckoutDeliveryForm, CheckoutPaymentForm
from checkout.selectors import get_checkout_session_by_id
from checkout.services import create_checkout_session, place_order, update_checkout_session
from core import meta_pixel

from payments.registry import PAYMENT_GATEWAYS
from payments.services import process_payment

logger = logging.getLogger(__name__)


def _get_checkout_cart(request: HttpRequest, create: bool = False):
    if request.GET.get("mode") == "cart":
        request.session["checkout_mode"] = "cart"
    if request.session.get("checkout_mode") == "buy_now":
        buy_now_cart_id = request.session.get("buy_now_cart_id")
        if buy_now_cart_id:
            from cart.models import Cart
            cart = Cart.objects.filter(pk=buy_now_cart_id).first()
            if cart:
                return cart
    if create:
        return get_or_create_cart(request=request)
    return get_cart_for_request(request=request)


@require_POST
def checkout_update_delivery_charge_view(request: HttpRequest) -> HttpResponse:
    """Update cart delivery charge if COD is selected and return updated summary."""
    cart = _get_checkout_cart(request=request, create=False)
    if not cart:
        return HttpResponse("")

    gateway_key = request.POST.get("gateway_key", "")
    request.session["checkout_gateway_key"] = gateway_key
    
    if gateway_key == "cod":
        from core.services import get_site_settings
        settings = get_site_settings()
        cart.delivery_charge = settings.cod_delivery_charge
    else:
        from decimal import Decimal
        cart.delivery_charge = Decimal("0.00")
        
    cart.save(update_fields=["delivery_charge", "updated_at"])

    from django.shortcuts import redirect
    return redirect("checkout:checkout")


@require_POST
def checkout_fix_stock_view(request: HttpRequest) -> HttpResponse:
    """Adjust cart items exceeding available stock to their maximum available stock."""
    cart = _get_checkout_cart(request=request, create=False)
    if not cart:
        return HttpResponse("")

    from cart.models import CartItem
    from cart.services import _resolve_unit_price

    items = CartItem.objects.filter(cart=cart).select_related("product", "variant")
    for item in items:
        max_stock = item.variant.stock_quantity if item.variant else item.product.stock_quantity
        if max_stock is None:
            max_stock = 0
        if max_stock > 0 and item.quantity > max_stock:
            user = (
                cart.customer_profile.user
                if (hasattr(cart, "customer_profile") and cart.customer_profile and cart.customer_profile.user_id)
                else None
            )
            try:
                unit_price = _resolve_unit_price(
                    product=item.product,
                    variant=item.variant,
                    user=user,
                    quantity=max_stock,
                )
            except Exception:
                unit_price = item.unit_price_at_add

            item.quantity = max_stock
            item.unit_price_at_add = unit_price
            item.save(update_fields=["quantity", "unit_price_at_add", "updated_at"])

    from django.shortcuts import redirect
    return redirect("checkout:checkout")


@require_GET
def checkout_view(request: HttpRequest) -> HttpResponse:
    """Multi-step checkout page with gift Order Preview partial."""
    cart = _get_checkout_cart(request=request, create=True)
    summary = get_cart_summary(cart=cart)
    if not summary.lines:
        #do not redirect,render the empty state in checkout.html
        pass

    if request.user.is_authenticated:
        from accounts.services import ensure_customer_profile_for_user
        profile = ensure_customer_profile_for_user(user=request.user)
    else:
        profile = None

    session = create_checkout_session(
        cart=cart,
        customer_profile=profile,
        session_key=request.session.session_key or "",
    )


    addresses = []
    if profile:
        if profile.default_address:
            addresses = [profile.default_address]
        else:
            saved_list = list(get_saved_addresses(customer_profile=profile, page_size=1)["results"])
            if saved_list:
                addresses = [saved_list[0]]
            
    from delivery.models import City
    active_cities = City.objects.filter(is_active=True)

    selected_gateway_key = request.session.get("checkout_gateway_key")
    if not selected_gateway_key and session.order:
        last_tx = session.order.payment_transactions.last()
        if last_tx:
            selected_gateway_key = last_tx.gateway_key

    from payments.adapters.concrete import _get_razorpay_credentials
    razorpay_key, razorpay_secret = _get_razorpay_credentials()
    
    available_gateways = {}
    for key, adapter in PAYMENT_GATEWAYS.items():
        if key.startswith("razorpay") and (not razorpay_key or not razorpay_secret):
            continue
        available_gateways[key] = adapter
        
    if not selected_gateway_key and available_gateways:
        selected_gateway_key = list(available_gateways.keys())[0]
        
    from core.services import get_site_settings
    settings = get_site_settings()
        
    if selected_gateway_key == "cod":
        if cart.delivery_charge != settings.cod_delivery_charge:
            cart.delivery_charge = settings.cod_delivery_charge
            cart.save(update_fields=["delivery_charge", "updated_at"])
    else:
        from decimal import Decimal
        if cart.delivery_charge != Decimal("0.00"):
            cart.delivery_charge = Decimal("0.00")
            cart.save(update_fields=["delivery_charge", "updated_at"])

    #reload summary after potential delivery charge update
    summary = get_cart_summary(cart=cart)

    from core.models import State
    INDIAN_STATES = list(State.objects.filter(is_active=True).values_list('name', flat=True))

    from marketing.selectors import has_any_active_coupons
    is_buy_now = request.session.get("checkout_mode") == "buy_now"
    mpx_events = []
    if summary.lines:
        initiate_params = meta_pixel.lines_params(
            summary.lines, value=summary.grand_total, currency=cart.currency
        )
        initiate_params["checkout_type"] = "buy_now" if is_buy_now else "cart"
        mpx_events.append(meta_pixel.event("InitiateCheckout", initiate_params))
    return render(
        request,
        "checkout/checkout.html",
        {
            "mpx_events": mpx_events,
            "cart": cart,
            "summary": summary,
            "checkout_session": session,
            "addresses": addresses,
            "active_cities": active_cities,
            "indian_states": INDIAN_STATES,
            "settings": settings,

            "payment_gateways": available_gateways,
            "selected_gateway_key": selected_gateway_key,
            "has_active_coupons": has_any_active_coupons(),
            "is_buy_now": is_buy_now,
        },
    )


@require_http_methods(["POST"])
def checkout_place_order_view(request: HttpRequest) -> HttpResponse:
    """Place order and process payment in one HTMX step."""
    form = CheckoutPaymentForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "checkout/partials/errors.html",
            {"errors": form.errors},
            status=200,
        )

    cart = _get_checkout_cart(request=request, create=False)
    if cart is None:
        raise Http404("Cart not found.")

    if request.user.is_authenticated:
        from accounts.services import ensure_customer_profile_for_user
        profile = ensure_customer_profile_for_user(user=request.user)
    else:
        profile = None

    session = create_checkout_session(cart=cart, customer_profile=profile, session_key=request.session.session_key or "")
    
    address = None
    address_form = CheckoutAddressForm(request.POST)
    if address_form.is_valid() and address_form.cleaned_data.get("address_id") and profile:
        address = get_address_by_id(
            address_id=address_form.cleaned_data["address_id"],
            customer_profile=profile,
        )
        if address:
            update_checkout_session(checkout_session=session, address=address)
            from accounts.services import set_default_address
            set_default_address(customer_profile=profile, address_id=address.pk)

    guest_name = request.POST.get("guest_name", "").strip()
    guest_email = request.POST.get("guest_email", "").strip()
    guest_phone = request.POST.get("guest_phone", "").strip()

    errors = {}
    if not guest_name:
        errors["guest_name"] = ["Name is required."]

    if not guest_email:
        errors["guest_email"] = ["Email is required."]
    else:
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", guest_email) or "@." in guest_email:
            errors["guest_email"] = ["Enter a valid email address."]
        else:
            try:
                validate_email(guest_email)
            except ValidationError:
                errors["guest_email"] = ["Enter a valid email address."]

    if not guest_phone:
        errors["guest_phone"] = ["Phone is required."]
    else:
        if not re.match(r'^\+?\d+$', guest_phone):
            errors["guest_phone"] = ["Phone number can only contain numbers."]
        elif not re.match(r'^\+?\d{10,15}$', guest_phone):
            errors["guest_phone"] = ["Enter a valid phone number."]

    if not address:
        guest_address_line1 = request.POST.get("guest_address_line1", "").strip()
        guest_address_line2 = request.POST.get("guest_address_line2", "").strip()
        guest_city = request.POST.get("guest_city", "").strip()
        guest_state = request.POST.get("guest_state", "").strip()
        guest_pincode = request.POST.get("guest_pincode", "").strip()

        if not guest_address_line1:
            errors["guest_address_line1"] = ["Address Line 1 is required."]
        elif re.fullmatch(r"^\d+$", guest_address_line1):
            errors["guest_address_line1"] = ["Address cannot consist of numbers only."]
        elif re.fullmatch(r"^[^a-zA-Z0-9]+$", guest_address_line1):
            errors["guest_address_line1"] = ["Address cannot consist of special characters only."]
        elif not re.search(r"[a-zA-Z]", guest_address_line1):
            errors["guest_address_line1"] = ["Enter a valid address containing letters."]

        if not guest_city:
            errors["guest_city"] = ["City is required."]
        elif re.fullmatch(r"^\d+$", guest_city):
            errors["guest_city"] = ["City cannot consist of numbers only."]
        elif re.fullmatch(r"^[^a-zA-Z0-9]+$", guest_city):
            errors["guest_city"] = ["City cannot consist of special characters only."]
        elif not re.search(r"[a-zA-Z]", guest_city):
            errors["guest_city"] = ["Enter a valid city containing letters."]

        if not guest_state:
            errors["guest_state"] = ["State / Province is required."]
        elif re.fullmatch(r"^\d+$", guest_state):
            errors["guest_state"] = ["State cannot consist of numbers only."]
        elif re.fullmatch(r"^[^a-zA-Z0-9]+$", guest_state):
            errors["guest_state"] = ["State cannot consist of special characters only."]
        elif not re.search(r"[a-zA-Z]", guest_state):
            errors["guest_state"] = ["Enter a valid state containing letters."]

        if not guest_pincode:
            errors["guest_pincode"] = ["PIN / Postal Code is required."]
        elif re.fullmatch(r"^[a-zA-Z\s]+$", guest_pincode):
            errors["guest_pincode"] = ["Postal code cannot contain alphabets only."]
        elif re.fullmatch(r"^[^a-zA-Z0-9]+$", guest_pincode):
            errors["guest_pincode"] = ["Postal code cannot contain special characters only."]
        elif not guest_pincode.isdigit():
            errors["guest_pincode"] = ["Postal code can only contain numbers."]
        elif len(guest_pincode) < 3:
            errors["guest_pincode"] = ["Enter a valid postal code."]

    if errors:
        return render(
            request,
            "checkout/partials/errors.html",
            {"errors": errors},
            status=200,
        )

    if not profile and not request.user.is_authenticated and guest_email:
        from accounts.services import login_or_create_customer_by_email
        profile = login_or_create_customer_by_email(email=guest_email, name=guest_name)

    if profile:
        if guest_phone and profile.phone != guest_phone:
            profile.phone = guest_phone
            profile.save(update_fields=["phone", "updated_at"])
        if guest_name:
            parts = guest_name.split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""
            if profile.user.first_name != first_name or profile.user.last_name != last_name:
                profile.user.first_name = first_name
                profile.user.last_name = last_name
                profile.user.save(update_fields=["first_name", "last_name"])

    if not address:
        from accounts.models import Address
        address = Address.objects.filter(
            customer_profile=profile,
            line1=guest_address_line1,
            line2=guest_address_line2,
            city=guest_city,
            pincode=guest_pincode,
        ).first()
        if not address and profile:
            address = Address.objects.create(
                customer_profile=profile,
                line1=guest_address_line1,
                line2=guest_address_line2,
                city=guest_city,
                state=guest_state,
                pincode=guest_pincode,
                label="Delivery Address"
            )
        elif address and profile:
            if getattr(address, "state", "") != guest_state or getattr(address, "pincode", "") != guest_pincode:
                address.state = guest_state
                address.pincode = guest_pincode
                address.save(update_fields=["state", "pincode", "updated_at"])
            
        if profile and address:
            from accounts.services import set_default_address
            set_default_address(customer_profile=profile, address_id=address.pk)
            
        if address:
            update_checkout_session(checkout_session=session, address=address)
            
        if session.customer_profile != profile:
            session.customer_profile = profile
            session.save(update_fields=["customer_profile", "updated_at"])

    delivery_form = CheckoutDeliveryForm(request.POST)
    if delivery_form.is_valid():
        update_checkout_session(
            checkout_session=session,
            delivery_date=delivery_form.cleaned_data.get("delivery_date"),
        )
        
    gateway_key = form.cleaned_data["gateway_key"]
    if gateway_key == "cod":
        from core.services import get_site_settings
        settings = get_site_settings()
        if cart.delivery_charge != settings.cod_delivery_charge:
            cart.delivery_charge = settings.cod_delivery_charge
            cart.save(update_fields=["delivery_charge", "updated_at"])
    else:
        from decimal import Decimal
        if cart.delivery_charge != Decimal("0.00"):
            cart.delivery_charge = Decimal("0.00")
            cart.save(update_fields=["delivery_charge", "updated_at"])

    from cart.selectors import get_cart_summary
    summary = get_cart_summary(cart=cart)
    if summary.has_stock_issues:
        from django.utils.translation import gettext as _
        is_buy_now = request.session.get("checkout_mode") == "buy_now"
        msg = _("This item just went out of stock or quantity exceeds available stock. Please review your order summary.") if is_buy_now else _("Some items in your cart are out of stock. Please review your order summary to adjust them.")
        response = render(
            request,
            "checkout/partials/errors.html",
            {"errors": {"__all__": [msg]}},
            status=200,
        )
        response["HX-Trigger"] = "stockChanged"
        return response

    try:
        from catalog.exceptions import InsufficientStockError
        order = place_order(
            checkout_session_id=session.pk,
            idempotency_key=form.cleaned_data["idempotency_key"],
            gateway_key=gateway_key,
            customer_profile=profile,
            is_guest_checkout=not request.user.is_authenticated,
        )
    except InsufficientStockError as exc:
        response = render(
            request,
            "checkout/partials/errors.html",
            {"errors": {"__all__": [str(exc)]}},
            status=200,
        )
        response["HX-Trigger"] = "stockChanged"
        return response

    if meta_pixel.is_enabled():
        #stored on the order so a webhook-confirmed payment (no browser in the request) can
        #still send fbp/fbc/IP/UA to the Conversions API, and so Purchase carries checkout_type
        tracking = meta_pixel.capture_tracking_context(
            request,
            checkout_type="buy_now" if request.session.get("checkout_mode") == "buy_now" else "cart",
        )
        tracking["source_url"] = request.build_absolute_uri(
            reverse("checkout:confirmation", kwargs={"order_id": order.pk})
        )
        order.invoice_details = {**(order.invoice_details or {}), "meta_tracking": tracking}
        order.save(update_fields=["invoice_details", "updated_at"])

    payment_data = {}

    process_payment(
        order=order,
        gateway_key=gateway_key,
        payment_data=payment_data,
    )

    if gateway_key.startswith("razorpay"):
        pay_url = reverse("checkout:razorpay-pay", kwargs={"order_id": order.pk})
        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Redirect"] = pay_url
            return response
        return redirect(pay_url)

    confirmation_url = reverse("checkout:confirmation", kwargs={"order_id": order.pk})
    if request.headers.get("HX-Request"):
        response = HttpResponse()
        response["HX-Redirect"] = confirmation_url
        return response
    return redirect(confirmation_url)


@require_GET
def checkout_confirmation_view(request: HttpRequest, order_id: int) -> HttpResponse:
    """Separate order confirmation / success page."""
    request.session["checkout_mode"] = "cart"
    from orders.models import Order
    from django.shortcuts import get_object_or_404
    order = get_object_or_404(Order, pk=order_id)
    #Purchase only for a real sale (order.success_at) — never for a pending / failed payment
    purchase_event = meta_pixel.purchase_page_event(order)
    return render(
        request,
        "checkout/confirmation_page.html",
        {
            "order": order,
            "mpx_events": [purchase_event] if purchase_event else [],
        },
    )


from django.views.decorators.cache import never_cache

@never_cache
@require_GET
def razorpay_pay_view(request: HttpRequest, order_id: int) -> HttpResponse:
    """Render Razorpay checkout payment page."""
    from orders.models import Order, OrderStatus
    from payments.models import PaymentTransaction
    from payments.adapters.concrete import _get_razorpay_credentials
    from django.shortcuts import get_object_or_404

    order = get_object_or_404(Order, pk=order_id)
    
    if order.order_status != OrderStatus.CHECKOUT_PENDING:
        from django.shortcuts import redirect
        return redirect("catalog:plp")

    payment_tx = PaymentTransaction.objects.filter(order=order, gateway_key__startswith="razorpay").last()
    key_id, _ = _get_razorpay_credentials()

    customer_name = ""
    customer_email = ""
    customer_phone = ""
    if order.customer_profile:
        customer_name = f"{order.customer_profile.user.first_name} {order.customer_profile.user.last_name}".strip() or order.customer_profile.user.username
        customer_email = order.customer_profile.user.email
        customer_phone = order.customer_profile.phone
    elif order.delivery_address_snapshot:
        customer_name = order.delivery_address_snapshot.get("recipient_name", "")
        customer_email = order.delivery_address_snapshot.get("email", "")
        customer_phone = order.delivery_address_snapshot.get("phone", "")

    amount_in_paise = int(order.total_amount * 100)
    from core.selectors import get_default_currency
    default_curr = get_default_currency()
    currency_code = order.currency.code if order.currency else (default_curr.code if default_curr else "AED")
    razorpay_order_id = payment_tx.external_intent_id if payment_tx else f"rzp_order_{order.pk}"

    #determine prefill method based on gateway key
    prefill_method = ""
    payment_method_name = "Razorpay"
    if payment_tx and payment_tx.gateway_key:
        if payment_tx.gateway_key == "razorpay_upi":
            prefill_method = "upi"
            payment_method_name = "UPI"
        elif payment_tx.gateway_key == "razorpay_card":
            prefill_method = "card"
            payment_method_name = "Credit/Debit Card"
        elif payment_tx.gateway_key == "razorpay_netbanking":
            prefill_method = "netbanking"
            payment_method_name = "Net Banking"
        elif payment_tx.gateway_key == "razorpay_wallet":
            prefill_method = "wallet"
            payment_method_name = "Wallet"

    #store order_id in session so the callback can retrieve it
    request.session["razorpay_order_pk"] = order.pk

    #build absolute callback URL for Razorpay redirect
    callback_url = request.build_absolute_uri(reverse("checkout:razorpay-callback"))
    cancel_url = request.build_absolute_uri(reverse("checkout:checkout"))

    #an unpaid order now exists: the customer is past checkout but has NOT bought anything yet
    pending_params = meta_pixel.order_params(order)
    pending_params["payment_method"] = "online"
    pending_params["payment_gateway"] = payment_tx.gateway_key if payment_tx else ""
    return render(
        request,
        "checkout/razorpay_pay.html",
        {
            "mpx_events": [meta_pixel.event("OnlinePaymentStarted", pending_params, custom=True)],
            "mpx_failure_params": pending_params,
            "order": order,
            "razorpay_key_id": key_id or "rzp_test_mock",
            "razorpay_order_id": razorpay_order_id,
            "amount_in_paise": amount_in_paise,
            "currency_code": currency_code,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "callback_url": callback_url,
            "cancel_url": cancel_url,
            "prefill_method": prefill_method,
            "payment_method_name": payment_method_name,
        },
    )


from django.views.decorators.csrf import csrf_exempt


def _queue_payment_failed(request: HttpRequest, *, order, reason: str) -> None:
    """Report a server-detected failed online payment on the checkout page the customer lands on."""
    params = meta_pixel.order_params(order)
    params["payment_method"] = "online"
    params["failure_reason"] = reason
    meta_pixel.queue_event(request, "PaymentFailed", params, custom=True)


@csrf_exempt
@require_http_methods(["POST"])
def razorpay_callback_view(request: HttpRequest) -> HttpResponse:
    """
    Handle POST callback from Razorpay after payment.

    Razorpay redirects the full browser here with razorpay_payment_id,
    razorpay_order_id, and razorpay_signature as POST parameters.
    """
    from payments.models import PaymentTransaction
    from payments.adapters.concrete import RazorpayAdapter
    from payments.services import confirm_payment_success, confirm_payment_failed
    from django.shortcuts import get_object_or_404
    from orders.models import Order
    from core.selectors import get_default_currency

    razorpay_payment_id = request.POST.get("razorpay_payment_id", "")
    razorpay_order_id = request.POST.get("razorpay_order_id", "")
    razorpay_signature = request.POST.get("razorpay_signature", "")

    #try order_id from POST (JS form submit) or session (Razorpay redirect)
    order_id = request.POST.get("order_id") or request.session.get("razorpay_order_pk")

    if not order_id:
        #fallback: look up order via Razorpay order ID stored in PaymentTransaction
        payment_tx = PaymentTransaction.objects.filter(
            external_intent_id=razorpay_order_id,
            gateway_key__startswith="razorpay",
        ).last()
        if payment_tx:
            order_id = payment_tx.order_id
        else:
            return redirect("checkout:checkout")

    order = get_object_or_404(Order, pk=order_id)
    payment_tx = PaymentTransaction.objects.filter(order=order, gateway_key__startswith="razorpay").last()

    #clean up session
    request.session.pop("razorpay_order_pk", None)

    adapter = RazorpayAdapter()
    is_valid = adapter.verify_payment_signature(
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_signature=razorpay_signature,
    )

    if is_valid and payment_tx:
        if not payment_tx.currency:
            default_curr = get_default_currency()
        currency_code = payment_tx.currency.code if payment_tx.currency else (default_curr.code if default_curr else "AED")
        capture_succeeded = adapter.capture_payment(
            razorpay_payment_id=razorpay_payment_id,
            amount=payment_tx.amount,
            currency=currency_code,
        )
        if not capture_succeeded:
            logger.error(
                "Razorpay capture failed after valid signature: order_id=%s "
                "razorpay_payment_id=%s razorpay_order_id=%s",
                order.pk, razorpay_payment_id, razorpay_order_id,
            )
            confirm_payment_failed(payment_transaction=payment_tx)
            _queue_payment_failed(request, order=order, reason="capture_failed")
            return redirect("checkout:checkout")

        confirm_payment_success(payment_transaction=payment_tx, external_transaction_id=razorpay_payment_id)
        return redirect("checkout:confirmation", order_id=order.pk)
    else:
        if payment_tx:
            confirm_payment_failed(payment_transaction=payment_tx)
        _queue_payment_failed(request, order=order, reason="verification_failed")
        return redirect("checkout:checkout")


@require_POST
def checkout_coupon_apply_view(request: HttpRequest) -> HttpResponse:
    """Validate and apply a coupon code from checkout."""
    from cart.forms import CartCouponForm
    from cart.services import apply_coupon
    from marketing.exceptions import InvalidCouponError
    from django.contrib import messages
    from cart.selectors import get_cart_for_request
    from django.utils.translation import gettext as _

    form = CartCouponForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Enter a valid coupon code."))
        return redirect("checkout:checkout")

    cart = _get_checkout_cart(request=request, create=False)
    if cart is None:
        raise Http404("Cart not found.")

    try:
        apply_coupon(cart=cart, code=form.cleaned_data["code"])
        messages.success(request, _("Coupon applied successfully!"))
    except InvalidCouponError as exc:
        messages.error(request, str(exc))

    return redirect("checkout:checkout")


@require_POST
def checkout_coupon_remove_view(request: HttpRequest) -> HttpResponse:
    """Remove any applied coupon from the cart from checkout."""
    from cart.services import remove_coupon
    from cart.selectors import get_cart_for_request
    from django.contrib import messages
    from django.utils.translation import gettext as _
    
    cart = _get_checkout_cart(request=request, create=False)
    if cart:
        remove_coupon(cart=cart)
        messages.success(request, _("Coupon removed."))
    return redirect("checkout:checkout")
