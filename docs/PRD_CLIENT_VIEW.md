# Product Requirements Document — Client's View

**Product:** Floward Clone — Luxury Flowers, Cakes, Chocolates & Gifts E-Commerce Platform
**Audience:** Business stakeholders, product owners, designers, QA, and onboarding engineers
**Perspective:** What the product *does* for its users — features, journeys, and rules — not how it is coded (see the technical docs for that).

Related documents:
- [`docs/TECH_STOREFRONT.md`](TECH_STOREFRONT.md) — storefront technical reference
- [`docs/TECH_ADMIN_DASHBOARD.md`](TECH_ADMIN_DASHBOARD.md) — admin dashboard technical reference

---

## 1. Product Vision

A premium, mobile-first gifting marketplace inspired by [Floward Qatar](https://floward.com/en-qa). Customers shop luxury flowers, cakes, chocolates, and curated gifts, personalize each gift with a plug-and-play **Gift Customization** engine (greeting cards, wrapping, ribbons, photos, add-ons, personal messages), and schedule same-day or future delivery down to a specific time slot — including midnight surprises. The platform is bilingual (English / Arabic with full RTL), multi-currency, and supports both individual (B2C) shoppers and corporate (B2B) clients.

### Product pillars

| Pillar | What it means for the customer |
|--------|-------------------------------|
| **Luxury gifting, not just retail** | Every product can be turned into a personalized gift, previewed before purchase. |
| **Occasion-driven discovery** | Shop by occasion (birthday, anniversary, condolences…), recipient, or category. |
| **Reliable timed delivery** | Real delivery slots with capacity limits, same-day cutoffs, and midnight delivery. |
| **Bilingual & regional** | English/Arabic, RTL, multi-currency, multi-country/city delivery. |
| **For everyone** | Guests, registered shoppers, subscribers, and corporate accounts. |

---

## 2. Personas

| Persona | Description | Primary goals |
|---------|-------------|---------------|
| **Guest shopper** | Browses without an account, may buy via guest checkout. | Fast discovery and checkout without sign-up friction. |
| **Registered customer** | Has an account and profile. | Save addresses/payment methods, track orders, wishlist, gift reminders, subscriptions. |
| **Gift sender** | Sending to someone else. | Personalize the gift, hide price (gift receipt), send anonymously, schedule delivery + message. |
| **Subscriber** | Wants recurring flower/gift deliveries. | Set frequency, pause/resume/cancel a subscription. |
| **Corporate buyer (B2B)** | Company account after approval. | Request quotes, place recurring bulk orders, receive invoices. |
| **Store staff / admin** | Operates the business. | Manage catalog, fulfill orders, run promotions, read reports (see admin dashboard PRD/tech). |

---

## 3. Feature Catalog

### 3.1 Discovery & Browsing
- **CMS-driven homepage** composed of configurable sections: hero slider, shop-by-occasion, shop-by-recipient, shop-by-category, product collections (premium / seasonal / luxury), same-day delivery rail, trending, best-sellers, featured brands, promotional banners, marketing feature cards, customer reviews, Instagram gallery, and newsletter signup.
- **Product Listing Page (PLP)** with filtering (category, occasion, recipient, brand, price), sorting (newest, price, popularity), and pagination (24/page). Category and occasion landing pages have shareable, canonical URLs.
- **Live search** with type-ahead suggestions.
- **Product Detail Page (PDP)**: image/video gallery, variant selection with live price updates, delivery-time estimate for a chosen city, customer reviews with ratings, and related products.
- **Recently viewed** products and **mega-menu** category navigation.

### 3.2 Gift Customization (signature feature)
On eligible products, the customer opens a **gift builder** and can:
- Write a **personal message** (with live character counter and max-length rule).
- Choose a **greeting card** design (optionally occasion-specific).
- Choose **gift wrapping**, **ribbon**, and **photo upload** options.
- Add **eligible add-ons** (e.g., chocolates, balloons) that are in stock.
- Toggle **send anonymously**, **gift receipt** (hide price), and **midnight delivery** where permitted.
- See a live **Order Preview** with itemized pricing before adding to cart.

Each customization is captured as an **immutable snapshot** so the gift the customer configured is exactly what appears in the cart, at checkout, and on the final order.

### 3.3 Cart & Wishlist
- Slide-out **cart drawer** with line items, gift-customization badges, quantity, and totals.
- Add/remove items, apply **coupon codes**, and see delivery charges recalculated per destination city.
- **Wishlist** for guests (session) and registered users (persistent), with **shareable read-only wishlist links**.

### 3.4 Checkout & Payments
- **Multi-step checkout**: select delivery address, delivery date + time slot, review gift previews, and pay.
- Supports **saved addresses** and **saved (tokenized) payment methods** for registered users; **guest checkout** via a signed token.
- **Delivery slot reservation** with capacity limits (no overbooking) and same-day cutoff enforcement.
- **Idempotent order placement** — a network retry or double-click never creates duplicate orders.
- Multiple **payment gateways** (adapter-based); synchronous capture or asynchronous confirmation via webhook; **gift voucher / gift card** redemption as a payment method.
- **Order confirmation** page with order number.

### 3.5 Orders & Tracking
- **Order tracking page** with a status timeline: Received → Preparing → Packaging → Ready → Out for Delivery → Delivered (with Cancelled / Refunded paths).
- **Proof of delivery** capture on the operations side.
- Customers see order history in their account dashboard.

### 3.6 Accounts & Authentication
- Sign up / log in with **email + password**, **phone OTP**, or **Google** sign-in.
- **Forgot / reset password** via OTP.
- **Rate limiting** on OTP requests and logins to prevent abuse.
- **Customer dashboard**: profile, recent orders, default address, saved addresses, saved payment methods, unread notifications.

### 3.7 Subscriptions & Gift Reminders
- **Subscriptions**: recurring delivery of a product on a chosen frequency; pause, resume, or cancel.
- **Gift reminders**: a personal gifting calendar (e.g., birthdays, anniversaries) that notifies the customer ahead of the date.

### 3.8 Corporate (B2B)
- **Corporate registration** with company name and trade license (requires admin approval).
- **Corporate dashboard**: pending quotes, active recurring orders, and invoice history.
- **Quote requests**, approval-to-order conversion, **recurring bulk orders**, and **invoice generation**.

### 3.9 Promotions & Marketing
- **Coupons** (percentage or fixed, with usage limits, minimum order, category scope, and date windows).
- **Flash sales** with time-boxed discounts surfaced on PLP/PDP.
- **Gift cards / vouchers**.
- **Newsletter** subscribe/unsubscribe.
- **Abandoned-cart recovery** emails.
- **Referrals**.

### 3.10 Notifications
- **Order status** updates and **gift reminders** delivered via in-app notification, email, SMS, and WhatsApp (per customer preferences).

### 3.11 Internationalization & Regionalization
- **English / Arabic** with full **RTL** layout.
- **Multi-currency** display with a default base currency and live conversion.
- **Multi-country / multi-city** delivery with per-city charges, cutoffs, and slots.
- Language, currency, and delivery country are switchable from the header and update the page instantly (without a full reload).

### 3.12 SEO & Performance
- Per-page meta titles/descriptions, Open Graph images, Product JSON-LD (with ratings), XML sitemap, hreflang (EN/AR), and canonical URLs.
- Cache-first homepage and pre-aggregated reporting for fast, consistent pages.

---

## 4. Core User Flows

### 4.1 Browse → Personalize → Buy (happy path)

```
Homepage / PLP
   → Product Detail Page (choose variant, see delivery estimate)
      → Gift Builder (message, card, wrap, ribbon, add-ons, options)
         → Live Order Preview
            → Add to Cart (gift snapshot attached)
               → Cart Drawer (apply coupon, review totals)
                  → Checkout (address → delivery date + slot → payment)
                     → Place Order (idempotent) → Payment
                        → Order Confirmation (order number)
                           → Order Tracking (status timeline)
```

### 4.2 Guest checkout
```
Add to cart as guest → Checkout → Issue signed guest token
   → Provide delivery + payment details → Place order → Confirmation
```

### 4.3 Registration / login
```
Register (email/password | phone OTP | Google)
   → Account Dashboard (profile, orders, addresses, payment methods, notifications)
```
OTP flow: request OTP (rate-limited) → receive SMS → verify → logged in / signed up.

### 4.4 Subscription
```
Choose product + frequency + address + first run date
   → Subscription created (recurring schedule)
   → System places orders automatically on schedule
   → Customer can pause / resume / cancel anytime
```

### 4.5 Gift reminder
```
Add occasion + date + recipient to gift calendar
   → System notifies customer ahead of the date (email/SMS/WhatsApp/in-app)
```

### 4.6 Corporate (B2B)
```
Register corporate account (company + trade license) → Pending
   → Admin approves
   → Corporate dashboard: request quote (optionally recurring)
      → Admin approves quote → converts to order
      → Invoice generated → visible in invoice history
```

### 4.7 Preference switching (language / currency / country)
```
Header selector → choose EN/AR, currency, or delivery country
   → Page shell re-renders in place with new locale/currency/region
```

---

## 5. Business Rules (customer-visible)

| Area | Rule |
|------|------|
| Gift message | Enforced maximum length; live counter; blocked if the product config disallows messages. |
| Gift options | Only **active** cards/wraps/ribbons/photos are selectable; add-ons must be **in stock**; anonymous/gift-receipt/midnight options only when the product permits them. |
| Gift snapshot | Immutable once built — cart, checkout, and order all show the exact same personalization and pricing. |
| Delivery slots | Capacity-limited (no overbooking); same-day offered only before the city cutoff; midnight delivery only where allowed. |
| Delivery charge | Derived from the destination city; recalculated when the destination changes; zero for an empty cart. |
| Coupons | Validated for date window, usage limits, minimum order value, and category scope; discount clamped so totals never go negative. |
| Order placement | Idempotent — duplicate submissions return the same order, never a second one. |
| Stock | Orders never oversell; stock is decremented atomically at order placement. |
| Order status | Follows a fixed state machine; invalid jumps are rejected; every change is recorded in history and notifies the customer. |
| Payments | No raw card data is stored (PCI-safe); only tokenized payment methods; success/failure converges to a single confirmed state regardless of gateway. |
| Auth security | OTP requests (3 / 10 min) and logins (10 / 10 min) are rate-limited. |
| Reviews | Submitted reviews are **pending** until moderated; only approved reviews show publicly. |

---

## 6. Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| **Performance** | Homepage cache-first (0 DB queries on cache hit); key pages audited for query counts and duplicates; pre-aggregated reports. Target p95: homepage <300ms, PLP <200ms, PDP <250ms, place order <500ms (see [`docs/PHASE10_REPORT.md`](PHASE10_REPORT.md)). |
| **Availability** | Health-check endpoint for load balancers; external uptime monitoring recommended. |
| **Security** | CSRF protection, RBAC for staff, rate limiting, PCI-safe tokenized payments, hardened production settings (HSTS, secure cookies, SSL redirect). |
| **Accessibility & SEO** | Semantic templates, meta/OG/JSON-LD, sitemap, hreflang, canonical URLs; Lighthouse ≥90 targets on production. |
| **Internationalization** | EN/AR, RTL, timezone `Asia/Qatar`, translatable content via model translation. |
| **Scalability** | Redis caching, Celery background processing, DB connection pooling, S3/CDN media in production. |
| **Reliability** | Idempotent order placement, atomic stock and slot reservation, background retries for notifications. |

---

## 7. Platform Surface Map (customer-facing pages)

| Journey | Page / entry point |
|---------|--------------------|
| Home | `/` (bilingual: `/ar/` for Arabic) |
| Shop / PLP | `/shop/`, `/shop/category/<slug>/` |
| Product detail | `/shop/products/<slug>/` |
| Gift builder | `/gifting/products/<slug>/builder/` |
| Cart drawer | `/cart/drawer/` |
| Checkout | `/checkout/` |
| Order confirmation | (rendered after placing order) |
| Order tracking | `/orders/<id>/tracking/` |
| Account (login/register/dashboard) | `/accounts/login/email/`, `/accounts/register/`, `/accounts/dashboard/` |
| Corporate dashboard | `/corporate/dashboard/` |

For the complete route inventory and behavior, see [`docs/TECH_STOREFRONT.md`](TECH_STOREFRONT.md).

---

## 8. Out of Scope / Future Enhancements

- Live delivery-driver GPS tracking on the customer map.
- In-app live chat / support console.
- Loyalty points program (referrals exist; points ledger not yet surfaced).
- Native mobile apps (current experience is responsive web + HTMX).
- Customer-facing self-service returns/RMA portal (refunds are handled operationally today).

---

## 9. Glossary

| Term | Meaning |
|------|---------|
| **PLP** | Product Listing Page (grid of products with filters). |
| **PDP** | Product Detail Page (single product). |
| **Gift snapshot** | Immutable saved record of a gift's personalization + pricing. |
| **Slot** | A specific delivery time window on a date, with limited capacity. |
| **Idempotency key** | A token ensuring a repeated place-order request produces one order. |
| **Flash sale** | Time-boxed promotional discount on selected products. |
| **B2B / Corporate** | Company accounts with quotes, recurring bulk orders, and invoices. |
| **RTL** | Right-to-left layout used for Arabic. |
