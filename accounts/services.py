"""Write operations and business rules for the accounts app."""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any, Optional

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from accounts.exceptions import (
    GoogleAuthError,
    OTPAlreadyUsedError,
    OTPExpiredError,
    OTPMaxAttemptsError,
    OTPMismatchError,
    OTPRateLimitError,
    OTPVerificationError,
)
from accounts.models import (
    Address,
    CustomerProfile,
    OTPPurpose,
    OTPRequest,
    SavedPaymentMethod,
    EmailOTPRequest,
)
from core.selectors import get_default_currency
from core.services import get_site_settings
from notifications.services import create_notification

UserModel = get_user_model()

GUEST_CHECKOUT_SALT = "accounts.guest-checkout"
OTP_RATE_LIMIT_KEY = "accounts:otp_rate:{phone}"
OTP_RATE_LIMIT_MAX = 3
OTP_RATE_LIMIT_WINDOW = 600
LOGIN_RATE_LIMIT_KEY = "accounts:login_rate:{identifier}"
LOGIN_RATE_LIMIT_MAX = 10
LOGIN_RATE_LIMIT_WINDOW = 600


def _normalize_phone(phone: str) -> str:
    """Strip whitespace from a phone number."""
    return phone.strip()


def _otp_rate_limit_key(phone: str) -> str:
    return OTP_RATE_LIMIT_KEY.format(phone=_normalize_phone(phone))


def _check_otp_rate_limit(*, phone: str) -> None:
    """Raise OTPRateLimitError if the phone has exceeded the OTP request quota."""
    key = _otp_rate_limit_key(phone)
    count = cache.get(key, 0)
    if count >= OTP_RATE_LIMIT_MAX:
        raise OTPRateLimitError(
            f"Maximum {OTP_RATE_LIMIT_MAX} OTP requests per 10 minutes exceeded."
        )


def _increment_otp_rate_limit(*, phone: str) -> None:
    """Increment the Redis-backed OTP request counter for a phone number."""
    key = _otp_rate_limit_key(phone)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=OTP_RATE_LIMIT_WINDOW)


def _login_rate_limit_key(*, identifier: str) -> str:
    return LOGIN_RATE_LIMIT_KEY.format(identifier=identifier.strip().lower())


def _check_login_rate_limit(*, identifier: str) -> None:
    """Raise OTPRateLimitError when login attempts exceed quota (reused exception type)."""
    key = _login_rate_limit_key(identifier=identifier)
    count = cache.get(key, 0)
    if count >= LOGIN_RATE_LIMIT_MAX:
        raise OTPRateLimitError(
            f"Maximum {LOGIN_RATE_LIMIT_MAX} login attempts per 10 minutes exceeded."
        )


def _increment_login_rate_limit(*, identifier: str) -> None:
    key = _login_rate_limit_key(identifier=identifier)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=LOGIN_RATE_LIMIT_WINDOW)


