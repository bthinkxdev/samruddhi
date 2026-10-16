"""Tests for the catalog app."""

from __future__ import annotations

from django.db.models import ProtectedError
from django.test import TestCase

from accounts.services import register_customer_email
from catalog.models import Collection, Product, ProductVariant
from core.models import Currency
from orders.models import Order, OrderItem, OrderStatus


class ProductDisplayVariantTests(TestCase):
    """Product.display_variant drives storefront price/stock display and (via
    dashboard.views.catalog._render_product_form) the admin's product-level
    price/stock sync — both must agree on which variant is authoritative."""

    def setUp(self) -> None:
        collection = Collection.objects.create(name="Variant Collection", slug="variant-collection")
        self.product = Product.objects.create(
            name="Variant Yarn",
            slug="variant-yarn",
            sku="SKU-VARIANT-1",
            base_price="100.00",
            mrp="100.00",
            purchase_price="60.00",
        )
        self.product.collections.add(collection)

    def test_display_variant_prefers_in_stock_default(self) -> None:
        ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="S",
            base_price="90.00", mrp="90.00", purchase_price="50.00",
            stock_quantity=5, is_default=False,
        )
        default_in_stock = ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="M",
            base_price="110.00", mrp="110.00", purchase_price="70.00",
            stock_quantity=3, is_default=True,
        )
        self.assertEqual(self.product.display_variant.pk, default_in_stock.pk)

    def test_sold_out_default_yields_to_in_stock_variant(self) -> None:
       
        ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="S",
            base_price="90.00", mrp="90.00", purchase_price="50.00",
            stock_quantity=0, is_default=True,
        )
        in_stock = ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="M",
            base_price="110.00", mrp="110.00", purchase_price="70.00",
            stock_quantity=5, is_default=False,
        )
        self.assertEqual(self.product.display_variant.pk, in_stock.pk)
        self.assertEqual(self.product.effective_stock_quantity, 5)

    def test_all_sold_out_falls_back_to_default(self) -> None:
        ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="S",
            base_price="90.00", mrp="90.00", purchase_price="50.00", stock_quantity=0,
        )
        default = ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="M",
            base_price="110.00", mrp="110.00", purchase_price="70.00",
            stock_quantity=0, is_default=True,
        )
        self.assertEqual(self.product.display_variant.pk, default.pk)

    def test_display_variant_falls_back_to_first_in_stock_when_no_default(self) -> None:
        ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="S",
            base_price="90.00", mrp="90.00", purchase_price="50.00",
            stock_quantity=0,
        )
        in_stock = ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="M",
            base_price="110.00", mrp="110.00", purchase_price="70.00",
            stock_quantity=5,
        )
        self.assertEqual(self.product.display_variant.pk, in_stock.pk)

    def test_effective_stock_uses_product_fields_when_no_variants(self) -> None:
        self.product.stock_quantity = 6
        self.product.low_stock_threshold = 10
        self.product.save()
        self.assertIsNone(self.product.display_variant)
        self.assertEqual(self.product.effective_stock_quantity, 6)
        self.assertEqual(self.product.effective_low_stock_threshold, 10)

    def test_effective_stock_uses_display_variant_when_present(self) -> None:
        ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="M",
            base_price="110.00", mrp="110.00", purchase_price="70.00",
            stock_quantity=3, low_stock_threshold=4,
        )
        self.assertEqual(self.product.effective_stock_quantity, 3)
        self.assertEqual(self.product.effective_low_stock_threshold, 4)

    def test_deleting_last_variant_keeps_product_stock(self) -> None:
        variant = ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="M",
            base_price="110.00", mrp="110.00", purchase_price="70.00",
            stock_quantity=9,
        )
        Product.objects.filter(pk=self.product.pk).update(stock_quantity=7)
        variant.delete()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 7)

    def test_deleting_one_of_many_variants_resyncs_stock(self) -> None:
        a = ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="S",
            base_price="90.00", mrp="90.00", purchase_price="50.00", stock_quantity=4,
        )
        ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="M",
            base_price="110.00", mrp="110.00", purchase_price="70.00", stock_quantity=6,
        )
        a.delete()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 6)


class ProductVariantDeleteProtectionTests(TestCase):
    """A variant referenced by an existing OrderItem must not be deletable —
    OrderItem.variant is PROTECT (not SET_NULL) precisely so historical order
    data can't silently go missing."""

    def setUp(self) -> None:
        collection = Collection.objects.create(name="Protect Collection", slug="protect-collection")
        self.product = Product.objects.create(
            name="Protect Yarn",
            slug="protect-yarn",
            sku="SKU-PROTECT-1",
            base_price="100.00",
            mrp="100.00",
            purchase_price="60.00",
        )
        self.product.collections.add(collection)
        self.variant = ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="S",
            base_price="90.00", mrp="90.00", purchase_price="50.00",
            stock_quantity=5,
        )
        self.currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="protect-test@example.com", password="testpass12345", name="Protect Test"
        )
        order = Order.objects.create(
            customer_profile=self.profile,
            order_number="#PROTECT-1",
            idempotency_key="protect-1",
            order_status=OrderStatus.PLACED_COD,
            subtotal="90.00",
            total_amount="90.00",
            currency=self.currency,
        )
        OrderItem.objects.create(
            order=order, product=self.product, variant=self.variant,
            variant_name=self.variant.name, variant_sku="SKU-PROTECT-1",
            quantity=1, unit_price="90.00",
        )

    def test_deleting_variant_referenced_by_order_raises_protected_error(self) -> None:
        with self.assertRaises(ProtectedError):
            self.variant.delete()


