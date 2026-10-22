"""Tests for the Razorpay browser-redirect checkout callback."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import Address
from accounts.services import register_customer_email
from cart.models import Cart, CartItem
from catalog.models import Collection, Product
from checkout.services import create_checkout_session, place_order
from core.models import Currency
from orders.models import Order, OrderStatus, OrderStatusHistory
from payments.models import PaymentStatus, PaymentTransaction


class RazorpayCallbackViewTests(TestCase):
    """
    adapter.capture_payment()'s result must gate confirmation: a valid redirect
    signature only proves the payment *request* was authentic, not that the
    money was actually captured (relevant when auto-capture is off). Confirming
    regardless of the capture result would ship orders that were never paid.
    """

    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="callback-test@example.com",
            password="testpass12345",
            name="Callback Test",
        )
        collection = Collection.objects.create(name="Test Collection", slug="test-collection")
        self.product = Product.objects.create(
            name="Test Yarn",
            slug="test-yarn",
            sku="SKU-TEST-CB-1",
            base_price="500.00",
            mrp="500.00",
            purchase_price="300.00",
            stock_quantity=100,
        )
        self.product.collections.add(collection)
        self._delhivery_patch = patch("delhivery.tasks.create_shipment_for_order.delay")
        self._delhivery_patch.start()
        self.addCleanup(self._delhivery_patch.stop)

        cart = Cart.objects.create(customer_profile=self.profile, currency=self.currency)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=1,
            unit_price_at_add=self.product.base_price,
        )
        session = create_checkout_session(cart=cart, customer_profile=self.profile)
        self.order = place_order(
            checkout_session_id=session.pk,
            idempotency_key="callback-test-order-1",
            gateway_key="razorpay_upi",
            customer_profile=self.profile,
        )
        self.tx = PaymentTransaction.objects.create(
            order=self.order,
            gateway_key="razorpay_upi",
            amount=self.order.total_amount,
            currency=self.order.currency,
            status=PaymentStatus.PENDING,
            external_intent_id="order_rzp_test_1",
        )
        self.callback_url = reverse("checkout:razorpay-callback")

    @patch("payments.adapters.concrete.RazorpayAdapter.capture_payment", return_value=True)
    @patch("payments.adapters.concrete.RazorpayAdapter.verify_payment_signature", return_value=True)
    def test_valid_signature_and_successful_capture_confirms_order(self, mock_verify, mock_capture):
        response = self.client.post(
            self.callback_url,
            data={
                "order_id": self.order.pk,
                "razorpay_payment_id": "pay_real",
                "razorpay_order_id": "order_rzp_test_1",
                "razorpay_signature": "irrelevant-signature-is-mocked",
            },
        )
        self.order.refresh_from_db()
        self.tx.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CONFIRMED)
        self.assertEqual(self.tx.status, PaymentStatus.SUCCESS)
        self.assertEqual(self.tx.external_transaction_id, "pay_real")
        self.assertRedirects(
            response,
            reverse("checkout:confirmation", kwargs={"order_id": self.order.pk}),
            fetch_redirect_response=False,
        )

    @patch("payments.adapters.concrete.RazorpayAdapter.capture_payment", return_value=False)
    @patch("payments.adapters.concrete.RazorpayAdapter.verify_payment_signature", return_value=True)
    def test_valid_signature_but_failed_capture_does_not_confirm_order(self, mock_verify, mock_capture):
        response = self.client.post(
            self.callback_url,
            data={
                "order_id": self.order.pk,
                "razorpay_payment_id": "pay_never_captured",
                "razorpay_order_id": "order_rzp_test_1",
                "razorpay_signature": "irrelevant-signature-is-mocked",
            },
        )
        self.order.refresh_from_db()
        self.tx.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CHECKOUT_PENDING)
        self.assertEqual(self.tx.status, PaymentStatus.FAILED)
        self.assertEqual(OrderStatusHistory.objects.filter(order=self.order).count(), 0)
        self.assertRedirects(response, reverse("checkout:checkout"), fetch_redirect_response=False)


class PlaceOrderCodAfterAbandonedOnlineAttemptTests(TestCase):
    """
    A customer who starts checkout with an online gateway (leaving an order
    stuck at CHECKOUT_PENDING when the payment is abandoned), then switches
    to Cash on Delivery and resubmits, must end up with a real PLACED_COD
    order — not one still stuck at CHECKOUT_PENDING, which the admin sees as
    an "abandoned checkout" instead of an order. The checkout form's hidden
    idempotency_key input isn't recomputed when the payment method changes,
    so the COD resubmission commonly arrives with the *same* idempotency_key
    as the earlier abandoned online attempt.
    """

    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="cod-switch-test@example.com",
            password="testpass12345",
            name="Cod Switch Test",
        )
        collection = Collection.objects.create(name="Test Collection", slug="test-collection-cod")
        self.product = Product.objects.create(
            name="Test Yarn",
            slug="test-yarn-cod",
            sku="SKU-TEST-COD-1",
            base_price="500.00",
            mrp="500.00",
            purchase_price="300.00",
            stock_quantity=100,
        )
        self.product.collections.add(collection)
        self._delhivery_patch = patch("delhivery.tasks.create_shipment_for_order.delay")
        self._delhivery_patch.start()
        self.addCleanup(self._delhivery_patch.stop)

        self.cart = Cart.objects.create(customer_profile=self.profile, currency=self.currency)
        CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            quantity=1,
            unit_price_at_add=self.product.base_price,
        )
        self.session = create_checkout_session(cart=self.cart, customer_profile=self.profile)

    def test_cod_resubmission_with_stale_idempotency_key_converts_pending_order(self):
        idempotency_key = f"{self.session.pk}-stale-key-from-first-page-load"

        abandoned_order = place_order(
            checkout_session_id=self.session.pk,
            idempotency_key=idempotency_key,
            gateway_key="razorpay_upi",
            customer_profile=self.profile,
        )
        self.assertEqual(abandoned_order.order_status, OrderStatus.CHECKOUT_PENDING)

        self.session.refresh_from_db()

        cod_order = place_order(
            checkout_session_id=self.session.pk,
            idempotency_key=idempotency_key,
            gateway_key="cod",
            customer_profile=self.profile,
        )

        self.assertEqual(cod_order.pk, abandoned_order.pk)
        self.assertEqual(cod_order.order_status, OrderStatus.PLACED_COD)
        self.assertEqual(Order.objects.filter(cart=self.cart).count(), 1)

    def test_duplicate_cod_conversion_call_does_not_create_second_order(self):
        """
        Simulates a duplicate place_order call landing after the first one
        already converted an abandoned online order to COD, but before
        confirm_payment_success has flipped the session to COMPLETED (the
        window process_payment/confirm_payment_success runs in, outside
        place_order's transaction). The duplicate must return the same order,
        not fall through and create a second one with a second stock decrement.
        """
        idempotency_key_1 = f"{self.session.pk}-first-attempt-key"
        abandoned_order = place_order(
            checkout_session_id=self.session.pk,
            idempotency_key=idempotency_key_1,
            gateway_key="razorpay_upi",
            customer_profile=self.profile,
        )
        self.session.refresh_from_db()

        idempotency_key_2 = f"{self.session.pk}-cod-attempt-key"
        first_cod_call = place_order(
            checkout_session_id=self.session.pk,
            idempotency_key=idempotency_key_2,
            gateway_key="cod",
            customer_profile=self.profile,
        )
        self.assertEqual(first_cod_call.pk, abandoned_order.pk)
        self.assertEqual(first_cod_call.order_status, OrderStatus.PLACED_COD)

        #session.status is still DRAFT here — confirm_payment_success (which
        #flips it to COMPLETED) hasn't run yet, matching the real race window.
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "draft")

        duplicate_call = place_order(
            checkout_session_id=self.session.pk,
            idempotency_key=idempotency_key_2,
            gateway_key="cod",
            customer_profile=self.profile,
        )

        self.assertEqual(duplicate_call.pk, abandoned_order.pk)
        self.assertEqual(Order.objects.filter(cart=self.cart).count(), 1)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 99)


class CheckoutWhatsAppVerificationTests(TestCase):
    """
    The checkout contact number is now gated behind a WhatsApp OTP: an order
    must not be placeable with an unverified phone, however correctly
    *formatted* that phone is — the format regex alone used to be sufficient.
    """

    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="wa-verify-test@example.com", password="testpass12345", name="Verify Test"
        )
        self.address = Address.objects.create(
            customer_profile=self.profile,
            label="Home",
            line1="123 Test Street",
            city="Test City",
            state="Test State",
            pincode="123456",
            is_default=True,
        )
        collection = Collection.objects.create(
            name="WA Verify Collection", slug="wa-verify-collection"
        )
        self.product = Product.objects.create(
            name="Test Yarn",
            slug="wa-verify-yarn",
            sku="SKU-WA-VERIFY-1",
            base_price="500.00",
            mrp="500.00",
            purchase_price="300.00",
            stock_quantity=100,
        )
        self.product.collections.add(collection)
        self._delhivery_patch = patch("delhivery.tasks.create_shipment_for_order.delay")
        self._delhivery_patch.start()
        self.addCleanup(self._delhivery_patch.stop)

        self.client.force_login(self.profile.user)
        cart = Cart.objects.create(customer_profile=self.profile, currency=self.currency)
        CartItem.objects.create(
            cart=cart, product=self.product, quantity=1, unit_price_at_add=self.product.base_price
        )
        create_checkout_session(cart=cart, customer_profile=self.profile)

    def _place_order_data(self, **overrides):
        data = {
            "guest_name": "Verify Test",
            "guest_email": "wa-verify-test@example.com",
            "guest_phone": "9876543210",
            "address_id": str(self.address.pk),
            "gateway_key": "cod",
            "idempotency_key": "wa-verify-order-1",
        }
        data.update(overrides)
        return data

    def test_unverified_phone_blocks_order_placement(self) -> None:
        response = self.client.post(reverse("checkout:place-order"), data=self._place_order_data())
        self.assertContains(response, "verify your WhatsApp number")
        self.assertFalse(Order.objects.exists())

    def test_verifying_a_different_phone_still_blocks_order_placement(self) -> None:
        session = self.client.session
        session["checkout_verified_phone"] = "919999999999"
        session.save()

        response = self.client.post(
            reverse("checkout:place-order"),
            data=self._place_order_data(guest_phone="9876543210"),
        )
        self.assertContains(response, "verify your WhatsApp number")
        self.assertFalse(Order.objects.exists())

    @patch("whatsapp.services.send_otp")
    def test_verified_phone_allows_order_placement(self, mock_send_otp) -> None:
        phone = "9876543221"
        captured = {}

        def _capture(phone, otp_code):
            captured["otp_code"] = otp_code

        mock_send_otp.side_effect = _capture

        send_response = self.client.post(
            reverse("checkout:whatsapp-otp-send"), data={"phone": phone}
        )
        self.assertEqual(send_response.status_code, 200)
        self.assertTrue(send_response.json()["success"])
        mock_send_otp.assert_called_once()

        verify_response = self.client.post(
            reverse("checkout:whatsapp-otp-verify"),
            data={"phone": phone, "otp_code": captured["otp_code"]},
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(verify_response.json()["success"])

        response = self.client.post(
            reverse("checkout:place-order"), data=self._place_order_data(guest_phone=phone)
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.order_status, OrderStatus.PLACED_COD)

    @patch("whatsapp.services.send_otp")
    def test_wrong_otp_code_does_not_verify(self, mock_send_otp) -> None:
        phone = "9876543222"
        captured = {}
        mock_send_otp.side_effect = lambda phone, otp_code: captured.update(otp_code=otp_code)

        self.client.post(reverse("checkout:whatsapp-otp-send"), data={"phone": phone})
        wrong_code = f"{(int(captured['otp_code']) + 1) % 1_000_000:06d}"

        verify_response = self.client.post(
            reverse("checkout:whatsapp-otp-verify"),
            data={"phone": phone, "otp_code": wrong_code},
        )
        self.assertEqual(verify_response.status_code, 400)
        self.assertFalse(verify_response.json()["success"])

        response = self.client.post(
            reverse("checkout:place-order"), data=self._place_order_data(guest_phone=phone)
        )
        self.assertContains(response, "verify your WhatsApp number")
        self.assertFalse(Order.objects.exists())


class CheckoutEmailOptionalTests(TestCase):
    """
    Email is optional at checkout now that the WhatsApp-OTP-verified phone is
    itself a sufficient, unique identity — a true anonymous guest (no account,
    no email) must still be able to place an order, falling back to
    accounts.services.login_or_create_customer_by_phone.
    """

    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="INR",
            defaults={"symbol": "₹", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        collection = Collection.objects.create(
            name="No Email Collection", slug="no-email-collection"
        )
        self.product = Product.objects.create(
            name="Test Yarn",
            slug="no-email-yarn",
            sku="SKU-NO-EMAIL-1",
            base_price="500.00",
            mrp="500.00",
            purchase_price="300.00",
            stock_quantity=100,
        )
        self.product.collections.add(collection)
        self._delhivery_patch = patch("delhivery.tasks.create_shipment_for_order.delay")
        self._delhivery_patch.start()
        self.addCleanup(self._delhivery_patch.stop)

        # force an anonymous session, then give it a cart — mirrors how an
        # unauthenticated guest's cart is resolved by session_key.
        session = self.client.session
        session.save()
        cart = Cart.objects.create(session_key=session.session_key, currency=self.currency)
        CartItem.objects.create(
            cart=cart, product=self.product, quantity=1, unit_price_at_add=self.product.base_price
        )
        create_checkout_session(cart=cart, customer_profile=None, session_key=session.session_key)

    def _verify_phone(self, phone: str) -> None:
        captured = {}
        with patch("whatsapp.services.send_otp") as mock_send_otp:
            mock_send_otp.side_effect = lambda phone, otp_code: captured.update(otp_code=otp_code)
            self.client.post(reverse("checkout:whatsapp-otp-send"), data={"phone": phone})
        self.client.post(
            reverse("checkout:whatsapp-otp-verify"),
            data={"phone": phone, "otp_code": captured["otp_code"]},
        )

    def test_guest_with_no_email_can_place_order(self) -> None:
        phone = "9876543230"
        self._verify_phone(phone)

        response = self.client.post(
            reverse("checkout:place-order"),
            data={
                "guest_name": "No Email Guest",
                "guest_email": "",
                "guest_phone": phone,
                "address_id": "",
                "guest_address_line1": "456 Guest Lane",
                "guest_city": "Guest City",
                "guest_state": "Guest State",
                "guest_pincode": "654321",
                "gateway_key": "cod",
                "idempotency_key": "no-email-order-1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.order_status, OrderStatus.PLACED_COD)

        profile = order.customer_profile
        self.assertIsNotNone(profile)
        self.assertEqual(profile.phone, "919876543230")
        self.assertTrue(profile.phone_verified)
        self.assertFalse(profile.notify_via_email)
        self.assertTrue(profile.user.email.endswith("@phone.samruddhi.local"))
