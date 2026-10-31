"""IP allowlist middleware for the admin dashboard."""

from __future__ import annotations

import ipaddress
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden

logger = logging.getLogger(__name__)


def get_client_ip(request: HttpRequest) -> str:
    """
    Best-effort real client IP behind a reverse proxy.

    Trusts the first address in X-Forwarded-For when present (set by the
    nginx/proxy in front of prod/staging — see SECURE_PROXY_SSL_HEADER in
    those settings modules) and falls back to REMOTE_ADDR for direct
    connections (dev, or no proxy in front).
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _ip_allowed(ip: str, allowed: list[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in allowed:
        entry = entry.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            logger.warning("DASHBOARD_ALLOWED_IPS has an invalid entry: %r", entry)
    return False


def _db_allowed_ips() -> list[str]:
    """
    Read SiteSettings.dashboard_allowed_ips (set from the dashboard Settings
    page), tolerating a missing table — e.g. before migrations have run.
    """
    try:
        from core.services import get_site_settings

        raw = get_site_settings().dashboard_allowed_ips
    except Exception:
        return []
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


class DashboardIPAllowlistMiddleware:
    """
    Restrict /dashboard/ (including the login page) to a configured IP allowlist.

    The allowlist can come from two places, merged together: the
    DASHBOARD_ALLOWED_IPS env var (settings.DASHBOARD_ALLOWED_IPS), and the
    "Dashboard allowed IPs" field on the dashboard's own Settings page
    (SiteSettings.dashboard_allowed_ips). Either one is enough to populate it.

    A no-op whenever both are empty, which is the default — the restriction
    only activates once at least one is explicitly configured, so it can't
    silently lock everyone (including the real admin) out.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.startswith("/dashboard/"):
            allowed = list(getattr(settings, "DASHBOARD_ALLOWED_IPS", [])) + _db_allowed_ips()
            if allowed:
                ip = get_client_ip(request)
                if not _ip_allowed(ip, allowed):
                    logger.warning(
                        "Blocked dashboard access from disallowed IP %s (path=%s)", ip, request.path
                    )
                    return HttpResponseForbidden("Access to the admin dashboard is restricted.")
        return self.get_response(request)
