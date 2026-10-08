"""HTTP views for the accounts app; thin request parsing delegating to selectors/services."""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.cache import never_cache
from django.core.exceptions import ValidationError

from accounts.exceptions import (
    GoogleAuthError,
    OTPRateLimitError,
    OTPVerificationError,
)
from accounts.forms import (
    AddressForm,
    EmailLoginForm,
    EmailRegistrationForm,
    ForgotPasswordForm,
    GoogleLoginForm,
    GuestCheckoutForm,
    OTPRequestForm,
    OTPVerifyForm,
    ResetPasswordForm,
    EmailOTPRequestForm,
    EmailOTPVerifyForm,
    ForgotPasswordEmailForm,
    ResetPasswordEmailForm,
)
from accounts.models import CustomerProfile, OTPPurpose
from accounts.selectors import (
    get_address_by_id,
    get_customer_dashboard_context,
    get_saved_addresses,
    get_saved_payment_methods,
    get_wishlist,
)
from accounts.services import (
    _check_login_rate_limit,
    _increment_login_rate_limit,
    authenticate_google,
    create_address,
    create_guest_checkout_token,
    delete_address,
    delete_saved_payment_method,
    login_or_create_customer_by_phone,
    register_customer_email,
    request_otp,
    reset_password_with_otp,
    update_address,
    verify_otp,
    request_email_otp,
    verify_email_otp,
    login_or_create_customer_by_email,
)
from core import meta_pixel
from core.decorators import role_required

from accounts.selectors import get_customer_subscriptions, get_customer_subscription_by_id
from accounts.forms import SubscriptionCreateForm
from accounts.subscription_services import (
    create_subscription,
    pause_subscription,
    resume_subscription,
    cancel_subscription,
)


def _json_body(request: HttpRequest) -> dict[str, Any]:
    """Parse JSON request body; return empty dict for non-JSON requests."""
    content_type = request.headers.get("Content-Type", "")
    if not content_type.startswith("application/json"):
        return {}
    if not request.body:
        return {}
    try:
        return json.loads(request.body)
    except json.JSONDecodeError:
        return {}


def _error_response(message: str, status: int = 400, code: str = "error") -> JsonResponse:
    return JsonResponse({"success": False, "code": code, "message": message}, status=status)


def _success_response(data: dict[str, Any] | None = None, status: int = 200) -> JsonResponse:
    payload: dict[str, Any] = {"success": True}
    if data:
        payload.update(data)
    return JsonResponse(payload, status=status)


def _serialize_address(address) -> dict[str, Any]:
    return {
        "id": address.pk,
        "label": address.label,
        "line1": address.line1,
        "line2": address.line2,
        "city": address.city,
        "state": getattr(address, "state", ""),
        "pincode": getattr(address, "pincode", ""),
        "is_default": address.is_default,
    }


def _serialize_payment_method(method) -> dict[str, Any]:
    return {
        "id": method.pk,
        "card_brand": method.card_brand,
        "last4": method.last4,
        "expiry_month": method.expiry_month,
        "expiry_year": method.expiry_year,
        "is_default": method.is_default,
    }


def _serialize_order(order) -> dict[str, Any]:
    return {
        "id": order.pk,
        "order_number": order.order_number,
        "order_status": order.order_status,
        "total_amount": str(order.total_amount),
        "created_at": order.created_at.isoformat(),
    }


def _wants_json(request: HttpRequest) -> bool:
    """Return True when the client expects a JSON API response."""
    content_type = request.headers.get("Content-Type", "")
    if request.body and content_type.startswith("application/json"):
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


