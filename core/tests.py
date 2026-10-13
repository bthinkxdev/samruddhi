"""Tests for the Meta Pixel / Conversions API integration (core.meta_pixel)."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.services import register_customer_email
from cart.models import Cart, CartItem
from catalog.models import Collection, Product
from checkout.services import create_checkout_session, place_order
from core import meta_pixel
from core.models import Currency
from orders.models import OrderStatus
from payments.models import PaymentStatus, PaymentTransaction

PIXEL_ID = "123456789012345"
PIXEL_SETTINGS = {
    "META_PIXEL_ID": PIXEL_ID,
    "META_CAPI_ACCESS_TOKEN": "capi-secret-token",
    "META_TEST_EVENT_CODE": "",
}


def _page_events(response) -> list[dict]:
    """Events the page hands to meta_pixel.js (the #mpx-events JSON blob)."""
    html = response.content.decode()
    marker = '<script id="mpx-events" type="application/json">'
    if marker not in html:
        return []
    return json.loads(html.split(marker, 1)[1].split("</script>", 1)[0])


class MetaPixelTestBase(TestCase):
    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="Pixel.Buyer@Example.com", password="testpass12345", name="Pixel Buyer"
        )
        self.profile.phone = "9876543210"
        self.profile.save(update_fields=["phone"])
        collection = Collection.objects.create(name="Gym Wear", slug="gym-wear")
        self.product = Product.objects.create(
            name="Test Hoodie",
            slug="test-hoodie",
            sku="SKU-PIXEL-1",
            base_price="500.00",
            mrp="600.00",
            purchase_price="300.00",
            stock_quantity=100,
        )
        self.product.collections.add(collection)
        for target in ("delhivery.tasks.create_shipment_for_order.delay",):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_order(self, gateway_key: str, key: str):
        cart = Cart.objects.create(customer_profile=self.profile, currency=self.currency)
        CartItem.objects.create(
            cart=cart, product=self.product, quantity=2, unit_price_at_add=self.product.base_price
        )
        session = create_checkout_session(cart=cart, customer_profile=self.profile)
        with patch("notifications.tasks.dispatch_new_order_admin_notification.delay"):
            return place_order(
                checkout_session_id=session.pk,
                idempotency_key=key,
                gateway_key=gateway_key,
                customer_profile=self.profile,
            )

    def confirmation(self, order):
        return self.client.get(reverse("checkout:confirmation", kwargs={"order_id": order.pk}))


class DashboardConfiguredPixelTests(MetaPixelTestBase):
    """Pixel id / CAPI token entered in dashboard Settings (no env vars set)."""

    def _form(self, **overrides):
        from core.services import get_site_settings
        from dashboard.forms import SiteSettingsForm

        data = {
            "site_name": "Samruddhi",
            "primary_color": "#0369A1",
            "secondary_color": "#0B1220",
            "font_family": "Inter, sans-serif",
            "tax_rate_percent": "0",
            "cod_delivery_charge": "50",
            **overrides,
        }
        return SiteSettingsForm(data, instance=get_site_settings())

    @override_settings(META_PIXEL_ID="", META_CAPI_ACCESS_TOKEN="")
    def test_dashboard_values_enable_pixel_and_capi(self):
        form = self._form(meta_pixel_id=" 555666777 ", meta_capi_access_token="dash-token")
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertEqual(meta_pixel.pixel_id(), "555666777")
        self.assertTrue(meta_pixel.is_capi_enabled())
        self.assertContains(self.client.get(reverse("catalog:plp")), "fbq('init', '555666777')")

        order = self.make_order("cod", "dash-cod")
        with patch("core.meta_pixel.requests.post") as post:
            post.return_value = MagicMock(raise_for_status=lambda: None)
            meta_pixel.send_purchase_event(order_id=order.pk)
        self.assertIn("/555666777/events", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["json"]["access_token"], "dash-token")

    @override_settings(META_PIXEL_ID="999", META_CAPI_ACCESS_TOKEN="env-token")
    def test_dashboard_value_overrides_env_and_blank_falls_back_to_env(self):
        self.assertEqual(meta_pixel.pixel_id(), "999")
        self._form(meta_pixel_id="111").save()
        self.assertEqual(meta_pixel.pixel_id(), "111")
        self._form(meta_pixel_id="").save()
        self.assertEqual(meta_pixel.pixel_id(), "999")

    def test_non_numeric_pixel_id_is_rejected_by_form(self):
        form = self._form(meta_pixel_id="12ab")
        self.assertFalse(form.is_valid())
        self.assertIn("meta_pixel_id", form.errors)

    def test_blank_token_keeps_saved_one_and_clear_removes_it(self):
        self._form(meta_capi_access_token="keep-me").save()
        self._form(meta_capi_access_token="").save()
        self.assertEqual(meta_pixel.capi_access_token(), "keep-me")

        self._form(meta_capi_access_token="", clear_meta_capi_access_token="on").save()
        with override_settings(META_CAPI_ACCESS_TOKEN=""):
            self.assertEqual(meta_pixel.capi_access_token(), "")

    def test_token_is_never_rendered_back_into_the_form(self):
        form = self._form(meta_capi_access_token="super-secret")
        form.save()
        from core.services import get_site_settings
        from dashboard.forms import SiteSettingsForm

        self.assertNotIn("super-secret", SiteSettingsForm(instance=get_site_settings()).as_p())


