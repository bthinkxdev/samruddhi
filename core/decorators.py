"""Reusable view decorators for RBAC and rate limiting."""

from __future__ import annotations

import functools
from typing import Callable

from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect


def role_required(*group_names: str, login_url: str | None = None):
    """
    Require authenticated user membership in at least one named Django group.

    Returns 403 JSON for API-style views and redirect for browser views.
    """

    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if not request.user.is_authenticated:
                if request.headers.get("Accept", "").startswith("application/json"):
                    return JsonResponse(
                        {"success": False, "code": "auth_required", "message": "Login required."},
                        status=401,
                    )
                return redirect_to_login(request.get_full_path(), login_url=login_url)

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            if not request.user.groups.filter(name__in=group_names).exists():
                if request.headers.get("Accept", "").startswith("application/json"):
                    return JsonResponse(
                        {
                            "success": False,
                            "code": "forbidden",
                            "message": "Insufficient permissions.",
                        },
                        status=403,
                    )
                return redirect("accounts:dashboard")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def rate_limit(
    *,
    key_prefix: str,
    max_requests: int,
    window_seconds: int,
    identifier: Callable[[HttpRequest], str],
):
    """
    Redis/cache-backed request rate limiter for views.

    Raises HTTP 429 when the per-identifier quota is exceeded within the window.
    """

    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            ident = identifier(request)
            cache_key = f"ratelimit:{key_prefix}:{ident}"
            count = cache.get(cache_key, 0)
            if count >= max_requests:
                return JsonResponse(
                    {
                        "success": False,
                        "code": "rate_limited",
                        "message": "Too many requests. Please try again later.",
                    },
                    status=429,
                )
            try:
                cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, 1, timeout=window_seconds)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