def _generate_otp_code() -> str:
    """Return a cryptographically secure 6-digit OTP."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _get_active_otp(*, phone: str, purpose: str) -> Optional[OTPRequest]:
    """Return the latest unused OTP request for a phone and purpose."""
    return (
        OTPRequest.objects.filter(
            phone=_normalize_phone(phone),
            purpose=purpose,
            is_used=False,
        )
        .order_by("-created_at")
        .first()
    )


def request_otp(*, phone: str, purpose: str, channel: str = "sms") -> OTPRequest:
    """
    Create a hashed OTP request and dispatch the code via SMS or WhatsApp.

    Rate-limited to 3 requests per phone per 10 minutes via Redis (not DB).
    Params:
        phone: Target phone number.
        purpose: OTPPurpose value (login, signup, password_reset, checkout_phone).
        channel: "sms" (default, async via Celery) or "whatsapp" (synchronous —
            the caller is a customer actively waiting for the code).
    Returns:
        Created OTPRequest instance (plaintext OTP is only sent via the channel).
    Raises:
        OTPRateLimitError: When the Redis rate limit is exceeded.
    """
    normalized_phone = _normalize_phone(phone)
    _check_otp_rate_limit(phone=normalized_phone)
    _increment_otp_rate_limit(phone=normalized_phone)

    otp_code = _generate_otp_code()
    expires_at = timezone.now() + timedelta(seconds=settings.ACCOUNTS_OTP_EXPIRY_SECONDS)

    with transaction.atomic():
        otp_request = OTPRequest.objects.create(
            phone=normalized_phone,
            otp_hash=make_password(otp_code),
            purpose=purpose,
            expires_at=expires_at,
        )

    # dispatched outside the transaction — a synchronous WhatsApp send should not
    # hold the DB connection open for the duration of an external HTTP round-trip.
    if channel == "whatsapp":
        from whatsapp.services import send_otp as send_whatsapp_otp

        send_whatsapp_otp(normalized_phone, otp_code)
    else:
        from accounts.tasks import send_otp_sms

        send_otp_sms.delay(phone=normalized_phone, otp_code=otp_code)
    return otp_request


def verify_otp(*, phone: str, otp_code: str, purpose: str) -> OTPRequest:
    """
    Validate an OTP and mark it as used on success.

    Failed attempts are persisted outside a wrapping atomic block so that
    attempt_count increments survive raised OTPMismatchError.

    Params:
        phone: Phone number the OTP was sent to.
        otp_code: Plaintext OTP submitted by the user.
        purpose: OTPPurpose value.
    Returns:
        The verified OTPRequest instance.
    Raises:
        OTPExpiredError: OTP past expiry.
        OTPAlreadyUsedError: OTP already consumed.
        OTPMaxAttemptsError: Too many failed attempts.
        OTPMismatchError: Code does not match hash.
    """
    normalized_phone = _normalize_phone(phone)
    otp_request = (
        OTPRequest.objects.filter(phone=normalized_phone, purpose=purpose)
        .order_by("-created_at")
        .first()
    )
    if otp_request is None:
        raise OTPMismatchError("No active OTP found for this phone and purpose.")

    if otp_request.is_used:
        raise OTPAlreadyUsedError("This OTP has already been used.")

    if timezone.now() > otp_request.expires_at:
        raise OTPExpiredError("This OTP has expired.")

    max_attempts = settings.ACCOUNTS_OTP_MAX_ATTEMPTS
    if otp_request.attempt_count >= max_attempts:
        raise OTPMaxAttemptsError(f"Maximum {max_attempts} verification attempts exceeded.")

    if not check_password(otp_code, otp_request.otp_hash):
        OTPRequest.objects.filter(pk=otp_request.pk).update(
            attempt_count=otp_request.attempt_count + 1,
        )
        otp_request.refresh_from_db()
        if otp_request.attempt_count >= max_attempts:
            raise OTPMaxAttemptsError(f"Maximum {max_attempts} verification attempts exceeded.")
        raise OTPMismatchError("The OTP code is incorrect.")

    otp_request.is_used = True
    otp_request.save(update_fields=["is_used", "updated_at"])
    return otp_request


@transaction.atomic
def register_customer_email(*, email: str, password: str, name: str) -> CustomerProfile:
    """
    Register a new customer with email and password credentials.
    Upgrades a shadow account (from guest checkout) if it exists.

    Params:
        email: Unique email address.
        password: Raw password (hashed by Django).
        name: Full name split into first/last.
    Returns:
        CustomerProfile with linked User.
    """
    currency = get_default_currency()
    if currency is None:
        raise ValueError("No default currency configured.")

    name_parts = name.strip().split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    normalized_email = email.strip().lower()

    user = UserModel.objects.filter(email=normalized_email).first()
    if user:
        if user.has_usable_password():
            raise ValueError("Email is already registered.")
        user.set_password(password)
        if not user.first_name and not user.last_name:
            user.first_name = first_name
            user.last_name = last_name
        user.save()
    else:
        user = UserModel.objects.create_user(
            username=normalized_email,
            email=normalized_email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

    profile, created = CustomerProfile.objects.get_or_create(
        user=user,
        defaults={"preferred_currency": currency},
    )
    return profile


def ensure_customer_profile_for_user(*, user: User) -> CustomerProfile:
    """
    Return or create a CustomerProfile for any authenticated user.

    Used when corporate users place retail orders via the shared checkout path.
    """
    profile = getattr(user, "customer_profile", None)
    if profile is not None:
        return profile
    currency = get_default_currency()
    if currency is None:
        raise ValueError("No default currency configured.")

    return CustomerProfile.objects.create(user=user, preferred_currency=currency, phone="")


def authenticate_email(*, email: str, password: str) -> Optional[User]:
    """
    Authenticate a user by email and password.

    Params:
        email: Registered email address.
        password: Raw password.
    Returns:
        User instance on success, None on failure.
    """
    user = authenticate(username=email, password=password)
    return user


@transaction.atomic
def authenticate_google(*, google_id_token: str) -> CustomerProfile:
    """
    Verify a Google ID token and return or create the customer profile.

    Params:
        google_id_token: Google Sign-In JWT from the client.
    Returns:
        CustomerProfile for the authenticated Google user.
    Raises:
        GoogleAuthError: Token verification failed.
    """
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        id_info = id_token.verify_oauth2_token(
            google_id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        raise GoogleAuthError("Invalid Google ID token.") from exc

    email = id_info.get("email")
    if not email:
        raise GoogleAuthError("Google account has no email address.")

    given_name = id_info.get("given_name", "")
    family_name = id_info.get("family_name", "")

    user, created = UserModel.objects.get_or_create(
        username=email,
        defaults={
            "email": email,
            "first_name": given_name,
            "last_name": family_name,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])

    profile, profile_created = CustomerProfile.objects.get_or_create(
        user=user,
        defaults={"preferred_currency": get_default_currency()},
    )
    if profile_created and profile.preferred_currency is None:
        profile.preferred_currency = get_default_currency()
        profile.save(update_fields=["preferred_currency", "updated_at"])

    return profile


def create_guest_checkout_token(*, cart_id: str) -> str:
    """
    Create a stateless signed token for guest checkout — no DB row required.

    Params:
        cart_id: Opaque cart session identifier.
    Returns:
        Signed token string.
    """
    return signing.dumps({"cart_id": cart_id}, salt=GUEST_CHECKOUT_SALT)


def verify_guest_checkout_token(*, token: str) -> dict[str, Any]:
    """
      Verify and decode a guest checkout token.

      Params:
          token: Signed token from create_guest_checkout_token.
      Returns:
          Decoded payload dict.
    Raises:
          signing.BadSignature: When the token is invalid or tampered.
    """
    return signing.loads(
        token, salt=GUEST_CHECKOUT_SALT, max_age=settings.ACCOUNTS_GUEST_TOKEN_MAX_AGE
    )


@transaction.atomic
def set_default_address(*, customer_profile: CustomerProfile, address_id: int) -> Address:
    """
    Atomically set one address as the customer's default.

    Uses select_for_update to prevent concurrent calls leaving two defaults.
    Params:
        customer_profile: Owner profile.
        address_id: Primary key of the address to promote.
    Returns:
        Updated Address instance.
    """
    addresses = Address.objects.select_for_update().filter(customer_profile=customer_profile)
    address = addresses.get(pk=address_id)
    addresses.exclude(pk=address_id).update(is_default=False)
    address.is_default = True
    address.save(update_fields=["is_default", "updated_at"])
    customer_profile.default_address = address
    customer_profile.save(update_fields=["default_address", "updated_at"])
    return address


@transaction.atomic
def update_address(
    *,
    customer_profile: CustomerProfile,
    address_id: int,
    label: str,
    line1: str,
    line2: str,
    city: str,
    state: str = "",
    pincode: str = "",
    is_default: bool = False,
) -> Address:
    """
    Update an existing address and optionally promote it to default.

    Params:
        customer_profile: Owner profile.
        address_id: Primary key of the address to update.
        label: Address label.
        line1: Primary address line.
        line2: Secondary address line.
        city: City name.
        state: State or province.
        pincode: Postal or PIN code.
        is_default: When True, demotes other defaults atomically.
    Returns:
        Updated Address instance.
    """
    address = Address.objects.get(pk=address_id, customer_profile=customer_profile)
    address.label = label
    address.line1 = line1
    address.line2 = line2
    address.city = city
    address.state = state
    address.pincode = pincode
    address.save(update_fields=["label", "line1", "line2", "city", "state", "pincode", "updated_at"])
    if is_default:
        return set_default_address(customer_profile=customer_profile, address_id=address.pk)
    return address


@transaction.atomic
def create_address(
    *,
    customer_profile: CustomerProfile,
    label: str,
    line1: str,
    line2: str,
    city: str,
    state: str = "",
    pincode: str = "",
    is_default: bool = False,
) -> Address:
    """
    Create a new address for a customer, optionally setting it as default.

    Params:
        customer_profile: Owner profile.
        label: Address label.
        line1: Primary address line.
        line2: Secondary address line.
        city: City name.
        state: State or province.
        pincode: Postal or PIN code.
        is_default: When True, demotes other defaults atomically.
    Returns:
        Created Address instance.
    """
    address = Address.objects.create(
        customer_profile=customer_profile,
        label=label,
        line1=line1,
        line2=line2,
        city=city,
        state=state,
        pincode=pincode,
        is_default=False,
    )
    if is_default:
        return set_default_address(customer_profile=customer_profile, address_id=address.pk)
    return address


@transaction.atomic
def delete_address(*, customer_profile: CustomerProfile, address_id: int) -> None:
    """
    Delete an address and clear profile.default_address if it pointed here.

    Params:
        customer_profile: Owner profile.
        address_id: Primary key of the address to remove.
    """
    address = Address.objects.get(pk=address_id, customer_profile=customer_profile)
    if customer_profile.default_address_id == address.pk:
        customer_profile.default_address = None
        customer_profile.save(update_fields=["default_address", "updated_at"])
    address.delete()


@transaction.atomic
def delete_saved_payment_method(
    *, customer_profile: CustomerProfile, payment_method_id: int
) -> None:
    """
    Delete a saved payment method (token only — no raw card data).

    Params:
        customer_profile: Owner profile.
        payment_method_id: Primary key of the saved method.
    """
    SavedPaymentMethod.objects.filter(
        pk=payment_method_id,
        customer_profile=customer_profile,
    ).delete()


PHONE_PLACEHOLDER_EMAIL_DOMAIN = "phone.samruddhi.local"


def is_placeholder_email(email: str | None) -> bool:
    """True for the synthetic email given to phone-only customers (never shown to users)."""
    return bool(email) and email.lower().endswith("@" + PHONE_PLACEHOLDER_EMAIL_DOMAIN)


@transaction.atomic
def login_or_create_customer_by_phone(*, phone: str) -> CustomerProfile:
    """
    Find or create a customer profile after successful OTP phone verification.

    Params:
        phone: Verified phone number.
    Returns:
        CustomerProfile with phone_verified=True.
    """
    normalized_phone = _normalize_phone(phone)
    profile = CustomerProfile.objects.filter(phone=normalized_phone).select_related("user").first()
    if profile is not None:
        profile.phone_verified = True
        profile.save(update_fields=["phone_verified", "updated_at"])
        return profile

    currency = get_default_currency()
    email = f"{normalized_phone.replace('+', '')}@{PHONE_PLACEHOLDER_EMAIL_DOMAIN}"
    user = UserModel(username=email, email=email)
    user.set_unusable_password()
    user.save()
    return CustomerProfile.objects.create(
        user=user,
        phone=normalized_phone,
        phone_verified=True,
        preferred_currency=currency,
        # the email above is a synthetic placeholder, not a real address —
        # never let notification dispatch treat it as one.
        notify_via_email=False,
    )


@transaction.atomic
def reset_password_with_otp(*, phone: str, otp_code: str, new_password: str) -> User:
    """
    Reset a user's password after OTP verification for PASSWORD_RESET purpose.

    Params:
        phone: Phone number tied to the customer profile.
        otp_code: Verified OTP code.
        new_password: New raw password.
    Returns:
        Updated User instance.
    """
    verify_otp(phone=phone, otp_code=otp_code, purpose=OTPPurpose.PASSWORD_RESET)
    profile = CustomerProfile.objects.select_related("user").get(phone=_normalize_phone(phone))
    user = profile.user
    user.set_password(new_password)
    user.save(update_fields=["password"])
    return user



#helper to generate a cryptographically secure 4-digit OTP code
def _generate_email_otp_code() -> str:
    """Return a cryptographically secure 4-digit OTP."""
    import secrets
    return f"{secrets.randbelow(10000):04d}"


@transaction.atomic
def request_email_otp(*, email: str, purpose: str) -> EmailOTPRequest:
    """Create a hashed email OTP request and dispatch it synchronously (single thread)."""
    from notifications.services import send_email
    from accounts.forms import validate_real_email_domain

    normalized_email = email.strip().lower()
    validate_real_email_domain(normalized_email)
    
    #rate limit check (using the email address as the key)
    rate_limit_key = f"accounts:email_otp_rate:{normalized_email}"
    count = cache.get(rate_limit_key, 0)
    if count >= OTP_RATE_LIMIT_MAX:
        raise OTPRateLimitError("Maximum OTP requests exceeded. Please try again later.")
    
    try:
        cache.incr(rate_limit_key)
    except ValueError:
        cache.set(rate_limit_key, 1, timeout=OTP_RATE_LIMIT_WINDOW)

    existing_request = (
        EmailOTPRequest.objects.filter(
            email=normalized_email,
            purpose=purpose,
            is_used=False,
            expires_at__gt=timezone.now()
        )
        .order_by("-created_at")
        .first()
    )
    raw_otp_cache_key = f"accounts:raw_email_otp:{normalized_email}:{purpose}"
    existing_code = cache.get(raw_otp_cache_key)

    if existing_request and existing_code:
        send_email(
            email=normalized_email,
            subject=f"Your {get_site_settings().site_name} Verification Code",
            message=f"Your verification code is: {existing_code}. It is valid for 5 minutes.",
        )
        return existing_request

    otp_code = _generate_email_otp_code()
    expires_at = timezone.now() + timedelta(seconds=settings.ACCOUNTS_OTP_EXPIRY_SECONDS)

    otp_request = EmailOTPRequest.objects.create(
        email=normalized_email,
        otp_hash=make_password(otp_code),
        purpose=purpose,
        expires_at=expires_at,
    )

    cache.set(raw_otp_cache_key, otp_code, timeout=settings.ACCOUNTS_OTP_EXPIRY_SECONDS)

    send_email(
        email=normalized_email,
        subject=f"Your {get_site_settings().site_name} Verification Code",
        message=f"Your verification code is: {otp_code}. It is valid for 5 minutes.",
    )
    return otp_request


def verify_email_otp(*, email: str, otp_code: str, purpose: str) -> EmailOTPRequest:
    """Validate an email OTP and mark it as consumed on success."""
    normalized_email = email.strip().lower()
    otp_request = (
        EmailOTPRequest.objects.filter(email=normalized_email, purpose=purpose)
        .order_by("-created_at")
        .first()
    )
    if otp_request is None:
        raise OTPVerificationError("No active OTP found for this email and purpose.")

    if otp_request.is_used:
        raise OTPVerificationError("This OTP has already been used.")

    if timezone.now() > otp_request.expires_at:
        raise OTPVerificationError("This OTP has expired.")

    max_attempts = settings.ACCOUNTS_OTP_MAX_ATTEMPTS
    if otp_request.attempt_count >= max_attempts:
        raise OTPVerificationError("Maximum verification attempts exceeded.")

    if not check_password(otp_code, otp_request.otp_hash):
        EmailOTPRequest.objects.filter(pk=otp_request.pk).update(
            attempt_count=otp_request.attempt_count + 1,
        )
        otp_request.refresh_from_db()
        if otp_request.attempt_count >= max_attempts:
            raise OTPVerificationError("Maximum verification attempts exceeded.")
        raise OTPVerificationError("The OTP code is incorrect.")

    otp_request.is_used = True
    otp_request.save(update_fields=["is_used", "updated_at"])
    raw_otp_cache_key = f"accounts:raw_email_otp:{normalized_email}:{purpose}"
    cache.delete(raw_otp_cache_key)
    return otp_request


@transaction.atomic
def login_or_create_customer_by_email(*, email: str, name: str = "") -> CustomerProfile:
    """Find or create a CustomerProfile after successful OTP email verification."""
    normalized_email = email.strip().lower()
    
    #check if a profile exists
    profile = CustomerProfile.objects.filter(user__email=normalized_email).select_related("user").first()
    if profile is not None:
        if name:
            name_parts = name.strip().split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            if profile.user.first_name != first_name or profile.user.last_name != last_name:
                profile.user.first_name = first_name
                profile.user.last_name = last_name
                profile.user.save(update_fields=["first_name", "last_name"])
        return profile

    currency = get_default_currency()
    if currency is None:
        raise ValueError("No default currency configured.")

    #get or create User
    user = UserModel.objects.filter(email=normalized_email).first()
    if user is None:
        user = UserModel(username=normalized_email, email=normalized_email)
        if name:
            name_parts = name.strip().split(" ", 1)
            user.first_name = name_parts[0]
            user.last_name = name_parts[1] if len(name_parts) > 1 else ""
        user.set_unusable_password()
        user.save()
    else:
        if name:
            name_parts = name.strip().split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            if user.first_name != first_name or user.last_name != last_name:
                user.first_name = first_name
                user.last_name = last_name
                user.save(update_fields=["first_name", "last_name"])

    #create customerprofile
    profile, created = CustomerProfile.objects.get_or_create(
        user=user,
        defaults={"preferred_currency": currency},
    )
    return profile