@never_cache
@require_http_methods(["GET", "POST"])
def email_register_view(request: HttpRequest) -> HttpResponse:
    """Register a new customer with email and password."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
        
    if request.method == "GET":
        return render(request, "accounts/register.html", {"form": EmailRegistrationForm()})

    data = _json_body(request) or request.POST.dict()
    form = EmailRegistrationForm(data)
    if not form.is_valid():
        if _wants_json(request):
            return _error_response(str(form.errors), code="validation_error")
        return render(
            request,
            "accounts/register.html",
            {"form": form, "errors": form.errors},
            status=400,
        )
    try:
        profile = register_customer_email(
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
            name=form.cleaned_data["name"],
        )
    except ValueError as exc:
        if _wants_json(request):
            return _error_response(str(exc), code="registration_failed")
        form.add_error("email", str(exc))
        return render(
            request,
            "accounts/register.html",
            {"form": form, "errors": form.errors},
            status=400,
        )

    login(request, profile.user, backend="django.contrib.auth.backends.ModelBackend")
    meta_pixel.queue_event(request, "CompleteRegistration", {"status": True, "registration_method": "email"})
    if _wants_json(request):
        return _success_response({"user_id": profile.user_id})
    return redirect("accounts:dashboard")


@never_cache
@require_http_methods(["GET", "POST"])
def email_login_view(request: HttpRequest) -> HttpResponse:
    """Authenticate a customer with email and password."""
    if request.user.is_authenticated:
        next_url = request.GET.get("next") or request.POST.get("next")
        return redirect(next_url or "accounts:dashboard")

    if request.method == "GET":
        return render(request, "accounts/login.html", {"form": EmailLoginForm()})

    data = _json_body(request) or request.POST.dict()
    identifier = (
        (data.get("email") or data.get("username") or request.META.get("REMOTE_ADDR", "anon"))
        .strip()
        .lower()
    )
    try:
        _check_login_rate_limit(identifier=identifier)
    except OTPRateLimitError as exc:
        if _wants_json(request):
            return _error_response(str(exc), code="rate_limited", status=429)
        return render(
            request,
            "accounts/login.html",
            {"form": EmailLoginForm(), "error_message": str(exc)},
            status=429,
        )
    form = EmailLoginForm(request, data)
    if not form.is_valid():
        _increment_login_rate_limit(identifier=identifier)
        if _wants_json(request):
            return _error_response("Invalid email or password.", code="auth_failed", status=401)
        return render(
            request,
            "accounts/login.html",
            {"form": form, "error_message": "Invalid email or password."},
            status=401,
        )
    login(request, form.get_user(), backend="django.contrib.auth.backends.ModelBackend")
    meta_pixel.queue_event(request, "Login", {"login_method": "email"}, custom=True)
    if _wants_json(request):
        return _success_response({"user_id": form.get_user().pk})
    next_url = request.GET.get("next") or request.POST.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("accounts:dashboard")


@require_http_methods(["GET", "POST"])
def email_logout_view(request: HttpRequest) -> HttpResponse:
    """Log out the current session."""
    logout(request)
    if _wants_json(request):
        return _success_response()
    return redirect("cms:homepage")


@require_POST
def otp_request_view(request: HttpRequest) -> HttpResponse:
    """Request an OTP for phone-based authentication."""
    data = _json_body(request) or request.POST.dict()
    form = OTPRequestForm(data)
    if not form.is_valid():
        return _error_response(str(form.errors), code="validation_error")
    try:
        otp_request = request_otp(
            phone=form.cleaned_data["phone"],
            purpose=form.cleaned_data["purpose"],
        )
    except OTPRateLimitError as exc:
        return _error_response(str(exc), code="rate_limited", status=429)
    return _success_response(
        {"otp_request_id": otp_request.pk, "expires_at": otp_request.expires_at.isoformat()}
    )


@require_POST
def otp_verify_view(request: HttpRequest) -> HttpResponse:
    """Verify an OTP and log the customer in."""
    data = _json_body(request) or request.POST.dict()
    form = OTPVerifyForm(data)
    if not form.is_valid():
        return _error_response(str(form.errors), code="validation_error")
    try:
        verify_otp(
            phone=form.cleaned_data["phone"],
            otp_code=form.cleaned_data["otp_code"],
            purpose=form.cleaned_data["purpose"],
        )
    except OTPVerificationError as exc:
        return _error_response(str(exc), code=exc.__class__.__name__, status=400)

    purpose = form.cleaned_data["purpose"]
    if purpose in (OTPPurpose.LOGIN, OTPPurpose.SIGNUP):
        profile = login_or_create_customer_by_phone(phone=form.cleaned_data["phone"])
        login(request, profile.user, backend="django.contrib.auth.backends.ModelBackend")
        return _success_response({"user_id": profile.user_id})

    return _success_response({"verified": True})


@require_POST
def google_login_view(request: HttpRequest) -> HttpResponse:
    """Authenticate via Google ID token and log the customer in."""
    data = _json_body(request) or request.POST.dict()
    form = GoogleLoginForm(data)
    if not form.is_valid():
        return _error_response(str(form.errors), code="validation_error")
    try:
        profile = authenticate_google(google_id_token=form.cleaned_data["id_token"])
    except GoogleAuthError as exc:
        return _error_response(str(exc), code="google_auth_failed", status=401)
    login(request, profile.user, backend="django.contrib.auth.backends.ModelBackend")
    return _success_response({"user_id": profile.user_id})


@require_POST
def guest_checkout_view(request: HttpRequest) -> HttpResponse:
    """Issue a signed guest checkout token for a cart session."""
    data = _json_body(request) or request.POST.dict()
    form = GuestCheckoutForm(data)
    if not form.is_valid():
        return _error_response(str(form.errors), code="validation_error")
    token = create_guest_checkout_token(cart_id=form.cleaned_data["cart_id"])
    return _success_response({"guest_token": token})


@require_http_methods(["GET", "POST"])
def forgot_password_view(request: HttpRequest) -> HttpResponse:
    """Send a password-reset OTP to customer's phone or handle single-page email flow."""
    if _wants_json(request):
        if request.method != "POST":
            return _error_response("Method not allowed", status=405)
        data = _json_body(request) or request.POST.dict()
        form = ForgotPasswordForm(data)
        if not form.is_valid():
            return _error_response(str(form.errors), code="validation_error")
        try:
            request_otp(phone=form.cleaned_data["phone"], purpose=OTPPurpose.PASSWORD_RESET)
        except OTPRateLimitError as exc:
            return _error_response(str(exc), code="rate_limited", status=429)
        return _success_response({"message": "OTP sent if the phone is registered."})

    #ui flow
    if request.method == "GET":
        return render(request, "accounts/forgot_password.html", {"form": ForgotPasswordEmailForm(), "step": 1})

    #POST flow
    step = request.POST.get("step")
    if step == "1":
        form = ForgotPasswordEmailForm(request.POST)
        if not form.is_valid():
            return render(request, "accounts/forgot_password.html", {"form": form, "step": 1}, status=400)
        
        email = form.cleaned_data["email"]
        try:
            request_email_otp(email=email, purpose=OTPPurpose.PASSWORD_RESET)
        except Exception as exc:
            form.add_error(None, f"Error generating OTP: {str(exc)}")
            return render(request, "accounts/forgot_password.html", {"form": form, "step": 1}, status=400)
        
        #transition to Step 2
        reset_form = ResetPasswordEmailForm(initial={"email": email})
        return render(request, "accounts/forgot_password.html", {"form": reset_form, "step": 2, "email": email})

    elif step == "2":
        form = ResetPasswordEmailForm(request.POST)
        email = request.POST.get("email", "")
        if not form.is_valid():
            return render(request, "accounts/forgot_password.html", {"form": form, "step": 2, "email": email}, status=400)
        
        otp_code = form.cleaned_data["otp_code"]
        new_password = form.cleaned_data["new_password"]
        
        try:
            verify_email_otp(email=email, otp_code=otp_code, purpose=OTPPurpose.PASSWORD_RESET)
        except Exception as exc:
            form.add_error("otp_code", str(exc))
            return render(request, "accounts/forgot_password.html", {"form": form, "step": 2, "email": email}, status=400)
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.filter(email=email).first()
        if not user:
            form.add_error(None, "User not found.")
            return render(request, "accounts/forgot_password.html", {"form": form, "step": 2, "email": email}, status=400)
        
        user.set_password(new_password)
        user.save(update_fields=["password"])
        
        #log the user in
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("accounts:dashboard")
    
    #fallback if step is missing or invalid
    return redirect("accounts:forgot-password")