def _make_product(*, sku: str, name: str, **extra) -> Product:
    return Product.objects.create(
        name=name,
        slug=sku.lower(),
        sku=sku,
        base_price="100.00",
        mrp="100.00",
        purchase_price="60.00",
        stock_quantity=5,
        **extra,
    )


class CollectionMembershipTests(TestCase):
    """Products and collections are many-to-many; the homepage grid honours the limit."""

    def setUp(self) -> None:
        self.shirts = Collection.objects.create(name="Shirts", slug="shirts")
        self.sale = Collection.objects.create(name="Sale", slug="sale")
        self.products = [_make_product(sku=f"P-{i}", name=f"Product {i}") for i in range(10)]
        for product in self.products:
            product.collections.add(self.shirts)
        self.products[0].collections.add(self.sale)

    def test_product_can_live_in_several_collections(self) -> None:
        self.assertEqual(set(self.products[0].collections.all()), {self.shirts, self.sale})
        self.assertEqual(self.sale.products.count(), 1)
        self.assertEqual(self.shirts.products.count(), 10)

    def test_collection_products_include_sub_collections(self) -> None:
        from catalog.selectors import get_collection_products

        child = Collection.objects.create(name="Polos", slug="polos", parent=self.shirts)
        extra = _make_product(sku="P-CHILD", name="Child product")
        extra.collections.add(child)
        slugs = {p.slug for p in get_collection_products(collection=self.shirts)}
        self.assertIn("p-child", slugs)

    def test_homepage_collections_respect_toggle_and_limit(self) -> None:
        from catalog.selectors import get_homepage_collections

        self.assertEqual(get_homepage_collections(), [])

        self.shirts.show_on_homepage = True
        self.shirts.homepage_product_limit = 3
        self.shirts.save()
        grids = get_homepage_collections()
        self.assertEqual([g["collection"] for g in grids], [self.shirts])
        self.assertEqual(len(grids[0]["products"]), 3)

    def test_homepage_limit_defaults_to_eight(self) -> None:
        self.assertEqual(self.shirts.homepage_product_limit, 8)
        self.assertFalse(self.shirts.show_on_homepage)

    def test_collection_page_lists_its_products(self) -> None:
        from django.urls import reverse

        response = self.client.get(reverse("catalog:plp-collection", kwargs={"collection_slug": "sale"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Product 0")
        self.assertNotContains(response, "Product 1<")

    def test_inactive_collection_is_not_found(self) -> None:
        from django.urls import reverse

        self.sale.is_active = False
        self.sale.save()
        response = self.client.get(reverse("catalog:plp-collection", kwargs={"collection_slug": "sale"}))
        self.assertEqual(response.status_code, 404)


class LabelTests(TestCase):
    """Labels are many-to-many corner badges on product cards."""

    def setUp(self) -> None:
        from catalog.models import Label

        self.collection = Collection.objects.create(name="Tees", slug="tees")
        self.hot = Label.objects.create(
            name="Hot Seller", slug="hot-seller", background_color="#112233", text_color="#FFEEDD"
        )
        self.hidden = Label.objects.create(name="Secret", slug="secret", is_active=False)
        self.tagged = _make_product(sku="L-1", name="Tagged tee")
        self.plain = _make_product(sku="L-2", name="Plain tee")
        for product in (self.tagged, self.plain):
            product.collections.add(self.collection)
        self.tagged.labels.add(self.hot, self.hidden)

    def _collection_page(self, **params):
        from django.urls import reverse

        return self.client.get(
            reverse("catalog:plp-collection", kwargs={"collection_slug": "tees"}), params
        )

    def test_active_label_renders_over_the_card_with_its_colours(self) -> None:
        response = self._collection_page()
        self.assertContains(response, "Hot Seller")
        self.assertContains(response, "background: #112233; color: #FFEEDD;")

    def test_inactive_label_is_hidden(self) -> None:
        self.assertNotContains(self._collection_page(), "Secret")

    def test_label_filter_narrows_the_listing(self) -> None:
        response = self._collection_page(label="hot-seller")
        self.assertContains(response, "Tagged tee")
        self.assertNotContains(response, "Plain tee")

    def test_inactive_label_does_not_filter(self) -> None:
        response = self._collection_page(label="secret")
        self.assertNotContains(response, "Tagged tee")

    def test_label_can_sit_on_many_products(self) -> None:
        self.plain.labels.add(self.hot)
        self.assertEqual(self.hot.products.count(), 2)
