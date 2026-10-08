#!/usr/bin/env python
"""Generate layered-architecture scaffold files for all Django apps."""

from __future__ import annotations

from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

APPS: dict[str, str] = {
    "accounts": "user authentication, profiles, and address book",
    "catalog": "product catalog, collections, and inventory",
    "gifting": "plug-and-play gift customization via ContentType",
    "cart": "shopping cart session and line-item management",
    "checkout": "checkout flow, delivery slot selection, and order preview",
    "orders": "order lifecycle, status tracking, and order history",
    "payments": "payment gateway integration and transaction records",
    "delivery": "delivery zones, slots, and fulfillment logistics",
    "corporate": "B2B corporate accounts and bulk ordering",
    "marketing": "promotions, coupons, and campaign management",
    "cms": "CMS pages, banners, and editorial content",
    "notifications": "email, SMS, and WhatsApp notification dispatch",
    "reports": "analytics dashboards and aggregated reporting",
}

FILE_TEMPLATES: dict[str, str] = {
    "models.py": (
        '"""Data layer for the {app} app — models only, no business logic."""\n\n'
        "from __future__ import annotations\n\n"
        "# Models will be added in subsequent phases.\n"
    ),
    "selectors.py": (
        '"""Read-only query functions for the {app} app; views must not call the ORM directly."""\n\n'
        "from __future__ import annotations\n\n"
        "# Selectors will be added in subsequent phases.\n"
    ),
    "services.py": (
        '"""Write operations and business rules for the {app} app."""\n\n'
        "from __future__ import annotations\n\n"
        "# Services will be added in subsequent phases.\n"
    ),
    "forms.py": (
        '"""Django forms for the {app} app."""\n\n'
        "from __future__ import annotations\n\n"
        "# Forms will be added in subsequent phases.\n"
    ),
    "serializers.py": (
        '"""DRF-style serializers placeholder for the {app} app (Phase 1 scaffold)."""\n\n'
        "from __future__ import annotations\n\n"
        "# Serializers will be added when DRF is introduced in a later phase.\n"
    ),
    "views.py": (
        '"""HTTP views for the {app} app; thin request parsing delegating to selectors/services."""\n\n'
        "from __future__ import annotations\n\n"
        "# Views will be added in subsequent phases.\n"
    ),
    "urls.py": (
        '"""URL routing for the {app} app."""\n\n'
        "from __future__ import annotations\n\n"
        'app_name = "{app}"\n\n'
        "urlpatterns: list = []\n"
    ),
    "admin.py": (
        '"""Django admin registrations for the {app} app."""\n\n'
        "from __future__ import annotations\n\n"
        "from django.contrib import admin as django_admin\n\n"
        "# Register models here as they are introduced in later phases.\n"
        "_ = django_admin\n"
    ),
    "signals.py": '"""Cross-app signal handlers for the {app} app (side effects only)."""\n\nfrom __future__ import annotations\n\n# Signals will be added when cross-app side effects are required.\n',
    "apps.py": '"""{app_title} application configuration."""\n\nfrom __future__ import annotations\n\nfrom django.apps import AppConfig\n\n\nclass {class_name}(AppConfig):\n    """Django app config for {description}."""\n\n    default_auto_field = "django.db.models.BigAutoField"\n    name = "{app}"\n    verbose_name = "{app_title}"\n\n    def ready(self) -> None:\n        """Import signal modules when Django starts."""\n        import {app}.signals  # noqa: F401\n',
    "tests/test_models.py": '"""Unit tests for {app} models."""\n\nfrom __future__ import annotations\n\n# Model tests will be added in subsequent phases.\n',
    "tests/test_selectors.py": '"""Unit tests for {app} selectors (including query-count assertions)."""\n\nfrom __future__ import annotations\n\n# Selector tests will be added in subsequent phases.\n',
    "tests/test_services.py": '"""Unit tests for {app} services (asserting side effects)."""\n\nfrom __future__ import annotations\n\n# Service tests will be added in subsequent phases.\n',
    "tests/test_views.py": '"""Integration tests for {app} views."""\n\nfrom __future__ import annotations\n\n# View tests will be added in subsequent phases.\n',
    "tests/__init__.py": "",
}


def title_case(name: str) -> str:
    return name.replace("_", " ").title()


def class_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_")) + "Config"


def main() -> None:
    for app, description in APPS.items():
        app_dir = BASE / app
        for rel_path, template in FILE_TEMPLATES.items():
            target = app_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            content = template.format(
                app=app,
                app_title=title_case(app),
                class_name=class_name(app),
                description=description,
            )
            target.write_text(content, encoding="utf-8")
        print(f"Scaffolded {app}")


if __name__ == "__main__":
    main()