@override_settings(**PIXEL_SETTINGS)
class PurchaseGatingTests(MetaPixelTestBase):
    """Only orders that actually became a sale may ever count as a Purchase."""

    def test_pending_online_order_is_not_a_purchase(self):
        order = self.make_order("razorpay_upi", "pending-1")
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        self.assertIsNone(meta_pixel.purchase_page_event(order))
        self.assertEqual(_page_events(self.confirmation(order)), [])

    def test_cod_order_is_a_purchase_with_cod_payment_method(self):
        order = self.make_order("cod", "cod-1")
        PaymentTransaction.objects.create(
            order=order,
            gateway_key="cod",
            amount=order.total_amount,
            currency=order.currency,
            status=PaymentStatus.PENDING,
        )
        events = _page_events(self.confirmation(order))
        self.assertEqual([e["name"] for e in events], ["Purchase"])
        purchase = events[0]
        self.assertEqual(purchase["event_id"], f"purchase_{order.pk}")
        self.assertFalse(purchase["custom"])
        params = purchase["params"]
        self.assertEqual(params["payment_method"], "cod")
        self.assertEqual(params["value"], float(order.total_amount))
        self.assertEqual(params["currency"], "INR")
        self.assertEqual(params["content_ids"], [str(self.product.pk)])
        self.assertEqual(params["num_items"], 2)
        self.assertEqual(params["order_id"], order.order_number)

    def test_old_successful_order_does_not_refire_in_browser(self):
        order = self.make_order("cod", "cod-old")
        order.success_at = timezone.now() - timedelta(hours=3)
        order.save(update_fields=["success_at"])
        self.assertEqual(_page_events(self.confirmation(order)), [])

    @override_settings(META_PIXEL_ID="")
    def test_disabled_pixel_renders_nothing(self):
        order = self.make_order("cod", "cod-disabled")
        response = self.confirmation(order)
        self.assertNotContains(response, "fbevents.js")
        self.assertEqual(_page_events(response), [])