@require_http_methods(["GET", "POST"])
def reset_password_view(request: HttpRequest) -> HttpResponse:
    """Redirect web users to single-page forgot_password_view."""
    if _wants_json(request):
        if request.method != "POST":
            return _error_response("Method not allowed", status=405)
        data = _json_body(request) or request.POST.dict()
        form = ResetPasswordForm(data)
        if not form.is_valid():
            return _error_response(str(form.errors), code="validation_error")
        try:
            user = reset_password_with_otp(
                phone=form.cleaned_data["phone"],
                otp_code=form.cleaned_data["otp_code"],
                new_password=form.cleaned_data["new_password"],
            )
        except OTPVerificationError as exc:
            return _error_response(str(exc), code=exc.__class__.__name__, status=400)
        except CustomerProfile.DoesNotExist:
            return _error_response("Customer profile not found.", status=404)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return _success_response({"user_id": user.pk})

    return redirect("accounts:forgot-password")



@login_required
@require_GET
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """Customer account dashboard."""
    context = get_customer_dashboard_context(user=request.user)
    if context is None:
        if _wants_json(request):
            return _error_response("Customer profile not found.", status=404)
        return render(
            request,
            "accounts/dashboard.html",
            {"error_message": "Customer profile not found."},
            status=404,
        )
    if _wants_json(request):
        return _success_response(
            {
                "profile": {
                    "id": context.profile.pk,
                    "phone": context.profile.phone,
                    "phone_verified": context.profile.phone_verified,
                    "preferred_language": context.profile.preferred_language,
                    "preferred_currency": context.profile.preferred_currency.code,
                },
                "default_address": (
                    _serialize_address(context.default_address) if context.default_address else None
                ),
                "recent_orders": [_serialize_order(o) for o in context.recent_orders],
                "unread_notification_count": context.unread_notification_count,
            }
        )
    return render(request, "accounts/dashboard.html", {"dashboard": context})


