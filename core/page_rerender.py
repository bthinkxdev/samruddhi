"""Re-render the current storefront page shell for HTMX preference updates."""

from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.test import RequestFactory
from django.urls import Resolver404, resolve
from django.utils import translation


def htmx_current_path(request: HttpRequest) -> str:
    """Return the path (+ query string) of the page that initiated the HTMX request."""
    raw = request.headers.get("HX-Current-URL") or request.META.get("HTTP_REFERER", "/")
    parsed = urlparse(raw)
    if parsed.query:
        return f"{parsed.path}?{parsed.query}"
    return parsed.path or "/"


def is_htmx_request(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _strip_language_prefix(path: str) -> str:
    """Map localized URL paths back to canonical routes used by resolve()."""
    for code, _label in settings.LANGUAGES:
        if code == settings.LANGUAGE_CODE:
            continue
        prefix = f"/{code}"
        if path == prefix:
            return "/"
        if path.startswith(f"{prefix}/"):
            return path[len(prefix) :]
    return path


def _resolve_target(target_path: str):
    """Resolve a storefront path independent of the active translation language."""
    path_only = _strip_language_prefix(urlparse(target_path).path or "/")
    with translation.override(settings.LANGUAGE_CODE):
        try:
            return resolve(path_only), path_only
        except Resolver404:
            return resolve("/"), "/"


def _dispatch_inner_get(
    request: HttpRequest,
    target_path: str,
    *,
    language: str | None,
) -> HttpResponse:
    resolved, canonical_path = _resolve_target(target_path)
    query = urlparse(target_path).query
    inner_path = f"{canonical_path}?{query}" if query else canonical_path

    factory = RequestFactory()
    inner = factory.get(inner_path)
    inner.session = request.session
    inner.user = getattr(request, "user", AnonymousUser())
    inner.COOKIES = request.COOKIES.copy()
    inner.META["HTTP_X_SHELL_RERENDER"] = "true"

    with translation.override(language or settings.LANGUAGE_CODE):
        inner.LANGUAGE_CODE = translation.get_language()
        response = resolved.func(inner, *resolved.args, **resolved.kwargs)

    if isinstance(response, HttpResponseRedirect):
        redirect_path = urlparse(response.url).path
        redirect_query = urlparse(response.url).query
        redirect_target = f"{redirect_path}?{redirect_query}" if redirect_query else redirect_path
        return _dispatch_inner_get(request, redirect_target, language=language)

    if isinstance(response, TemplateResponse):
        response.render()

    return response


def rerender_app_shell(request: HttpRequest) -> HttpResponse:
    """
    Dispatch a GET to the current URL and return only the app-shell fragment.

    Approach (a): one HTMX round trip re-renders header, translated content, footer,
    and prices for the active session language/currency without a browser navigation.
    """
    target_path = htmx_current_path(request)
    language = request.session.get("django_language")
    return _dispatch_inner_get(request, target_path, language=language)