@override_settings(**PIXEL_SETTINGS)
class ServerSidePurchaseTests(MetaPixelTestBase):
    def test_cod_order_dispatches_exactly_one_capi_purchase(self):
        with patch("core.tasks.send_meta_purchase_event.apply_async") as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                order = self.make_order("cod", "cod-capi")
        apply_async.assert_called_once_with(kwargs={"order_id": order.pk}, countdown=5)

    def test_pending_online_order_does_not_dispatch(self):
        with patch("core.tasks.send_meta_purchase_event.apply_async") as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                self.make_order("razorpay_upi", "pending-capi")
        apply_async.assert_not_called()

    def test_payment_confirmation_dispatches_once_even_if_confirmed_twice(self):
        order = self.make_order("razorpay_upi", "online-capi")
        tx = PaymentTransaction.objects.create(
            order=order,
            gateway_key="razorpay_upi",
            amount=order.total_amount,
            currency=order.currency,
            status=PaymentStatus.PENDING,
            external_intent_id="order_rzp_pixel",
        )
        from payments.services import confirm_payment_success

        with patch("core.tasks.send_meta_purchase_event.apply_async") as apply_async, patch(
            "notifications.tasks.dispatch_order_confirmation_notification.delay"
        ), patch("notifications.tasks.dispatch_new_order_admin_notification.delay"):
            with self.captureOnCommitCallbacks(execute=True):
                confirm_payment_success(payment_transaction=tx, external_transaction_id="pay_1")
            with self.captureOnCommitCallbacks(execute=True):
                confirm_payment_success(payment_transaction=tx, external_transaction_id="pay_1")
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        apply_async.assert_called_once_with(kwargs={"order_id": order.pk}, countdown=5)

        events = _page_events(self.confirmation(order))
        self.assertEqual(events[0]["params"]["payment_method"], "online")

    @override_settings(META_CAPI_ACCESS_TOKEN="")
    def test_no_dispatch_without_access_token(self):
        with patch("core.tasks.send_meta_purchase_event.apply_async") as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                self.make_order("cod", "cod-no-token")
        apply_async.assert_not_called()

    def test_capi_request_hashes_pii_and_keeps_token_out_of_url(self):
        order = self.make_order("cod", "cod-payload")
        order.invoice_details = {
            "meta_tracking": {
                "fbp": "fb.1.123.456",
                "fbc": "fb.1.123.abc",
                "ip": "203.0.113.9",
                "user_agent": "UA/1.0",
                "checkout_type": "buy_now",
                "source_url": "https://shop.example/checkout/confirmation/1/",
            }
        }
        order.delivery_address_snapshot = {
            "name": "Pixel Buyer",
            "email": "Pixel.Buyer@Example.com",
            "phone": "98765 43210",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
        }
        order.save(update_fields=["invoice_details", "delivery_address_snapshot"])

        with patch("core.meta_pixel.requests.post") as post:
            post.return_value = MagicMock(raise_for_status=lambda: None)
            self.assertTrue(meta_pixel.send_purchase_event(order_id=order.pk))

        url = post.call_args.args[0]
        body = post.call_args.kwargs["json"]
        self.assertIn(f"/{PIXEL_ID}/events", url)
        self.assertNotIn("capi-secret-token", url)
        self.assertEqual(body["access_token"], "capi-secret-token")

        data = body["data"][0]
        self.assertEqual(data["event_name"], "Purchase")
        self.assertEqual(data["event_id"], f"purchase_{order.pk}")
        self.assertEqual(data["action_source"], "website")
        self.assertEqual(data["event_time"], int(order.success_at.timestamp()))
        self.assertEqual(data["custom_data"]["checkout_type"], "buy_now")

        user = data["user_data"]
        sha = lambda v: hashlib.sha256(v.encode()).hexdigest()  # noqa: E731
        self.assertEqual(user["em"], [sha("pixel.buyer@example.com")])
        self.assertEqual(user["ph"], [sha("919876543210")])
        self.assertEqual(user["ct"], [sha("mumbai")])
        self.assertEqual(user["zp"], [sha("400001")])
        self.assertEqual(user["fbp"], "fb.1.123.456")
        self.assertEqual(user["client_ip_address"], "203.0.113.9")
        self.assertNotIn("pixel.buyer@example.com", json.dumps(body).lower())

    def test_unsuccessful_order_is_never_sent(self):
        order = self.make_order("razorpay_upi", "pending-no-send")
        with patch("core.meta_pixel.requests.post") as post:
            self.assertFalse(meta_pixel.send_purchase_event(order_id=order.pk))
        post.assert_not_called()


