"""
Locust load test for Phase 10 performance validation.

Usage:
    locust -f loadtests/locustfile.py --host=http://127.0.0.1:8000

Targets: homepage, PLP, checkout place_order (authenticated), gift builder POST.
"""

from __future__ import annotations

import os
import uuid

from locust import HttpUser, between, task


class StorefrontUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.email = f"load-{uuid.uuid4().hex[:8]}@example.com"
        self.password = "LoadTestPass123!"
        self.client.post(
            "/accounts/register/",
            json={"email": self.email, "password": self.password, "name": "Load User"},
            name="POST /accounts/register/",
        )
        self.client.post(
            "/accounts/login/email/",
            json={"email": self.email, "password": self.password},
            name="POST /accounts/login/email/",
        )

    @task(5)
    def homepage(self) -> None:
        self.client.get("/", name="GET /homepage")

    @task(4)
    def plp(self) -> None:
        self.client.get("/shop/?sort=newest", name="GET /shop/ (filtered PLP)")

    @task(3)
    def pdp_and_gift_builder(self) -> None:
        response = self.client.get("/shop/", name="GET /shop/ (discover product)")
        if response.status_code != 200:
            return
        self.client.get("/shop/products/rose-bouquet/", name="GET /shop/products/<slug>/ (PDP)")
        self.client.get(
            "/gifting/products/rose-bouquet/builder/",
            name="GET /gifting/products/<slug>/builder/",
        )

    @task(1)
    def checkout_flow(self) -> None:
        csrf = self.client.cookies.get("csrftoken", "")
        headers = {"X-CSRFToken": csrf} if csrf else {}
        self.client.post(
            "/cart/add/",
            data={"product_id": "1", "quantity": "1"},
            headers=headers,
            name="POST /cart/add/",
        )
        self.client.get("/checkout/", name="GET /checkout/")
        self.client.post(
            "/checkout/place-order/",
            data={"checkout_session_id": "1", "idempotency_key": uuid.uuid4().hex},
            headers=headers,
            name="POST /checkout/place-order/",
        )


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