from django.views.decorators.http import require_http_methods
from accounts.forms import CustomerProfileEditForm

@login_required
@require_http_methods(["GET", "POST"])
def edit_profile_view(request: HttpRequest) -> HttpResponse:
    """Edit retail customer profile and default address."""
    from accounts.selectors import get_customer_dashboard_context
    context = get_customer_dashboard_context(user=request.user)
    if not context:
        return redirect("accounts:dashboard")
        
    profile = context.profile
    address = context.default_address
    
    initial = {
        "name": request.user.get_full_name(),
        "email": request.user.email or request.user.username,
        "phone": profile.phone,
    }
    if address:
        initial.update({
            "address_line1": address.line1,
            "address_line2": address.line2,
            "city": address.city,
            "state": address.state,
            "pincode": address.pincode,
        })
        
    if request.method == "POST":
        form = CustomerProfileEditForm(request.POST, initial=initial)
        if form.is_valid():
            name = form.cleaned_data["name"]
            if name:
                parts = name.split(" ", 1)
                request.user.first_name = parts[0]
                request.user.last_name = parts[1] if len(parts) > 1 else ""
                request.user.save(update_fields=["first_name", "last_name"])
            
            profile.phone = form.cleaned_data["phone"]
            profile.save(update_fields=["phone", "updated_at"])
            
            line1 = form.cleaned_data["address_line1"]
            if line1:
                city = form.cleaned_data.get("city")
                line2 = form.cleaned_data.get("address_line2", "")
                state = form.cleaned_data.get("state", "")
                pincode = form.cleaned_data.get("pincode", "")
                
                if address:
                    address.line1 = line1
                    address.line2 = line2
                    if city:
                        address.city = city
                    address.state = state
                    address.pincode = pincode
                    address.save(update_fields=["line1", "line2", "city", "state", "pincode", "updated_at"])
                else:
                    from accounts.models import Address
                    from accounts.services import set_default_address
                    new_addr = Address.objects.create(
                        customer_profile=profile,
                        line1=line1,
                        line2=line2,
                        city=city if city else "",
                        state=state,
                        pincode=pincode,
                        label="Default Address"
                    )
                    set_default_address(customer_profile=profile, address_id=new_addr.pk)
                    
            from django.contrib import messages
            messages.success(request, "Profile updated successfully.")
            return redirect("accounts:dashboard")
    else:
        form = CustomerProfileEditForm(initial=initial)
        
    return render(request, "accounts/edit_profile.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def address_list_create_view(request: HttpRequest) -> HttpResponse:
    """List saved addresses or create a new one."""
    profile = request.user.customer_profile
    if request.method == "GET":
        page = int(request.GET.get("page", 1))
        data = get_saved_addresses(customer_profile=profile, page=page)
        return _success_response(
            {
                "addresses": [_serialize_address(a) for a in data["results"]],
                "pagination": {
                    "page": data["page"],
                    "total_count": data["total_count"],
                    "has_next": data["has_next"],
                },
            }
        )
    data = _json_body(request) or request.POST.dict()
    form = AddressForm(data)
    if not form.is_valid():
        return _error_response(str(form.errors), code="validation_error")
    address = create_address(
        customer_profile=profile,
        label=form.cleaned_data["label"],
        line1=form.cleaned_data["line1"],
        line2=form.cleaned_data.get("line2", ""),
        city=form.cleaned_data.get("city", ""),
        state=form.cleaned_data.get("state", ""),
        pincode=form.cleaned_data.get("pincode", ""),
        is_default=form.cleaned_data.get("is_default", False),
    )
    return _success_response({"address": _serialize_address(address)}, status=201)


@login_required
@require_http_methods(["PUT", "PATCH", "DELETE"])
def address_detail_view(request: HttpRequest, address_id: int) -> HttpResponse:
    """Update or delete a saved address."""
    profile = request.user.customer_profile
    if request.method == "DELETE":
        delete_address(customer_profile=profile, address_id=address_id)
        return _success_response()

    data = _json_body(request)
    form = AddressForm(data)
    if not form.is_valid():
        return _error_response(str(form.errors), code="validation_error")
    address = update_address(
        customer_profile=profile,
        address_id=address_id,
        label=form.cleaned_data["label"],
        line1=form.cleaned_data["line1"],
        line2=form.cleaned_data.get("line2", ""),
        city=form.cleaned_data.get("city", ""),
        state=form.cleaned_data.get("state", ""),
        pincode=form.cleaned_data.get("pincode", ""),
        is_default=form.cleaned_data.get("is_default", False),
    )
    address = get_address_by_id(address_id=address.pk, customer_profile=profile)
    return _success_response({"address": _serialize_address(address)})


@login_required
@require_GET
def payment_methods_list_view(request: HttpRequest) -> HttpResponse:
    """List saved payment methods (token metadata only)."""
    page = int(request.GET.get("page", 1))
    data = get_saved_payment_methods(customer_profile=request.user.customer_profile, page=page)
    return _success_response(
        {
            "payment_methods": [_serialize_payment_method(m) for m in data["results"]],
            "pagination": {
                "page": data["page"],
                "total_count": data["total_count"],
                "has_next": data["has_next"],
            },
        }
    )


@login_required
@require_POST
def payment_method_delete_view(request: HttpRequest, payment_method_id: int) -> HttpResponse:
    """Delete a saved payment method."""
    delete_saved_payment_method(
        customer_profile=request.user.customer_profile,
        payment_method_id=payment_method_id,
    )
    return _success_response()



@require_GET
def wishlist_shared_view(request: HttpRequest) -> HttpResponse:
    """Read-only shared wishlist via signed token — no auth required."""
    token = request.GET.get("token", "")
    view = get_wishlist(share_token=token)
    if view is None:
        return JsonResponse({"error": "Invalid or expired wishlist link."}, status=404)
    return JsonResponse(
        {
            "readonly": True,
            "items": [
                {"product_id": item.product_id, "name": item.product.name} for item in view.items
            ],
        }
    )


@login_required
@require_POST
def wishlist_add_view(request: HttpRequest) -> HttpResponse:
    """Add a product to the authenticated customer's wishlist."""
    from accounts.subscription_services import add_to_wishlist, get_or_create_wishlist

    product_id = int(request.POST.get("product_id", 0))
    wishlist = get_or_create_wishlist(request=request)
    add_to_wishlist(wishlist=wishlist, product_id=product_id)
    return JsonResponse({"status": "added"})

@require_POST
def wishlist_remove_view(request: HttpRequest) -> HttpResponse:
    """Remove a product from the customer's wishlist (guest or authenticated)."""
    from accounts.subscription_services import get_or_create_wishlist, remove_from_wishlist

    product_id = int(request.POST.get("product_id", 0))
    wishlist = get_or_create_wishlist(request=request)
    remove_from_wishlist(wishlist=wishlist, product_id=product_id)
    return redirect("accounts:wishlist")

@require_POST
def wishlist_shared_mutate_view(request: HttpRequest) -> HttpResponse:
    """Mutations via share token are forbidden."""
    token = request.POST.get("token", "")
    if token:
        return JsonResponse({"error": "Shared wishlists are read-only."}, status=403)
    return JsonResponse({"error": "Authentication required."}, status=401)

@require_GET
def wishlist_view(request: HttpRequest) -> HttpResponse:
    """Render the customer's wishlist page (guest or authenticated)."""
    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        profile = request.user.customer_profile
        view = get_wishlist(customer_profile=profile)
    else:
        session_key = request.session.session_key
        view = get_wishlist(session_key=session_key) if session_key else None
        if view and view.wishlist:
            request.session["guest_wishlist_id"] = view.wishlist.pk

    if view is None:
        response = render(request, "accounts/wishlist.html", {"items": []})
    else:
        response = render(request, "accounts/wishlist.html", {"wishlist": view.wishlist, "items": view.items})
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@login_required
@require_GET
def subscription_list_view(request: HttpRequest) -> HttpResponse:
    """List the authenticated customer's subscriptions."""
    profile = request.user.customer_profile
    subscriptions = get_customer_subscriptions(customer_profile=profile)
    return render(request, "accounts/subscription_list.html", {"subscriptions": subscriptions})


@login_required
@require_http_methods(["GET", "POST"])
def subscription_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        initial = {}
        product_id = request.GET.get("product_id")
        if product_id:
            initial["product_id"] = product_id
        return render(request, "accounts/subscription_create.html", {"form": SubscriptionCreateForm(initial=initial)})

    data = _json_body(request) or request.POST.dict()
    form = SubscriptionCreateForm(data)
    if not form.is_valid():
        if _wants_json(request):
            return _error_response(str(form.errors), code="validation_error")
        return render(
            request,
            "accounts/subscription_create.html",
            {"form": form, "errors": form.errors},
            status=400,
        )
    subscription = create_subscription(
        customer_profile=request.user.customer_profile,
        product_id=form.cleaned_data["product_id"],
        delivery_address_id=form.cleaned_data["delivery_address_id"],
        frequency=form.cleaned_data["frequency"],
        next_run_date=form.cleaned_data["next_run_date"],
        quantity=form.cleaned_data["quantity"],
        created_by=request.user,
    )
    if _wants_json(request):
        return _success_response({"subscription_id": subscription.pk}, status=201)
    return redirect("accounts:subscription-list")


@login_required
@require_POST
def subscription_pause_view(request: HttpRequest, subscription_id: int) -> HttpResponse:
    """Pause a subscription owned by the current customer."""
    subscription = get_customer_subscription_by_id(
        subscription_id=subscription_id, customer_profile=request.user.customer_profile
    )
    if subscription is None:
        return _error_response("Subscription not found.", status=404)
    pause_subscription(subscription=subscription)
    return _success_response()


@login_required
@require_POST
def subscription_resume_view(request: HttpRequest, subscription_id: int) -> HttpResponse:
    """Resume a paused subscription owned by the current customer."""
    subscription = get_customer_subscription_by_id(
        subscription_id=subscription_id, customer_profile=request.user.customer_profile
    )
    if subscription is None:
        return _error_response("Subscription not found.", status=404)
    resume_subscription(subscription=subscription)
    return _success_response()


@login_required
@require_POST
def subscription_cancel_view(request: HttpRequest, subscription_id: int) -> HttpResponse:
    """Cancel a subscription owned by the current customer."""
    subscription = get_customer_subscription_by_id(
        subscription_id=subscription_id, customer_profile=request.user.customer_profile
    )
    if subscription is None:
        return _error_response("Subscription not found.", status=404)
    cancel_subscription(subscription=subscription)
    return _success_response()


@never_cache
@require_http_methods(["GET", "POST"])
def email_otp_request_view(request: HttpRequest) -> HttpResponse:
    """Request a passwordless login OTP for General Customers."""
    next_url = request.GET.get("next") or request.POST.get("next", "")

    if request.user.is_authenticated:
        return redirect(next_url or "accounts:dashboard")
    
    #if no next_url is specified, look at the http referer
    if not next_url:
        referer = request.META.get("HTTP_REFERER", "")
        if referer:
            from urllib.parse import urlparse
            try:
                parsed_url = urlparse(referer)
                #avoid redirecting back to login/registration pages themselves to prevent redirect loops
                if not any(path in parsed_url.path for path in ("/accounts/login/", "/accounts/verify-email-otp/", "/accounts/register/")):
                    next_url = referer
            except Exception:
                pass

    if request.method == "GET":
        import time
        return render(request, "accounts/email_otp_request.html", {"form": EmailOTPRequestForm(), "next": next_url, "captcha_bust": int(time.time() * 1000)})

    data = _json_body(request) or request.POST.dict()
    form = EmailOTPRequestForm(data)
    if not form.is_valid():
        import time
        return render(request, "accounts/email_otp_request.html", {"form": form, "next": next_url, "captcha_bust": int(time.time() * 1000)}, status=400)

    from core import image_captcha
    try:
        image_captcha.verify_answer(
            request,
            image_captcha.extract_image_captcha_value(request),
            scope='customer_login',
            ip_address=request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')
        )
    except ValidationError as exc:
        msg = exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
        form.add_error(None, msg)
        import time
        return render(request, "accounts/email_otp_request.html", {"form": form, "next": next_url, "captcha_bust": int(time.time() * 1000)}, status=400)

    email = form.cleaned_data["email"]
    try:
        request_email_otp(email=email, purpose=OTPPurpose.LOGIN)
    except Exception as exc:
        form.add_error(None, f"Error generating OTP: {str(exc)}")
        import time
        return render(request, "accounts/email_otp_request.html", {"form": form, "next": next_url, "captcha_bust": int(time.time() * 1000)}, status=400)

    from django.utils.http import urlencode
    query_params = urlencode({"email": email, "purpose": "login", "next": next_url})
    return redirect(f"/accounts/verify-email-otp/?{query_params}")


@never_cache
@require_http_methods(["GET", "POST"])
def email_otp_verify_view(request: HttpRequest) -> HttpResponse:
    """Verify email 4-digit OTP for customer login."""
    email = request.GET.get("email") or request.POST.get("email", "")
    purpose = request.GET.get("purpose") or request.POST.get("purpose", OTPPurpose.LOGIN)
    next_url = request.GET.get("next") or request.POST.get("next", "")

    if request.user.is_authenticated:
        return redirect(next_url or "accounts:dashboard")

    if request.method == "GET":
        form = EmailOTPVerifyForm(initial={"email": email})
        return render(
            request, 
            "accounts/email_otp_verify.html", 
            {"form": form, "email": email, "purpose": purpose, "next": next_url}
        )

    data = _json_body(request) or request.POST.dict()
    form = EmailOTPVerifyForm(data)
    if not form.is_valid():
        return render(
            request, 
            "accounts/email_otp_verify.html", 
            {"form": form, "email": email, "purpose": purpose, "next": next_url}, 
            status=400
        )

    otp_code = form.cleaned_data["otp_code"]

    try:
        verify_email_otp(email=email, otp_code=otp_code, purpose=purpose)
    except Exception as exc:
        form.add_error("otp_code", str(exc))
        return render(
            request, 
            "accounts/email_otp_verify.html", 
            {"form": form, "email": email, "purpose": purpose, "next": next_url}, 
            status=400
        )

    profile = login_or_create_customer_by_email(email=email)
    login(request, profile.user, backend="django.contrib.auth.backends.ModelBackend")

    if next_url:
        from django.utils.http import url_has_allowed_host_and_scheme
        if url_has_allowed_host_and_scheme(url=next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
    return redirect("accounts:dashboard")


@require_POST
def resend_email_otp_view(request: HttpRequest) -> HttpResponse:
    """Resend email OTP directly within the verify screen without requiring captcha re-submission."""
    data = _json_body(request) or request.POST.dict()
    email = (data.get("email") or "").strip()
    purpose = data.get("purpose") or OTPPurpose.LOGIN

    if not email:
        return _error_response("Email address is required.", status=400)

    try:
        request_email_otp(email=email, purpose=purpose)
    except Exception as exc:
        msg = getattr(exc, "messages", [str(exc)])[0] if hasattr(exc, "messages") else str(exc)
        if _wants_json(request):
            return _error_response(msg, status=400)
        from django.contrib import messages
        messages.error(request, msg)
        from django.utils.http import urlencode
        return redirect(f"/accounts/verify-email-otp/?{urlencode({'email': email, 'purpose': purpose})}")

    if _wants_json(request):
        return _success_response({"message": "Verification code sent successfully."})

    from django.contrib import messages
    messages.success(request, "A new verification code has been sent to your email.")
    from django.utils.http import urlencode
    next_url = data.get("next") or request.GET.get("next", "")
    params = {"email": email, "purpose": purpose}
    if next_url:
        params["next"] = next_url
    return redirect(f"/accounts/verify-email-otp/?{urlencode(params)}")


@require_http_methods(["GET"])
def customer_invoice_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the HTML invoice for a customer order."""
    from orders.models import Order
    from core.models import SiteSettings
    from django.shortcuts import get_object_or_404
    
    order = get_object_or_404(
        Order.objects.select_related("customer_profile__user", "currency", "cart"), 
        pk=pk
    )
    
    #security check to prevent unauthorized invoice downloads
    if request.user.is_authenticated:
        if order.customer_profile and order.customer_profile.user != request.user:
            from django.http import Http404
            raise Http404("Invoice not found.")
    else:
        session_key = request.session.session_key
        allowed_keys = {session_key, f"bn_{session_key}"[:40]} if session_key else set()
        cart_key = order.cart.session_key if order.cart else None
        if not cart_key or cart_key not in allowed_keys:
            from django.http import Http404
            raise Http404("Invoice not found.")

    context = {
        "order": order,
        "site_settings": SiteSettings.objects.first(),
    }
    return render(request, "shared/order_invoice.html", context)
