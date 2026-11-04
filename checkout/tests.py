"""Tests for the Stripe browser-return checkout flow."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Address
from accounts.services import register_customer_email
from cart.models import Cart, CartItem
from catalog.models import Collection, Product
from checkout.services import create_checkout_session, place_order
from core.models import Currency
from orders.models import Order, OrderStatus, OrderStatusHistory
from payments.models import PaymentStatus, PaymentTransaction


@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
class StripeReturnViewTests(TestCase):
    """
    stripe_return_view must verify the Checkout Session's actual
    payment_status server-side before confirming anything — the browser
    landing on the return URL is only a UX signal, never proof of payment.
    """

    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="AED",
            defaults={"symbol": "AED", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="stripe-return-test@example.com",
            password="testpass12345",
            name="Stripe Return Test",
        )
        collection = Collection.objects.create(name="Test Collection", slug="test-collection-stripe")
        self.product = Product.objects.create(
            name="Test Yarn",
            slug="test-yarn-stripe",
            sku="SKU-TEST-STRIPE-1",
            base_price="500.00",
            mrp="500.00",
            purchase_price="300.00",
            stock_quantity=100,
        )
        self.product.collections.add(collection)

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
            idempotency_key="stripe-return-test-order-1",
            gateway_key="stripe",
            customer_profile=self.profile,
        )
        self.tx = PaymentTransaction.objects.create(
            order=self.order,
            gateway_key="stripe",
            amount=self.order.total_amount,
            currency=self.order.currency,
            status=PaymentStatus.PENDING,
            external_intent_id="cs_test_1",
        )
        self.return_url = reverse("checkout:stripe-return")
        self.client.force_login(self.profile.user)

    @patch("payments.adapters.concrete._get_stripe_credentials", return_value=("pk_test", "sk_test"))
    @patch("stripe.checkout.Session.retrieve")
    def test_paid_session_confirms_order(self, mock_retrieve, mock_creds):
        mock_retrieve.return_value = {
            "payment_status": "paid",
            "payment_intent": "pi_real",
            "status": "complete",
        }

        response = self.client.get(self.return_url, {"session_id": "cs_test_1"})

        self.order.refresh_from_db()
        self.tx.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CONFIRMED)
        self.assertEqual(self.tx.status, PaymentStatus.SUCCESS)
        self.assertEqual(self.tx.external_transaction_id, "pi_real")
        self.assertRedirects(
            response,
            reverse("checkout:confirmation", kwargs={"order_id": self.order.pk}),
            fetch_redirect_response=False,
        )

    @patch("payments.adapters.concrete._get_stripe_credentials", return_value=("pk_test", "sk_test"))
    @patch("stripe.checkout.Session.retrieve")
    def test_expired_unpaid_session_marks_payment_failed(self, mock_retrieve, mock_creds):
        mock_retrieve.return_value = {
            "payment_status": "unpaid",
            "payment_intent": "",
            "status": "expired",
        }

        response = self.client.get(self.return_url, {"session_id": "cs_test_1"})

        self.order.refresh_from_db()
        self.tx.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CHECKOUT_PENDING)
        self.assertEqual(self.tx.status, PaymentStatus.FAILED)
        self.assertEqual(OrderStatusHistory.objects.filter(order=self.order).count(), 0)
        self.assertRedirects(response, reverse("checkout:checkout"), fetch_redirect_response=False)

    @patch("payments.adapters.concrete._get_stripe_credentials", return_value=("pk_test", "sk_test"))
    @patch("stripe.checkout.Session.retrieve")
    def test_still_open_unpaid_session_shows_processing_not_failure(self, mock_retrieve, mock_creds):
        """An async payment method awaiting confirmation isn't a failure yet —
        the webhook (async_payment_succeeded/failed) is what actually
        converges it; the return page just shows processing in the meantime."""
        mock_retrieve.return_value = {
            "payment_status": "unpaid",
            "payment_intent": "pi_pending",
            "status": "open",
        }

        response = self.client.get(self.return_url, {"session_id": "cs_test_1"})

        self.order.refresh_from_db()
        self.tx.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CHECKOUT_PENDING)
        self.assertEqual(self.tx.status, PaymentStatus.PENDING)
        self.assertRedirects(
            response,
            reverse("checkout:confirmation", kwargs={"order_id": self.order.pk}),
            fetch_redirect_response=False,
        )

    def test_missing_session_id_redirects_to_checkout(self):
        response = self.client.get(self.return_url)
        self.assertRedirects(response, reverse("checkout:checkout"), fetch_redirect_response=False)

    def test_unknown_session_id_redirects_to_checkout(self):
        response = self.client.get(self.return_url, {"session_id": "cs_never_existed"})
        self.assertRedirects(response, reverse("checkout:checkout"), fetch_redirect_response=False)


class CheckoutOwnershipTests(TestCase):
    """
    Regression tests for the ownership check added to checkout_confirmation_view
    and stripe_pay_view — previously both used a bare get_object_or_404 with no
    ownership check at all, letting any signed-in user view another customer's
    order by guessing/enumerating the order_id in the URL.
    """

    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="AED",
            defaults={"symbol": "AED", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.owner = register_customer_email(
            email="order-owner@example.com", password="testpass12345", name="Owner"
        )
        self.intruder = register_customer_email(
            email="intruder@example.com", password="testpass12345", name="Intruder"
        )
        collection = Collection.objects.create(name="Ownership Collection", slug="ownership-collection")
        self.product = Product.objects.create(
            name="Test Yarn",
            slug="ownership-yarn",
            sku="SKU-OWNERSHIP-1",
            base_price="500.00",
            mrp="500.00",
            purchase_price="300.00",
            stock_quantity=100,
        )
        self.product.collections.add(collection)

        cart = Cart.objects.create(customer_profile=self.owner, currency=self.currency)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=1,
            unit_price_at_add=self.product.base_price,
        )
        session = create_checkout_session(cart=cart, customer_profile=self.owner)
        self.order = place_order(
            checkout_session_id=session.pk,
            idempotency_key="ownership-test-order-1",
            gateway_key="stripe",
            customer_profile=self.owner,
        )
        PaymentTransaction.objects.create(
            order=self.order,
            gateway_key="stripe",
            amount=self.order.total_amount,
            currency=self.order.currency,
            status=PaymentStatus.PENDING,
            external_intent_id="cs_ownership_1",
        )

    def test_other_user_cannot_view_confirmation_page(self):
        self.client.force_login(self.intruder.user)
        response = self.client.get(reverse("checkout:confirmation", kwargs={"order_id": self.order.pk}))
        self.assertEqual(response.status_code, 404)

    def test_other_user_cannot_open_pay_view(self):
        self.client.force_login(self.intruder.user)
        response = self.client.get(reverse("checkout:stripe-pay", kwargs={"order_id": self.order.pk}))
        self.assertEqual(response.status_code, 404)

    def test_owner_can_view_confirmation_page(self):
        self.client.force_login(self.owner.user)
        response = self.client.get(reverse("checkout:confirmation", kwargs={"order_id": self.order.pk}))
        self.assertEqual(response.status_code, 200)


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
            gateway_key="stripe",
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
            gateway_key="stripe",
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


class StripeGatewayFailureTests(TestCase):
    """
    place_order already committed a real order (CHECKOUT_PENDING) before
    process_payment ever talks to Stripe — a gateway outage or bad
    credentials at that point must show the customer a friendly retry
    message, not a raw 500, and must not corrupt the order.
    """

    def setUp(self) -> None:
        self.currency, _ = Currency.objects.get_or_create(
            code="AED",
            defaults={"symbol": "AED", "exchange_rate_to_base": "1.00000000", "is_default": True},
        )
        self.profile = register_customer_email(
            email="stripe-failure-test@example.com", password="testpass12345", name="Stripe Failure Test"
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
        collection = Collection.objects.create(name="Stripe Failure Collection", slug="stripe-failure-collection")
        self.product = Product.objects.create(
            name="Test Yarn",
            slug="stripe-failure-yarn",
            sku="SKU-STRIPE-FAILURE-1",
            base_price="500.00",
            mrp="500.00",
            purchase_price="300.00",
            stock_quantity=100,
        )
        self.product.collections.add(collection)

        self.client.force_login(self.profile.user)
        cart = Cart.objects.create(customer_profile=self.profile, currency=self.currency)
        CartItem.objects.create(
            cart=cart, product=self.product, quantity=1, unit_price_at_add=self.product.base_price
        )
        create_checkout_session(cart=cart, customer_profile=self.profile)

    def _verify_phone(self, phone: str) -> None:
        captured = {}
        with patch("whatsapp.services.send_otp") as mock_send_otp:
            mock_send_otp.side_effect = lambda phone, otp_code: captured.update(otp_code=otp_code)
            self.client.post(reverse("checkout:whatsapp-otp-send"), data={"phone": phone})
        self.client.post(
            reverse("checkout:whatsapp-otp-verify"),
            data={"phone": phone, "otp_code": captured["otp_code"]},
        )

    @patch("payments.adapters.concrete._get_stripe_credentials", return_value=("pk_test", "sk_test_bad"))
    @patch("stripe.checkout.Session.create", side_effect=Exception("simulated Stripe outage"))
    def test_gateway_outage_shows_friendly_error_not_500(self, mock_create, mock_creds):
        phone = "9876543240"
        self._verify_phone(phone)

        response = self.client.post(
            reverse("checkout:place-order"),
            data={
                "guest_name": "Stripe Failure Test",
                "guest_email": "stripe-failure-test@example.com",
                "guest_phone": phone,
                "address_id": str(self.address.pk),
                "gateway_key": "stripe",
                "idempotency_key": "stripe-failure-order-1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "temporarily unavailable")
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.order_status, OrderStatus.CHECKOUT_PENDING)
        #process_payment is one atomic block — create_payment_intent raising
        #rolls back the PaymentTransaction it was about to create along with it,
        #so nothing here to assert about PaymentTransaction rows; the order
        #itself (committed by the earlier, separate place_order call) is what
        #must survive intact and retriable.


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