@override_settings(**PIXEL_SETTINGS)
class StorefrontEventTests(MetaPixelTestBase):
    def test_base_snippet_and_pageview_rendered_once(self):
        response = self.client.get(reverse("catalog:plp"))
        html = response.content.decode()
        self.assertEqual(html.count("fbq('init', '" + PIXEL_ID + "')"), 1)
        self.assertEqual(html.count("fbq('track', 'PageView')"), 1)
        self.assertIn("js/meta_pixel.js", html)

    def test_pdp_fires_view_content(self):
        response = self.client.get(reverse("catalog:pdp", kwargs={"slug": self.product.slug}))
        events = _page_events(response)
        view_content = next(e for e in events if e["name"] == "ViewContent")
        self.assertEqual(view_content["params"]["content_ids"], [str(self.product.pk)])
        self.assertEqual(view_content["params"]["content_name"], "Test Hoodie")
        self.assertEqual(view_content["params"]["currency"], "INR")

    def test_plp_fires_view_collection_and_search(self):
        events = _page_events(self.client.get(reverse("catalog:plp"), {"q": "hoodie"}))
        self.assertEqual([e["name"] for e in events], ["Search", "ViewCollection"])
        self.assertEqual(events[0]["params"]["search_string"], "hoodie")
        self.assertTrue(events[1]["custom"])

    def test_plp_htmx_partial_is_not_a_page_view(self):
        response = self.client.get(reverse("catalog:plp"), HTTP_HX_REQUEST="true")
        self.assertNotContains(response, "mpx-events")

    def test_add_to_cart_htmx_response_carries_event(self):
        response = self.client.post(
            reverse("cart:add"),
            {"product_id": self.product.pk, "quantity": 2},
            HTTP_HX_REQUEST="true",
        )
        trigger = json.loads(response["HX-Trigger"])
        add_event = trigger["mpxEvent"]
        self.assertEqual(add_event["name"], "AddToCart")
        self.assertEqual(add_event["params"]["value"], 1000.0)
        self.assertEqual(add_event["params"]["contents"][0]["quantity"], 2)

    def test_checkout_page_fires_initiate_checkout(self):
        self.client.post(reverse("cart:add"), {"product_id": self.product.pk, "quantity": 1}, HTTP_HX_REQUEST="true")
        events = _page_events(self.client.get(reverse("checkout:checkout")))
        initiate = next(e for e in events if e["name"] == "InitiateCheckout")
        self.assertEqual(initiate["params"]["checkout_type"], "cart")
        self.assertEqual(initiate["params"]["content_ids"], [str(self.product.pk)])

    def test_buy_now_event_survives_the_redirect_to_checkout(self):
        self.client.post(
            reverse("cart:add"), {"product_id": self.product.pk, "quantity": 1, "buy_now": "true"}
        )
        events = _page_events(self.client.get(reverse("checkout:checkout")))
        self.assertEqual([e["name"] for e in events], ["AddToCart", "InitiateCheckout"])
        self.assertEqual(events[1]["params"]["checkout_type"], "buy_now")

    def test_htmx_requests_do_not_drain_the_event_queue(self):
        session = self.client.session
        session[meta_pixel.SESSION_QUEUE_KEY] = [meta_pixel.event("Subscribe")]
        session.save()
        self.client.get(reverse("catalog:plp"), HTTP_HX_REQUEST="true")
        self.assertEqual([e["name"] for e in _page_events(self.client.get(reverse("catalog:plp")))][0], "Subscribe")
        # drained after the first full page load — never replayed
        self.assertNotIn("Subscribe", [e["name"] for e in _page_events(self.client.get(reverse("catalog:plp")))])

    def test_ajax_newsletter_returns_subscribe_event_instead_of_queueing(self):
        url = reverse("marketing:newsletter-subscribe")
        response = self.client.post(url, {"email": "pixel-news@example.com"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        data = response.json()
        self.assertEqual(data["mpx_event"]["name"], "Subscribe")
        self.assertEqual(data["mpx_event"]["params"]["subscription_type"], "newsletter")
        # not left in the session to fire again on the next page
        self.assertNotIn(meta_pixel.SESSION_QUEUE_KEY, self.client.session)
        # already-subscribed email: no event
        again = self.client.post(url, {"email": "pixel-news@example.com"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertNotIn("mpx_event", again.json())

    def test_home_fires_view_home(self):
        events = _page_events(self.client.get("/"))
        self.assertIn("ViewHome", [e["name"] for e in events])

    def test_non_numeric_pixel_id_is_rejected(self):
        with override_settings(META_PIXEL_ID="123');alert(1);//"):
            response = self.client.get(reverse("catalog:plp"))
        self.assertNotContains(response, "fbevents.js")
