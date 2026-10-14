"""Tests for the dashboard app.

Access control, CRUD flows, and report views are exercised here. Add cases
under a tests/ package as coverage grows (see scripts/scaffold_apps.py).
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.services import register_customer_email
from cart.models import Cart, CartItem
from catalog.models import Collection, Product
from checkout.services import create_checkout_session, place_order
from core.models import Currency
from dashboard.forms import ProductVariantForm, ProductVariantFormSet
from orders.models import Order, OrderStatus
from payments.models import PaymentStatus, PaymentTransaction
from payments.services import confirm_payment_success


class OrderListTabsTests(TestCase):
    """The Orders list splits real orders from CHECKOUT_PENDING abandoned
    checkouts into two tabs (see dashboard/views/orders.py::order_list)."""

    def setUp(self) -> None:
        self.staff_user = User.objects.create_superuser(
            username="dash-admin", email="dash-admin@example.com", password="testpass12345"
        )
        self.client.force_login(self.staff_user)

        self.currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="dash-order-test@example.com", password="testpass12345", name="Dash Order Test"
        )
        collection = Collection.objects.create(name="Test Collection", slug="dash-test-collection")
        self.product = Product.objects.create(
            name="Test Yarn",
            slug="dash-test-yarn",
            sku="SKU-DASH-1",
            base_price="500.00",
            mrp="500.00",
            purchase_price="300.00",
            stock_quantity=100,
        )
        self.product.collections.add(collection)

        self.confirmed_order = self._place_order("confirmed")
        tx = PaymentTransaction.objects.create(
            order=self.confirmed_order,
            gateway_key="razorpay_upi",
            amount=self.confirmed_order.total_amount,
            currency=self.confirmed_order.currency,
            status=PaymentStatus.PENDING,
            external_intent_id="order_dash_confirmed_1",
        )
        confirm_payment_success(payment_transaction=tx, external_transaction_id="pay_dash_confirmed_1")

        self.abandoned_order = self._place_order("abandoned")
        self.assertEqual(self.abandoned_order.order_status, OrderStatus.CHECKOUT_PENDING)

    def _place_order(self, suffix: str):
        cart = Cart.objects.create(customer_profile=self.profile, currency=self.currency)
        CartItem.objects.create(
            cart=cart, product=self.product, quantity=1, unit_price_at_add=self.product.base_price
        )
        session = create_checkout_session(cart=cart, customer_profile=self.profile)
        return place_order(
            checkout_session_id=session.pk,
            idempotency_key=f"dash-order-test-{suffix}",
            gateway_key="razorpay_upi",
            customer_profile=self.profile,
        )

    def test_orders_tab_excludes_abandoned_checkouts(self):
        response = self.client.get(reverse("dashboard:order-list"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertContains(response, self.confirmed_order.order_number)
        self.assertNotContains(response, self.abandoned_order.order_number)
        self.assertIn("Abandoned Checkouts", content)
        self.assertIn(">1<", content)  # abandoned_count badge
        self.assertNotIn("Payment Pending", content)  # excluded from status dropdown + rows

    def test_abandoned_tab_shows_only_abandoned_checkouts(self):
        response = self.client.get(reverse("dashboard:order-list") + "?view=abandoned")
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, self.abandoned_order.order_number)
        self.assertNotContains(response, self.confirmed_order.order_number)
        # status dropdown is hidden entirely on this tab
        self.assertNotContains(response, "All order statuses")

    def test_search_filter_works_within_abandoned_tab(self):
        response = self.client.get(
            reverse("dashboard:order-list") + f"?view=abandoned&q={self.abandoned_order.order_number}"
        )
        self.assertContains(response, self.abandoned_order.order_number)

        response = self.client.get(reverse("dashboard:order-list") + "?view=abandoned&q=NO_SUCH_ORDER")
        self.assertNotContains(response, self.abandoned_order.order_number)


class OrderAddressUpdateViewTests(TestCase):
    """dashboard:order-address-update — the previously-missing address edit."""

    def setUp(self) -> None:
        self.staff_user = User.objects.create_superuser(
            username="dash-admin-addr", email="dash-admin-addr@example.com", password="testpass12345"
        )
        self.client.force_login(self.staff_user)

        self.currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="dash-addr-test@example.com", password="testpass12345", name="Dash Addr Test"
        )
        self.editable_order = Order.objects.create(
            customer_profile=self.profile,
            order_number="#ADDR-EDITABLE",
            idempotency_key="addr-editable",
            order_status=OrderStatus.PLACED_COD,
            total_amount="500.00",
            currency=self.currency,
            delivery_address_snapshot={
                "name": "Original Name", "line1": "Old Line 1", "city": "Old City",
                "state": "Old State", "pincode": "111111",
            },
        )
        self.delivered_order = Order.objects.create(
            customer_profile=self.profile,
            order_number="#ADDR-DELIVERED",
            idempotency_key="addr-delivered",
            order_status=OrderStatus.DELIVERED,
            total_amount="500.00",
            currency=self.currency,
            delivery_address_snapshot={"name": "Frozen Name", "line1": "Frozen Line 1", "city": "Frozen City"},
        )

    def test_editable_status_updates_snapshot(self) -> None:
        response = self.client.post(
            reverse("dashboard:order-address-update", args=[self.editable_order.pk]),
            data={"name": "New Name", "line1": "New Line 1", "city": "New City", "state": "New State", "pincode": "222222"},
        )
        self.assertRedirects(response, reverse("dashboard:order-detail", args=[self.editable_order.pk]))
        self.editable_order.refresh_from_db()
        self.assertEqual(self.editable_order.delivery_address_snapshot["line1"], "New Line 1")
        self.assertEqual(self.editable_order.delivery_address_snapshot["city"], "New City")

    def test_blocked_status_rejects_update(self) -> None:
        response = self.client.post(
            reverse("dashboard:order-address-update", args=[self.delivered_order.pk]),
            data={"name": "New Name", "line1": "New Line 1", "city": "New City"},
        )
        self.assertRedirects(response, reverse("dashboard:order-detail", args=[self.delivered_order.pk]))
        self.delivered_order.refresh_from_db()
        self.assertEqual(self.delivered_order.delivery_address_snapshot["line1"], "Frozen Line 1")


class ProductVariantHasChangedTests(TestCase):
    """
    A variant row an admin explicitly filled with legitimate-but-default-
    looking values (stock 0, threshold 5) must not be silently dropped as an
    "untouched extra" row.
    """

    def test_explicit_zero_values_count_as_changed(self) -> None:
        data = {
            "variants-0-variant_type": "",
            "variants-0-name": "",
            "variants-0-base_price": "0",
            "variants-0-mrp": "0",
            "variants-0-purchase_price": "0",
            "variants-0-sku_suffix": "",
            "variants-0-stock_quantity": "0",
            "variants-0-low_stock_threshold": "5",
        }
        form = ProductVariantForm(data, prefix="variants-0")
        self.assertTrue(form.has_changed())

    def test_untouched_added_row_with_prefilled_defaults_is_unchanged(self) -> None:
        """
        "Add variant" then removing it (or leaving it empty) posts only the
        template's pre-filled stock 0 / threshold 5 plus the hidden parent FK;
        that row must be ignored, not validated into "... is required" errors.
        """
        data = {
            "variants-0-id": "",
            "variants-0-product": "85",
            "variants-0-variant_type": "",
            "variants-0-name": "",
            "variants-0-base_price": "",
            "variants-0-mrp": "",
            "variants-0-purchase_price": "",
            "variants-0-sku_suffix": "",
            "variants-0-stock_quantity": "0",
            "variants-0-low_stock_threshold": "5",
        }
        form = ProductVariantForm(data, prefix="variants-0")
        self.assertFalse(form.has_changed())

    def test_changed_stock_alone_counts_as_changed(self) -> None:
        data = {"variants-0-stock_quantity": "10", "variants-0-low_stock_threshold": "5"}
        form = ProductVariantForm(data, prefix="variants-0")
        self.assertTrue(form.has_changed())

    def test_fully_blank_row_is_unchanged(self) -> None:
        data = {
            "variants-0-variant_type": "",
            "variants-0-name": "",
            "variants-0-base_price": "",
            "variants-0-mrp": "",
            "variants-0-purchase_price": "",
            "variants-0-sku_suffix": "",
            "variants-0-stock_quantity": "",
            "variants-0-low_stock_threshold": "",
        }
        form = ProductVariantForm(data, prefix="variants-0")
        self.assertFalse(form.has_changed())


class ProductVariantFormSetValidationTests(TestCase):
    """Cross-row validation added to ProductVariantInlineFormSet."""

    def setUp(self) -> None:
        collection = Collection.objects.create(name="Formset Collection", slug="formset-collection")
        self.product = Product.objects.create(
            name="Formset Yarn",
            slug="formset-yarn",
            sku="SKU-FORMSET-1",
            base_price="100.00",
            mrp="100.00",
            purchase_price="60.00",
        )
        self.product.collections.add(collection)

    def _management_form(self, total: int) -> dict:
        return {
            "variants-TOTAL_FORMS": str(total),
            "variants-INITIAL_FORMS": "0",
            "variants-MIN_NUM_FORMS": "0",
            "variants-MAX_NUM_FORMS": "1000",
        }

    def _row(self, index: int, **overrides) -> dict:
        row = {
            f"variants-{index}-variant_type": "Size",
            f"variants-{index}-name": f"Variant {index}",
            f"variants-{index}-base_price": "90.00",
            f"variants-{index}-mrp": "90.00",
            f"variants-{index}-purchase_price": "50.00",
            f"variants-{index}-sku_suffix": f"SKU{index}",
            f"variants-{index}-stock_quantity": "5",
            f"variants-{index}-low_stock_threshold": "5",
        }
        for key, value in overrides.items():
            row[f"variants-{index}-{key}"] = value
        return row

    def test_duplicate_sku_suffix_rejected(self) -> None:
        data = self._management_form(2)
        data.update(self._row(0, sku_suffix="Small"))
        data.update(self._row(1, sku_suffix="small"))  # case-insensitive collision
        formset = ProductVariantFormSet(data, instance=self.product, prefix="variants")
        self.assertFalse(formset.is_valid())

    def test_variant_sku_equal_to_own_product_sku_rejected(self) -> None:
        data = self._management_form(1)
        data.update(self._row(0, sku_suffix="sku-formset-1"))  # product SKU, other case
        formset = ProductVariantFormSet(data, instance=self.product, prefix="variants")
        self.assertFalse(formset.is_valid())
        self.assertIn("this product's SKU", str(formset.forms[0].errors["sku_suffix"]))

    def test_variant_sku_checked_against_submitted_product_sku(self) -> None:
        """On create the formset has an unsaved product; the view passes the typed SKU."""
        data = self._management_form(1)
        data.update(self._row(0, sku_suffix="NEW-SKU"))
        formset = ProductVariantFormSet(data, instance=Product(), prefix="variants")
        formset.product_sku = "new-sku"
        self.assertFalse(formset.is_valid())

    def test_variant_sku_different_from_product_sku_accepted(self) -> None:
        data = self._management_form(1)
        data.update(self._row(0, sku_suffix="SKU-FORMSET-1-S"))
        formset = ProductVariantFormSet(data, instance=self.product, prefix="variants")
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_variant_type_casing_normalized_to_first_seen(self) -> None:
        data = self._management_form(2)
        data.update(self._row(0, variant_type="Size"))
        data.update(self._row(1, variant_type="size", sku_suffix="SKU1"))
        formset = ProductVariantFormSet(data, instance=self.product, prefix="variants")
        self.assertTrue(formset.is_valid())
        self.assertEqual(formset.forms[1].cleaned_data["variant_type"], "Size")

    def test_only_one_default_variant_allowed(self) -> None:
        data = self._management_form(2)
        data.update(self._row(0, is_default="on"))
        data.update(self._row(1, is_default="on"))
        formset = ProductVariantFormSet(data, instance=self.product, prefix="variants")
        self.assertFalse(formset.is_valid())


class ProductFormRequiredPriceGateTests(TestCase):
    """
    ProductForm.clean() silently defaults blank base_price/mrp/purchase_price/
    stock_quantity to 0 — fine when a variant will drive those fields, but a
    variant-less product must actually require them, matching the form's own
    (previously dead) error_messages.
    """

    def setUp(self) -> None:
        self.staff_user = User.objects.create_superuser(
            username="dash-admin-price", email="dash-admin-price@example.com", password="testpass12345"
        )
        self.client.force_login(self.staff_user)
        self.collection = Collection.objects.create(name="Price Collection", slug="price-collection")

    def _base_post(self, **overrides) -> dict:
        data = {
            "name": "Priced Yarn",
            "sku": "SKU-PRICE-1",
            "collections": [str(self.collection.pk)],
            "variants-TOTAL_FORMS": "0",
            "variants-INITIAL_FORMS": "0",
            "variants-MIN_NUM_FORMS": "0",
            "variants-MAX_NUM_FORMS": "1000",
            "images-TOTAL_FORMS": "0",
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "1000",
            "specifications-TOTAL_FORMS": "0",
            "specifications-INITIAL_FORMS": "0",
            "specifications-MIN_NUM_FORMS": "0",
            "specifications-MAX_NUM_FORMS": "1000",
        }
        data.update(overrides)
        return data

    def test_no_variants_and_blank_prices_is_rejected(self) -> None:
        response = self.client.post(reverse("dashboard:product-create"), data=self._base_post())
        self.assertEqual(response.status_code, 200)  # re-renders the form with errors
        self.assertFalse(Product.objects.filter(sku="SKU-PRICE-1").exists())

    def test_no_variants_with_prices_is_accepted(self) -> None:
        response = self.client.post(reverse("dashboard:product-create"), data=self._base_post(
            base_price="100.00", mrp="120.00", purchase_price="60.00", stock_quantity="10",
        ))
        self.assertRedirects(response, reverse("dashboard:product-list"))
        self.assertTrue(Product.objects.filter(sku="SKU-PRICE-1").exists())


_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)

_EMPTY_FORMSETS = {
    "variants-TOTAL_FORMS": "0", "variants-INITIAL_FORMS": "0",
    "variants-MIN_NUM_FORMS": "0", "variants-MAX_NUM_FORMS": "1000",
    "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0",
    "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "1000",
    "specifications-TOTAL_FORMS": "0", "specifications-INITIAL_FORMS": "0",
    "specifications-MIN_NUM_FORMS": "0", "specifications-MAX_NUM_FORMS": "1000",
}


class CollectionDashboardTests(TestCase):
    """Collection form: images required, product membership managed from the collection."""

    def setUp(self) -> None:
        import tempfile

        from django.test import override_settings

        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)

        self.client.force_login(
            User.objects.create_superuser(
                username="dash-collections", email="dash-collections@example.com", password="testpass12345"
            )
        )
        self.alpha = Product.objects.create(
            name="Alpha Tee", slug="alpha-tee", sku="ALPHA-1",
            base_price="10.00", mrp="10.00", purchase_price="5.00",
        )
        self.beta = Product.objects.create(
            name="Beta Tee", slug="beta-tee", sku="BETA-1",
            base_price="10.00", mrp="10.00", purchase_price="5.00",
        )

    def _post(self, **overrides) -> dict:
        from django.core.files.uploadedfile import SimpleUploadedFile

        data = {
            "name": "Summer",
            "slug": "",
            "display_order": "0",
            "is_active": "on",
            "image": SimpleUploadedFile("c.gif", _PIXEL_GIF, content_type="image/gif"),
            "banner_image": SimpleUploadedFile("b.gif", _PIXEL_GIF, content_type="image/gif"),
        }
        data.update(overrides)
        return data

    def test_create_assigns_products_and_defaults(self) -> None:
        response = self.client.post(
            reverse("dashboard:collection-create"),
            self._post(products=[str(self.alpha.pk), str(self.beta.pk)]),
        )
        self.assertRedirects(response, reverse("dashboard:collection-list"))
        collection = Collection.objects.get(name="Summer")
        self.assertEqual(collection.slug, "summer")
        self.assertEqual(set(collection.products.all()), {self.alpha, self.beta})
        self.assertFalse(collection.show_on_homepage)
        self.assertEqual(collection.homepage_product_limit, 8)

    def test_images_are_required(self) -> None:
        response = self.client.post(
            reverse("dashboard:collection-create"), self._post(image="", banner_image="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Collection.objects.exists())

    def test_update_replaces_membership_and_sets_homepage_limit(self) -> None:
        collection = Collection.objects.create(name="Winter", slug="winter")
        collection.products.add(self.alpha)
        response = self.client.post(
            reverse("dashboard:collection-update", args=[collection.pk]),
            self._post(
                name="Winter", slug="winter", products=[str(self.beta.pk)],
                show_on_homepage="on", homepage_product_limit="12",
            ),
        )
        self.assertRedirects(response, reverse("dashboard:collection-list"))
        collection.refresh_from_db()
        self.assertEqual(list(collection.products.all()), [self.beta])
        self.assertTrue(collection.show_on_homepage)
        self.assertEqual(collection.homepage_product_limit, 12)

    def test_blank_homepage_limit_falls_back_to_default(self) -> None:
        self.client.post(
            reverse("dashboard:collection-create"),
            self._post(show_on_homepage="on", homepage_product_limit=""),
        )
        self.assertEqual(Collection.objects.get(name="Summer").homepage_product_limit, 8)

    def test_collection_with_children_cannot_be_nested(self) -> None:
        parent = Collection.objects.create(name="Parent", slug="parent")
        Collection.objects.create(name="Child", slug="child", parent=parent)
        other = Collection.objects.create(name="Other", slug="other")
        response = self.client.post(
            reverse("dashboard:collection-update", args=[parent.pk]),
            self._post(name="Parent", slug="parent", parent=str(other.pk)),
        )
        self.assertEqual(response.status_code, 200)
        parent.refresh_from_db()
        self.assertIsNone(parent.parent)

    def test_product_search_matches_name_and_sku(self) -> None:
        url = reverse("dashboard:collection-product-search")
        by_name = self.client.get(url, {"q": "alpha"}).json()["results"]
        self.assertEqual([r["sku"] for r in by_name], ["ALPHA-1"])
        by_sku = self.client.get(url, {"q": "BETA-1"}).json()["results"]
        self.assertEqual([r["name"] for r in by_sku], ["Beta Tee"])
        self.assertEqual(self.client.get(url, {"q": "a"}).json()["results"], [])

    def test_product_form_saves_collection_checkboxes(self) -> None:
        collection = Collection.objects.create(name="Basics", slug="basics")
        data = {
            "name": "Boxed Tee", "sku": "BOX-1", "collections": [str(collection.pk)],
            "base_price": "5.00", "mrp": "5.00", "purchase_price": "2.00", "stock_quantity": "3",
            **_EMPTY_FORMSETS,
        }
        self.client.post(reverse("dashboard:product-create"), data=data)
        self.assertEqual(list(Product.objects.get(sku="BOX-1").collections.all()), [collection])


class HomepageSectionReorderTests(TestCase):
    """Drag-and-drop ordering of homepage sections."""

    def setUp(self) -> None:
        from cms.models import HomepageSection, HomepageSectionType

        self.client.force_login(
            User.objects.create_superuser(
                username="dash-sections", email="dash-sections@example.com", password="testpass12345"
            )
        )
        self.sections = [
            HomepageSection.objects.create(
                section_type=HomepageSectionType.REVIEWS, title=f"S{i}", display_order=i
            )
            for i in range(3)
        ]
        self.url = reverse("dashboard:homepagesection-reorder")

    def _reorder(self, order):
        import json

        return self.client.post(self.url, json.dumps({"order": order}), content_type="application/json")

    def test_reorder_persists_new_positions(self) -> None:
        a, b, c = self.sections
        response = self._reorder([c.pk, a.pk, b.pk])
        self.assertEqual(response.status_code, 200)
        for section in self.sections:
            section.refresh_from_db()
        self.assertEqual([c.display_order, a.display_order, b.display_order], [0, 1, 2])

    def test_partial_or_stale_order_is_rejected(self) -> None:
        a, b, _ = self.sections
        self.assertEqual(self._reorder([a.pk, b.pk]).status_code, 400)
        self.assertEqual(self._reorder([a.pk, a.pk, b.pk]).status_code, 400)
        a.refresh_from_db()
        self.assertEqual(a.display_order, 0)

    def test_malformed_payload_is_rejected(self) -> None:
        self.assertEqual(self.client.post(self.url, "nope", content_type="application/json").status_code, 400)

    def test_new_section_is_appended_last(self) -> None:
        from cms.models import HomepageSection

        self.client.post(
            reverse("dashboard:homepagesection-create"),
            {"section_type": "newsletter", "title": "Join", "is_active": "on", "config": "{}"},
        )
        self.assertEqual(HomepageSection.objects.get(title="Join").display_order, 3)

    def test_list_requires_dashboard_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("dashboard:homepagesection-list"))
        self.assertEqual(response.status_code, 302)


class LabelDashboardTests(TestCase):
    """Label CRUD and assigning labels from the product form."""

    def setUp(self) -> None:
        self.client.force_login(
            User.objects.create_superuser(
                username="dash-labels", email="dash-labels@example.com", password="testpass12345"
            )
        )

    def test_create_label_derives_slug(self) -> None:
        from catalog.models import Label

        response = self.client.post(
            reverse("dashboard:label-create"),
            {"name": "Just In", "slug": "", "background_color": "#AA0000", "text_color": "#FFFFFF",
             "display_order": "1", "is_active": "on"},
        )
        self.assertRedirects(response, reverse("dashboard:label-list"))
        self.assertEqual(Label.objects.get().slug, "just-in")

    def test_invalid_colour_is_rejected(self) -> None:
        from catalog.models import Label

        response = self.client.post(
            reverse("dashboard:label-create"),
            {"name": "Bad", "slug": "bad", "background_color": "red", "text_color": "#FFFFFF",
             "display_order": "0", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Label.objects.exists())

    def test_product_form_assigns_labels(self) -> None:
        from catalog.models import Label

        label = Label.objects.create(name="Sale", slug="sale")
        data = {
            "name": "Labelled Tee", "sku": "LAB-1", "labels": [str(label.pk)],
            "base_price": "5.00", "mrp": "5.00", "purchase_price": "2.00", "stock_quantity": "3",
            **_EMPTY_FORMSETS,
        }
        self.client.post(reverse("dashboard:product-create"), data=data)
        self.assertEqual(list(Product.objects.get(sku="LAB-1").labels.all()), [label])

    def test_removed_section_types_are_not_offered(self) -> None:
        from cms.models import HomepageSectionType

        values = {value for value, _ in HomepageSectionType.choices}
        self.assertTrue({"featured_products", "new_arrivals", "best_sellers"}.isdisjoint(values))
