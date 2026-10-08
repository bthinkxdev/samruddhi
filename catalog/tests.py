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

    def test_display_variant_prefers_is_default_over_first_in_stock(self) -> None:
        default_but_out_of_stock = ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="S",
            base_price="90.00", mrp="90.00", purchase_price="50.00",
            stock_quantity=0, is_default=True,
        )
        ProductVariant.objects.create(
            product=self.product, variant_type="Size", name="M",
            base_price="110.00", mrp="110.00", purchase_price="70.00",
            stock_quantity=5, is_default=False,
        )
        self.assertEqual(self.product.display_variant.pk, default_but_out_of_stock.pk)

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
