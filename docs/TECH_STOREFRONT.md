# Technical Documentation — Storefront

**Product:** Floward Clone (Django 5) — customer-facing storefront
**Scope:** Every storefront folder, file, and function (models, selectors, services, views, urls, forms, tasks, signals, templates, static, config). The admin dashboard is documented separately in [`docs/TECH_ADMIN_DASHBOARD.md`](TECH_ADMIN_DASHBOARD.md). Product/feature intent is in [`docs/PRD_CLIENT_VIEW.md`](PRD_CLIENT_VIEW.md).

> **Convention note:** Every business app follows a strict layered architecture. Files that exist as generated placeholders (created by `scripts/scaffold_apps.py`) are called out as *stub* / *empty placeholder*. Selector functions document their query-count guarantees in code; those counts are reproduced here where relevant.

---

## 1. Architecture Overview

### 1.1 Layered architecture (per app)

```
app/
├── models.py          # Data layer only (tables, choices, model methods)
├── selectors.py       # All READ queries (optimized, query-count documented)
├── services.py        # All WRITES and business rules (mostly @transaction.atomic)
├── forms.py           # Form/validation layer
├── views.py           # Thin HTTP layer — parse request, call selector/service, render
├── urls.py            # Route table (app_name namespaced)
├── tasks.py           # Celery background tasks
├── signals.py         # Cross-app side effects only (custom signals + receivers)
├── admin.py           # Django admin registrations
├── templates/<app>/   # App templates + partials
└── tests/             # test_models / test_selectors / test_services / test_views
```

**Golden rule:** views never touch the ORM directly. Reads go through `selectors`, writes go through `services`. Cross-app interactions happen through service calls or Django signals, never by reaching into another app's ORM.

### 1.2 Request lifecycle

```
Browser / HTMX request
  → config/urls.py (routing, i18n_patterns, sitemaps)
  → LocaleMiddleware (activate en/ar) + session + CSRF + auth
  → app view (thin)
      → selectors.py  (reads)  and/or  services.py (writes)
      → core.context_processors.storefront (global template context)
  → template render (templates/base.html + app template/partials)
  → HTMX partial swap OR full HTML response
```

### 1.3 The 16 installed apps

| App | Responsibility | HTTP surface |
|-----|----------------|--------------|
| `core` | Shared mixins, currency, SEO, sitemaps, RBAC/rate-limit, preference switching, health | Yes |
| `accounts` | Auth, profiles, addresses, payment methods, wishlist, subscriptions, gift reminders, corporate registration | Yes (mostly JSON) |
| `catalog` | Products, categories, occasions, brands, recipients, variants, reviews | Yes |
| `gifting` | Gift customization engine (ContentType-based) | Yes |
| `cart` | Shopping cart + drawer + wishlist toggle | Yes |
| `checkout` | Checkout session, order placement | Yes |
| `orders` | Order lifecycle + tracking | Yes (tracking) |
| `payments` | Payment processing + webhooks | JSON webhook only |
| `delivery` | Countries, cities, zones, slots, bookings | No (service/selector only) |
| `recurring` | Generic recurrence engine (registry + beat) | No |
| `corporate` | B2B accounts, quotes, invoices, recurring orders | Yes (dashboard) |
| `marketing` | Coupons, gift cards, flash sales, newsletter, abandoned carts, referrals | No (service/selector only) |
| `cms` | CMS-driven homepage + content models | Yes (homepage) |
| `notifications` | Email/SMS/WhatsApp/in-app dispatch | No (service/task/signal) |
| `reports` | Pre-aggregated analytics | JSON endpoint |
| `dashboard` | Admin dashboard (see separate doc) | Yes |

---

## 2. Project Configuration — `config/`

| File | Purpose |
|------|---------|
| `config/__init__.py` | Loads the Celery app at Django startup (`celery_app`). |
| `config/settings/__init__.py` | Package marker; environments imported explicitly. |
| `config/settings/base.py` | Shared settings (apps, middleware, DB, cache, Celery, i18n, static/media, auth). |
| `config/settings/dev.py` | Development: `DEBUG=True`, LocMem cache, console email, eager Celery, optional debug toolbar. |
| `config/settings/staging.py` | Staging: production-like, secure cookies, no HSTS/SSL redirect. |
| `config/settings/prod.py` | Production: hardened security (HSTS, SSL redirect, secure cookies), optional Sentry. |
| `config/urls.py` | Root URL config: admin, sitemaps, i18n_patterns, app includes, dev static/media. |
| `config/celery.py` | Creates `Celery("config")`, reads `CELERY_*` settings, autodiscovers tasks. |
| `config/asgi.py` / `wsgi.py` | ASGI/WSGI entrypoints (default settings module = prod). |

### 2.1 `settings/base.py` highlights
- **Env loading** via `django-environ` from `BASE_DIR/.env`.
- **INSTALLED_APPS**: `modeltranslation` first (before admin), Django contrib (incl. `sitemaps`), then the 16 local apps.
- **MIDDLEWARE**: Security → Session → **Locale (i18n)** → Common → CSRF → Auth → Messages → XFrameOptions.
- **TEMPLATES**: `DIRS=[BASE_DIR/templates]`, `APP_DIRS=True`; custom context processors `core.context_processors.storefront` and `dashboard.context_processors.dashboard_chrome`.
- **DATABASES**: `DATABASE_URL` (SQLite dev fallback); Postgres gets `CONN_MAX_AGE=600`, health checks, `statement_timeout=30000ms`, psycopg connection pool (min 2 / max 10).
- **CACHES**: `django_redis.cache.RedisCache` at `REDIS_URL`.
- **Celery**: broker DB1, result backend DB2, JSON serialization, `CELERY_TIMEZONE="Asia/Qatar"`.
- **Static/Media**: `STATIC_ROOT=staticfiles`, `STATICFILES_DIRS=[static]`; `MEDIA_ROOT=media`; optional S3 via `USE_S3`.
- **Auth**: `LOGIN_URL=/accounts/login/email/`, `LOGIN_REDIRECT_URL=/accounts/dashboard/`, Google client id, OTP/guest-token settings.
- **i18n**: `LANGUAGES=[en, ar]`, `LOCALE_PATHS=[locale]`, `TIME_ZONE="Asia/Qatar"`, modeltranslation (en default, AR→EN fallback).
- **Misc**: `DEFAULT_AUTO_FIELD=BigAutoField`; `MESSAGE_TAGS` maps ERROR→`danger`; console logging.

### 2.2 `CELERY_BEAT_SCHEDULE`

| Key | Task | Interval |
|-----|------|----------|
| `celery-health-check-every-minute` | `core.tasks.celery_health_check` | 60s |
| `process-due-recurring-schedules-daily` | `recurring.tasks.process_due_schedules` | 86400s |
| `send-due-gift-reminders-daily` | `accounts.tasks.send_due_gift_reminders` | 86400s |
| `aggregate-daily-reports-nightly` | `reports.tasks.aggregate_daily_reports` | 86400s |
| `scan-abandoned-carts-hourly` | `marketing.tasks.scan_abandoned_carts` | 3600s |
| `refresh-sitemap-daily` | `core.tasks.refresh_sitemap_cache` | 86400s |

### 2.3 Root URL map (`config/urls.py`)

**Non-i18n (no language prefix):**
| Route | Include |
|-------|---------|
| `admin/` | Django admin |
| `sitemap.xml`, `sitemap-<section>.xml` | sitemaps (products, categories, occasions, blog, pages) |
| `` | `core.urls` |
| `accounts/` | `accounts.urls` |
| `payments/` | `payments.urls` |
| `reports/` | `reports.urls` |
| `dashboard/` | `dashboard.urls` |

**`i18n_patterns(prefix_default_language=False)` (EN unprefixed, AR under `/ar/`):**
| Route | Include |
|-------|---------|
| `` | `cms.urls` (homepage) |
| `shop/` | `catalog.urls` |
| `gifting/` | `gifting.urls` |
| `cart/` | `cart.urls` |
| `checkout/` | `checkout.urls` |
| `orders/` | `orders.urls` |
| `corporate/` | `corporate.urls` |

---

## 3. App: `core`

Cross-cutting foundation: shared model mixins, currency, SEO, sitemaps, RBAC/rate-limiting, storefront context, and preference (language/currency/country) switching.

### 3.1 `core/models.py`
| Model / class | Purpose |
|---------------|---------|
| `TimeStampedModel` | Abstract base adding `created_at` / `updated_at`. |
| `SoftDeleteQuerySet` / `SoftDeleteManager` | Queryset/manager filtering out soft-deleted rows. |
| `SoftDeleteModel` | Abstract base with `is_deleted` + soft-delete manager. |
| `SEOModel` | Abstract base with meta title/description/OG image (translatable). |
| `Currency` | Storefront currency (code, symbol, exchange rate, `is_default`). |
| `SiteSettings` | Singleton row (pk=1) for global site configuration. |

### 3.2 `core/selectors.py`
- `get_default_currency() -> Currency|None` — default currency (cached 5 min).
- `invalidate_default_currency_cache() -> None` — clears the cache.
- `get_currency_by_code(*, code) -> Currency|None` — currency by ISO code.

### 3.3 `core/services.py`
- `get_site_settings() -> SiteSettings` — singleton `get_or_create` (pk=1).
- `create_currency(*, code, symbol, exchange_rate_to_base, is_default=False)` — create currency, demote others if default (atomic).
- `set_default_currency(*, currency)` — promote one currency default, demote rest (atomic).

### 3.4 `core/views.py` (thin; delegate to `page_rerender.py`)
| View | Response | Decorators |
|------|----------|-----------|
| `health_view(request)` | plain-text `"ok"` for LB probes | — |
| `set_language_view(request)` | persist en/ar to session + re-render shell (HTMX) | `@require_POST` |
| `set_currency_view(request)` | persist currency to session | `@require_POST` |
| `set_country_view(request)` | persist delivery country to session | `@require_POST` |

### 3.5 `core/urls.py` (`app_name="core"`)
| Route | View | Name |
|-------|------|------|
| `health/` | `health_view` | `health` |
| `preferences/language/` | `set_language_view` | `set-language` |
| `preferences/currency/` | `set_currency_view` | `set-currency` |
| `preferences/country/` | `set_country_view` | `set-country` |

### 3.6 `core/page_rerender.py` (HTMX shell re-render)
- `htmx_current_path(request)` — path+query of the HTMX-initiating page.
- `is_htmx_request(request)` — True when `HX-Request` header set.
- `_strip_language_prefix(path)` — map localized URL back to canonical route.
- `_resolve_target(target_path)` — resolve a path independent of active language.
- `_dispatch_inner_get(request, target_path, *, language)` — internally re-dispatch a GET.
- `rerender_app_shell(request)` — re-render the app-shell fragment for preference updates.

### 3.7 `core/decorators.py`
- `role_required(*group_names, login_url=None)` — require Django group membership; 401/403 JSON for API, redirect for browsers (superuser bypass).
- `rate_limit(*, key_prefix, max_requests, window_seconds, identifier)` — cache-backed limiter → HTTP 429 JSON on quota exceed.

### 3.8 `core/context_processors.py`
- `storefront(request) -> dict` — injects category tree, cart/wishlist counts, currencies, countries, language, and `shell_only` into every template.

### 3.9 `core/seo.py`
- `resolve_meta_title` / `resolve_meta_description` / `resolve_og_image_url` — resolve SEO fields with fallbacks.
- `build_hreflang_urls(*, request)` — EN/AR + x-default alternates.
- `build_plp_canonical_url(*, request, category_slug=None)` — canonical PLP URL.
- `build_product_json_ld(...)` — schema.org Product JSON-LD (Offer + AggregateRating).
- `seo_context(*, request, obj=None, title, description, canonical_url=None)` — assemble standard SEO context.

### 3.10 `core/sitemaps.py`
`ProductSitemap`, `CategorySitemap`, `OccasionSitemap`, `BlogPostSitemap`, `PageSitemap` — one `Sitemap` per public content type.

### 3.11 `core/tasks.py`
- `refresh_sitemap_cache()` — warms `/sitemap.xml` nightly (`@shared_task`).
- (`celery_health_check` referenced by beat — trivial liveness task.)

### 3.12 `core/forms.py` / `core/signals.py`
- `CurrencyAdminForm` — admin form; `clean_code()` uppercases code.
- `signals.py` — no handlers (core emits no cross-app signals).

### 3.13 `core/templatetags/storefront_tags.py`
- `in_display_currency(amount, currency)` — filter converting base amount to active display currency.
- `money_label(amount, currency)` — simple tag formatting amount + currency code.

### 3.14 `core/management/commands/audit_page_queries.py`
- `PageAuditResult` (dataclass) — query-audit metrics for one page.
- `Command` — audits query counts/duplicates for key pages; `--output`, `--slow-ms`; seeds data and hits pages under DEBUG, writes JSON report.

---

## 4. App: `accounts`

Authentication, profiles, addresses, payment methods, wishlist, subscriptions, gift reminders, and corporate registration. Endpoints are largely JSON (content-negotiated via `_wants_json`); register/login/dashboard/corporate-register render HTML.

### 4.1 `accounts/models.py`
| Model / choices | Purpose |
|-----------------|---------|
| `OTPPurpose` | Choices: login / signup / reset. |
| `CorporateApprovalStatus` | Pending / Approved / Rejected. |
| `CustomerProfile` | Customer profile (currency, default address, notification prefs). |
| `Address` | Saved delivery address (city FK, `is_default`). |
| `SavedPaymentMethod` | Tokenized payment method metadata (no raw card data). |
| `CorporateAccount` | B2B account (company, trade license, approval status). |
| `OTPRequest` | Hashed OTP with purpose, attempts, used flag. |
| `SubscriptionStatus` | Active / Paused / Cancelled. |
| `Subscription` | Recurring product delivery (frequency, next run). |
| `Wishlist` / `WishlistItem` | Persistent wishlist + items. |
| `GiftOccasionType` | Occasion enum for reminders. |
| `GiftReminder` | Gifting-calendar reminder (occasion, date, notify-days-before). |

### 4.2 `accounts/views.py`
Private helpers: `_json_body`, `_error_response`, `_success_response`, `_serialize_address`, `_serialize_payment_method`, `_serialize_order`, `_wants_json`.

| View | Response | Decorators |
|------|----------|-----------|
| `email_register_view` | GET→`accounts/register.html`; POST→redirect/JSON | `@require_http_methods(["GET","POST"])` |
| `email_login_view` | GET→`accounts/login.html`; POST→redirect/JSON (429 on limit) | `@require_http_methods(["GET","POST"])` |
| `email_logout_view` | redirect `cms:homepage` or JSON | `@require_http_methods(["GET","POST"])` |
| `otp_request_view` | JSON (429 on limit) | `@require_POST` |
| `otp_verify_view` | JSON | `@require_POST` |
| `google_login_view` | JSON (401 on fail) | `@require_POST` |
| `guest_checkout_view` | JSON (signed guest token) | `@require_POST` |
| `forgot_password_view` | JSON (429 on limit) | `@require_POST` |
| `reset_password_view` | JSON | `@require_POST` |
| `dashboard_view` | `accounts/dashboard.html` or JSON | `@login_required`, `@require_GET` |
| `address_list_create_view` | JSON | `@login_required`, GET/POST |
| `address_detail_view` | JSON | `@login_required`, PUT/PATCH/DELETE |
| `payment_methods_list_view` | JSON | `@login_required`, `@require_GET` |
| `payment_method_delete_view` | JSON | `@login_required`, `@require_POST` |
| `corporate_register_view` | GET→`accounts/corporate_register.html`; POST→JSON | GET/POST |
| `corporate_pending_approvals_view` | JSON | `@login_required`, `@role_required("SuperAdmin","StoreAdmin")`, `@require_GET` |
| `wishlist_shared_view` | JSON (signed token, read-only) | `@require_GET` |
| `wishlist_add_view` | JSON | `@login_required`, `@require_POST` |
| `wishlist_shared_mutate_view` | JSON (403/401 — mutation via share token rejected) | `@require_POST` |

### 4.3 `accounts/urls.py` (`app_name="accounts"`)
| Route | Name |
|-------|------|
| `register/` | `register` |
| `login/email/` | `login-email` |
| `logout/` | `logout` |
| `login/otp/request/` | `otp-request` |
| `login/otp/verify/` | `otp-verify` |
| `login/google/` | `login-google` |
| `guest-checkout/` | `guest-checkout` |
| `password/forgot/` | `forgot-password` |
| `password/reset/` | `reset-password` |
| `dashboard/` | `dashboard` |
| `addresses/` | `address-list-create` |
| `addresses/<int:address_id>/` | `address-detail` |
| `payment-methods/` | `payment-methods-list` |
| `payment-methods/<int:payment_method_id>/delete/` | `payment-method-delete` |
| `corporate/register/` | `corporate-register` |
| `corporate/pending/` | `corporate-pending` |
| `wishlist/shared/` | `wishlist-shared` |
| `wishlist/add/` | `wishlist-add` |
| `wishlist/shared/mutate/` | `wishlist-shared-mutate` |

### 4.4 `accounts/selectors.py`
- `CustomerDashboardContext` (dataclass) — aggregated dashboard data.
- `get_customer_profile_for_user(*, user)` — profile w/ select_related (1 query).
- `get_customer_dashboard_context(*, user)` — full dashboard context (4 queries).
- `get_address_by_id(*, address_id, customer_profile)` — one owned address (1 query).
- `get_saved_addresses(*, customer_profile, page=1, page_size=50)` — paginated addresses.
- `get_saved_payment_methods(*, customer_profile, page=1, page_size=50)` — paginated methods.
- `get_pending_corporate_approvals(*, page=1, page_size=20)` — paginated pending corporates.
- `WishlistView` (dataclass) — wishlist + items + readonly flag.
- `get_wishlist(*, customer_profile=None, share_token=None)` — wishlist by owner or share token.
- `get_upcoming_gift_reminders(*, customer_profile)` — reminders ordered by date.

### 4.5 `accounts/services.py`
Internal helpers: phone normalization, OTP generation, and OTP/login rate-limit key/check/increment functions; `GUEST_CHECKOUT_SALT`.
- `request_otp(*, phone, purpose)` — create hashed OTP, dispatch SMS via Celery (rate-limited, atomic).
- `verify_otp(*, phone, otp_code, purpose)` — validate OTP, mark used, track attempts.
- `register_customer_email(*, email, password, name)` — create user + profile (atomic).
- `ensure_customer_profile_for_user(*, user)` — get/create profile for any user.
- `authenticate_email(*, email, password)` — email/password auth.
- `authenticate_google(*, google_id_token)` — verify Google token, get/create profile (atomic).
- `create_guest_checkout_token(*, cart_id)` / `verify_guest_checkout_token(*, token)` — stateless guest token sign/verify.
- `set_default_address` / `update_address` / `create_address` / `delete_address` — address CRUD w/ default promotion (atomic, `select_for_update`).
- `delete_saved_payment_method(*, customer_profile, payment_method_id)` — delete token (atomic).
- `register_corporate_account(...)` — create PENDING corporate account + notify admins (atomic).
- `login_or_create_customer_by_phone(*, phone)` — find/create verified-phone profile (atomic).
- `reset_password_with_otp(*, phone, otp_code, new_password)` — verify OTP + reset (atomic).
- `notify_admins_corporate_pending(*, corporate_account_id)` — in-app notifications to SuperAdmins.

### 4.6 `accounts/subscription_services.py`
- `create_subscription(...)` — subscription + recurring schedule (atomic).
- `pause_subscription` / `resume_subscription` / `cancel_subscription` — lifecycle transitions (atomic).
- `execute_subscription_recurrence(*, schedule)` — recurrence handler: build cart, place order (atomic).
- `get_or_create_wishlist(*, request)` — persistent wishlist for user/guest (atomic).
- `add_to_wishlist` / `remove_from_wishlist` — item mutation (atomic).
- `generate_wishlist_share_token(*, wishlist)` — signed read-only share token.
- `schedule_gift_reminder(...)` — create gift-calendar reminder (atomic).
- `send_due_gift_reminders()` — emit `gift_reminder_due` for due reminders.

### 4.7 `accounts/recurrence.py`
- `register()` — registers `Subscription` recurrence handler with the recurring registry (called on import).

### 4.8 `accounts/tasks.py`
- `send_otp_sms(*, phone, otp_code)` — dispatch OTP SMS.
- `notify_corporate_registration(*, corporate_account_id)` — notify admins.
- `send_due_gift_reminders_task()` — daily beat task for gift reminders.

### 4.9 `accounts/signals.py`
- `gift_reminder_due = Signal()` — emitted when a gift reminder is due (notifications listen).

### 4.10 `accounts/forms.py`
`EmailLoginForm`, `OTPRequestForm`, `OTPVerifyForm`, `EmailRegistrationForm`, `GoogleLoginForm`, `GuestCheckoutForm`, `ForgotPasswordForm`, `ResetPasswordForm`, `AddressForm` (limits city queryset to active), `CorporateRegistrationForm`.

---

## 5. App: `catalog`

Product catalog. All views are GET-only.

### 5.1 `catalog/models.py`
| Model / choices | Purpose |
|-----------------|---------|
| `Category` | Product category (self-referential tree, SEO). |
| `Occasion` | Occasion tag (birthday, anniversary…). |
| `Brand` | Product brand. |
| `Recipient` | Recipient tag (for her, for him…). |
| `Product` | Core product (price, stock, flags incl. gift-customization support, SEO). |
| `VariantType` / `ProductVariant` | Variant type enum + variant rows (size/color, price delta, stock). |
| `ProductImage` / `ProductVideo` | Product media (primary image flag). |
| `RelationType` / `ProductRelation` | Related/cross-sell/upsell links. |
| `ModerationStatus` / `Review` / `ReviewPhoto` | Customer reviews (pending→approved/rejected) + photos. |

### 5.2 `catalog/views.py`
Helper: `_parse_plp_filters(request)` — parse shareable PLP query params into a filter dict.

| View | Response | Decorators |
|------|----------|-----------|
| `plp_view(request, category_slug=None)` | `catalog/plp.html` (HTMX → `partials/product_grid.html`); 404 bad category | `@require_GET` |
| `pdp_view(request, slug)` | `catalog/pdp.html`; 404 if missing | `@require_GET` |
| `search_suggestions_view(request)` | `catalog/partials/search_suggestions.html` | `@require_GET` |
| `variant_price_view(request, product_id)` | `JsonResponse` | `@require_GET` |
| `delivery_estimate_view(request, product_id)` | `JsonResponse`; 404 if missing | `@require_GET` |

### 5.3 `catalog/urls.py` (`app_name="catalog"`)
| Route | Name |
|-------|------|
| `search/suggest/` | `search-suggest` |
| `products/<slug:slug>/` | `pdp` |
| `products/<int:product_id>/variant-price/` | `variant-price` |
| `products/<int:product_id>/delivery-estimate/` | `delivery-estimate` |
| `category/<slug:category_slug>/` | `plp-category` |
| `` | `plp` |

### 5.4 `catalog/selectors.py`
- `get_product_display_price(*, product)` — flash-sale-adjusted PLP card price.
- `_primary_image_prefetch()` — prefetch only primary image.
- `get_homepage_product_rails()` — merchandising rails (trending/bestseller/new/same-day; 6 queries).
- `get_plp_products(*, filters=None, sort="newest", page=1, page_size=24)` — paginated PLP w/ rating annotation + flash pricing (4 queries).
- `get_product_detail(*, slug)` — fully hydrated PDP product (10 queries).
- `record_product_view` / `get_recently_viewed` — Redis recently-viewed list.
- `get_category_tree()` — mega-menu tree (cached, 2 queries) / `invalidate_category_tree_cache()`.
- `get_search_suggestions(*, query, limit=8)` — live-search name matches.
- `get_occasions_for_display` / `get_recipients_for_display` / `get_root_categories` / `get_featured_brands` — homepage/filter data.
- `get_products_for_section_config(*, config)` — products for CMS collection sections.
- `get_recent_approved_reviews(*, limit=6)` — homepage reviews.
- `get_variant_price(*, product_id, variant_id=None)` — computed price w/ flash sale.
- `get_category_by_slug(*, slug)` — active category (1 query).
- `get_plp_filter_options()` — sidebar filter options (4 queries).
- `get_product_for_cart_add` / `get_products_by_ids` — cart-support reads.

### 5.5 `catalog/services.py`
- `create_product_with_variants(...)` — create product + variants + images (requires a primary image; atomic).
- `adjust_stock(*, target, delta, reason)` — atomic stock adjust (`select_for_update`; raises on negative).
- `submit_review(...)` — create PENDING review + notify admins (atomic).
- `moderate_review(*, review_id, decision, moderator)` — approve/reject (atomic).

### 5.6 `catalog/tasks.py` / `signals.py` / `templatetags`
- `notify_review_moderation(*, review_id)` — notify SuperAdmins of pending review.
- `category_changed(...)` — on Category save/delete, invalidate the category-tree cache.
- `catalog_tags.query_with(context, **kwargs)` — build a query string overriding params (for filter/sort links).
- `catalog/forms.py` — empty placeholder.

---

## 6. App: `gifting`

The plug-and-play gift customization engine, attached to any product via Django `ContentType`.

### 6.1 `gifting/models.py`
| Model / choices | Purpose |
|-----------------|---------|
| `BaseCustomizationOption` | Abstract base for option types (active flag, price). |
| `GiftCustomizationConfig` | Per-product config (ContentType FK; permission flags `allows_*`). |
| `GreetingCardDesign` | Greeting card options (optional occasion). |
| `GiftWrapName` / `GiftWrapOption` | Gift wrap enum + options. |
| `RibbonName` / `RibbonOption` | Ribbon enum + options. |
| `GiftPhotoUploadOption` | Photo-upload options. |
| `GiftAddonEligibility` | Which addon products are eligible for a product. |
| `GiftLineItemRef` | Opaque anchor row tying a builder session to a snapshot. |
| `GiftCustomizationSnapshot` | Immutable snapshot of selections + pricing. |
| `GiftSnapshotAddon` | Snapshot's chosen addon rows. |

### 6.2 `gifting/views.py`
Helpers: `_get_line_item_ref(*, request, slug)` (resolve/create ref, cache in session), `_builder_context(...)` (assemble full builder context; 404 if no config).

| View | Response | Decorators |
|------|----------|-----------|
| `gift_builder_view(request, slug)` | `gifting/builder.html`; 404 if no product | `@require_GET` |
| `gift_builder_preview_view(request, line_item_id)` | validate `GiftBuilderForm`, persist snapshot, render `gifting/partials/order_preview.html` | GET/POST |
| `gift_message_preview_view(request)` | `gifting/partials/message_preview.html` (live counter) | POST |

### 6.3 `gifting/urls.py` (`app_name="gifting"`)
| Route | Name |
|-------|------|
| `products/<slug:slug>/builder/` | `builder` |
| `builder/<int:line_item_id>/preview/` | `builder-preview` |
| `builder/message-preview/` | `message-preview` |

### 6.4 `gifting/selectors.py`
- `get_gift_customization_config(*, product_instance, request=None)` — config by content_type+object_id (per-request cached).
- `get_available_greeting_cards(*, occasion_id=None)` — active cards.
- `get_active_gift_wrap_options` / `get_active_ribbon_options` / `get_active_photo_upload_options` — active options.
- `get_eligible_addons(*, product_instance)` — eligible in-stock addon products.
- `get_gift_customization_snapshot(*, line_item_reference)` — **single shared read-path** used by cart, checkout, and order confirmation.
- `get_line_item_ref_by_id(*, line_item_id)` — ref by pk.

### 6.5 `gifting/services.py`
- `create_line_item_reference()` — create an opaque builder anchor.
- `build_gift_customization_snapshot(*, product_instance, selections, line_item_reference)` — **atomic**; validate against config, resolve prices, `update_or_create` an immutable snapshot + replace addon rows.
- `_resolve_selections(...)` — enforce business rules (message length/allowed, option eligibility + active flags, anonymous/gift-receipt/midnight permissions), build pricing JSON.
- `ensure_gift_customization_config(*, product_instance, **flags)` — `update_or_create` a config for any product.

**State machine:** none (snapshot idempotent via `update_or_create`). **Errors:** `GiftCustomizationValidationError` (field-level, `as_dict()`).

### 6.6 `gifting/forms.py` / `exceptions.py` / `signals.py`
- `GiftBuilderForm` — parses builder POST; `to_selections()` returns a plain dict (splits `addon_product_ids` CSV).
- `GiftCustomizationValidationError` — field-error exception.
- `signals.py` — empty placeholder.

---

## 7. App: `cart`

### 7.1 `cart/models.py`
- `Cart` — profile-linked (auth) or session-key (guest) cart with coupon code/discount + delivery charge.
- `CartItem` — line item (product, variant, quantity, snapshot unit price, optional gift snapshot link).

### 7.2 `cart/views.py`
Helper: `_cart_drawer_response(request, *, hx_triggers=None)` — render drawer, optional `HX-Trigger` header.

| View | Response | Decorators |
|------|----------|-----------|
| `cart_drawer_view` | `cart/partials/drawer.html` | `@require_GET` |
| `cart_count_view` | `cart/partials/count_badge.html` | `@require_GET` |
| `cart_add_view` | drawer partial + `cartItemAdded` trigger; 404 if no product | `@require_POST` |
| `cart_remove_view` | drawer partial + `cartUpdated` trigger | `@require_POST` |
| `wishlist_toggle_view` | redirect to referer (session wishlist) | `@require_POST` |

### 7.3 `cart/urls.py` (`app_name="cart"`)
| Route | Name |
|-------|------|
| `drawer/` | `drawer` |
| `count/` | `count` |
| `add/` | `add` |
| `remove/` | `remove` |
| `wishlist/toggle/` | `wishlist-toggle` |

### 7.4 `cart/selectors.py`
- `get_cart_for_request(*, request)` — resolve cart (auth profile else session key) with request-scoped cache (`_floward_resolved_cart`).
- `CartSummaryLine` / `CartSummary` (dataclasses) — hydrated line + computed totals.
- `get_cart_by_id` / `get_cart_item_count` / `get_cart_count` / `get_wishlist_count` — counts & lookups.
- `get_cart_summary(*, cart)` — full totals with per-line gift-delta hydration; subtotal/coupon/delivery/grand_total (clamped ≥ 0).

### 7.5 `cart/services.py`
- `get_or_create_cart(*, request)` — resolve/create cart (atomic; requires default currency).
- `add_to_cart(*, cart, product, variant=None, quantity=1, gift_selections=None)` — add/increment line; optionally build + link gift snapshot (atomic).
- `remove_cart_item(*, cart, cart_item_id)` — delete a line (atomic).
- `apply_coupon(*, cart, code)` — validate via `marketing.validate_coupon_for_cart`, persist discount (atomic).
- `recalculate_delivery_charge(*, cart, destination_city)` — recompute via `delivery.get_delivery_charge` (atomic).
- `toggle_wishlist(*, request, product_id)` — session-only wishlist toggle.
- `cart/forms.py` / `signals.py` — empty placeholders. `exceptions.py`: `CartError`, `CartNotFoundError`.

---

## 8. App: `checkout`

### 8.1 `checkout/models.py`
- `CheckoutSessionStatus` — DRAFT / COMPLETED.
- `CheckoutSession` — checkout state (cart, address, delivery date/slot, invoice details, resulting order).

### 8.2 `checkout/views.py`
| View | Response | Decorators |
|------|----------|-----------|
| `checkout_view` | `checkout/checkout.html`; redirect to PLP if cart empty | `@login_required`, `@require_GET` |
| `checkout_place_order_view` | validate payment form (`partials/errors.html` 400 on invalid) → `place_order` → `process_payment` → `checkout/confirmation.html`; 404 if no cart | `@login_required`, POST |

### 8.3 `checkout/urls.py` (`app_name="checkout"`)
| Route | Name |
|-------|------|
| `` | `checkout` |
| `place-order/` | `place-order` |

### 8.4 `checkout/selectors.py` / `services.py`
- `get_checkout_session_by_id` — fully select_related session.
- `get_draft_checkout_for_cart(*, cart_id)` — active DRAFT for a cart.
- `create_checkout_session(...)` — return existing DRAFT or create (atomic).
- `update_checkout_session(...)` — persist step data (atomic).
- `place_order(*, checkout_session_id, idempotency_key, customer_profile)` — **atomic, idempotent**: `select_for_update` on session, reserve delivery slot, decrement stock via `catalog.adjust_stock`, snapshot address, create `Order`+`OrderItem`s, record coupon redemption, mark session COMPLETED, clear cart.

**State machine:** DRAFT → COMPLETED. **Idempotency:** dual guard (pre-check on key + `IntegrityError` fallback returning existing order). **Errors:** `CheckoutSessionError`, `IdempotentOrderExistsError(order)`; slot/stock guarded by `SlotFullyBookedError` / `InsufficientStockError`.

### 8.5 `checkout/forms.py`
`CheckoutAddressForm` (address_id), `CheckoutDeliveryForm` (date, slot), `CheckoutPaymentForm` (gateway_key, idempotency_key, optional voucher_code). `signals.py` — empty placeholder.

---

## 9. App: `orders`

### 9.1 `orders/models.py`
| Model / choices | Purpose |
|-----------------|---------|
| `OrderStatus` | Received / Preparing / Packaging / Ready / Out for Delivery / Delivered / Cancelled / Refunded. |
| `Order` | Order header (number, customer, currency, address snapshot, totals, slot booking). |
| `OrderItem` | Order line (product/variant snapshot, quantity, price, gift snapshot). |
| `OrderStatusHistory` | Audit trail of status transitions. |
| `ProofOfDelivery` | Delivery confirmation artifact. |

### 9.2 `orders/views.py` / `urls.py`
- `order_tracking_view(request, order_id)` → `orders/tracking.html`; `@login_required`, `@require_GET`; 404 if not owned. Route `<int:order_id>/tracking/` name `tracking`.

### 9.3 `orders/selectors.py`
- `OrderTrackingView` (frozen dataclass) — order + status history.
- `get_customer_orders(*, customer_profile, page=1, page_size=20)` — paginated orders.
- `get_recent_orders_for_customer(*, customer_profile_id, limit=5)` — recent orders.
- `get_order_tracking_view(*, order_id, customer_profile=None)` — hydrated order + prefetched history/items (owner-scoped when profile passed).

### 9.4 `orders/services.py`
- `generate_order_number()` — unique `FLW-...` number.
- `transition_order_status(*, order, new_status, actor=None, note="")` — **atomic**; validate against `ALLOWED_STATUS_TRANSITIONS`, update, write `OrderStatusHistory`, **emit `order_status_changed`**.
- `ALLOWED_STATUS_TRANSITIONS` — the state-machine graph (Cancelled reachable from pre-delivery states; Cancelled/Refunded terminal).

### 9.5 `orders/signals.py` / `exceptions.py`
- `order_status_changed = Signal()` — cross-app signal (notifications listen).
- `InvalidOrderStatusTransitionError` — disallowed status change.

---

## 10. App: `payments`

Payment processing via an adapter/registry pattern. JSON only — no templates.

### 10.1 `payments/models.py`
- `PaymentStatus` — PENDING / SUCCESS / FAILED.
- `PaymentTransaction` — payment record (order, gateway, amount, external intent id, status).
- `RazorpayWebhookEvent` — durable dedup + audit record for real Razorpay webhook deliveries, keyed on `event_id` (unique). `status` records the terminal outcome of the first processing attempt (PROCESSED / UNKNOWN_TRANSACTION / AMOUNT_MISMATCH / CURRENCY_MISMATCH / IGNORED_EVENT_TYPE / ERROR) — never overwritten by a redelivery.

### 10.2 `payments/views.py` / `urls.py`
- `payment_webhook_view(request, gateway_key)` → `JsonResponse` (`@csrf_exempt`, `@require_POST`; reads `X-Payment-Signature`; 404 `{"status":"ignored"}` when unmatched). Route `webhooks/<str:gateway_key>/` name `webhook`. Generic mock contract — not used by Razorpay in production.
- `razorpay_webhook_view(request)` → `JsonResponse` (`@csrf_exempt`, `@require_POST`). The real, production Razorpay server-to-server confirmation path, independent of the browser `checkout.js` redirect callback (`checkout/views.py::razorpay_callback_view`). Verifies `X-Razorpay-Signature` (HMAC-SHA256 over the raw body with `RAZORPAY_WEBHOOK_SECRET`) before parsing anything; 400 on invalid/missing signature, missing `X-Razorpay-Event-Id`, or malformed JSON. Route `webhooks/razorpay/` name `razorpay-webhook` — registered **before** the generic `<str:gateway_key>` route, which would otherwise shadow it. Subscribe only `payment.captured`, `order.paid`, `payment.failed` in the Razorpay dashboard; other event types are acknowledged and ignored (`IGNORED_EVENT_TYPE`).

### 10.3 `payments/services.py`
- `confirm_payment_success` / `confirm_payment_failed` — single convergence points (atomic), called by **both** the browser callback and the Razorpay webhook. Idempotent and concurrency-safe: reload the row under `select_for_update()` and no-op if the transaction already reached a terminal state (SUCCESS is never re-processed or downgraded by a later `payment.failed`).
- `process_payment(*, order, gateway_key, payment_data)` — **atomic**; create PENDING tx, resolve adapter, create intent; async gateways stay PENDING (await webhook), sync gateways (incl. `GiftVoucherAdapter`) capture inline and converge.
- `handle_payment_webhook(*, gateway_key, payload, signature)` — **atomic**; the old generic mock-webhook path (non-Razorpay sandbox adapters only). Verify via adapter, match tx by `external_intent_id`, converge; None if unmatched.
- `verify_razorpay_webhook_signature(*, payload, signature)` — HMAC-SHA256 raw-body check against `RAZORPAY_WEBHOOK_SECRET`.
- `handle_razorpay_webhook_event(*, event_id, event_type, event_data)` — **atomic**; the real Razorpay webhook's orchestration. Dedupes on `event_id` (`RazorpayWebhookEvent.objects.get_or_create`), resolves the `PaymentTransaction` by `external_intent_id` (Razorpay order id) + `gateway_key__startswith="razorpay"`, validates amount (paise-exact) and currency before calling `confirm_payment_success`/`confirm_payment_failed`. Unknown transactions and amount/currency mismatches are recorded on `RazorpayWebhookEvent` for investigation, never guessed at.

**State machine:** PENDING → SUCCESS/FAILED. `selectors.py`, `forms.py`, `signals.py` — empty placeholders.

---

## 11. App: `delivery`

No HTTP surface (`views.py`/`urls.py`/`forms.py`/`signals.py` are stubs); logic lives in selectors/services.

### 11.1 `delivery/models.py`
| Model / choices | Purpose |
|-----------------|---------|
| `Country` | Delivery country (active flag). |
| `City` | Delivery city (country FK, cutoff hour, `delivery_charge_base`). |
| `DeliveryZone` | Geographic zone within a city. |
| `DeliverySlotType` | Slot type enum (standard / midnight …). |
| `DeliverySlot` | Time window with capacity. |
| `DeliverySlotBooking` | A reserved slot on a date. |

### 11.2 `delivery/selectors.py`
- `get_active_countries()` / `get_active_cities()` / `get_city_by_slug(*, slug)` — region reads.
- `_same_day_allowed(*, city, delivery_date)` — same-day still offerable given cutoff.
- `get_available_slots(*, city, delivery_date, allow_midnight=False)` — slots with remaining capacity (cutoff + midnight rules).
- `get_available_delivery_slots(...)` — backward-compatible wrapper.
- `get_earliest_delivery_estimate(*, product, destination_city)` — earliest estimate (today/tomorrow/+2).
- `get_delivery_charge(*, item_count, destination_city)` — charge from city base (0 for empty).
- `get_slot_booking_count(*, slot_id, delivery_date)` — current bookings.

### 11.3 `delivery/services.py`
- `reserve_delivery_slot(*, slot, delivery_date)` — **atomic**; reserve one booking via `select_for_update` (no oversell), raises `SlotFullyBookedError`.

---

## 12. App: `recurring`

Generic recurrence engine (no HTTP surface). Other apps register handlers keyed by model.

### 12.1 `recurring/models.py`
- `RecurrenceFrequency` / `RecurrenceStatus` — enums.
- `RecurringSchedule` — schedule (ContentType target, frequency, next run, status).

### 12.2 `recurring/services.py`
- `_advance_next_run_date(*, schedule)` — advance by 7 (weekly) or 30 days.
- `execute_recurrence(*, schedule)` — **atomic**; run the content-type strategy handler, then advance.
- `process_due_schedules()` — process all ACTIVE schedules due today (entry point for the daily beat task).

### 12.3 `recurring/registry.py` / `tasks.py`
- `register_recurrence_handler(*, model_class, handler)` / `get_recurrence_handler(*, content_type)` — registry API (`RECURRENCE_HANDLERS`).
- `process_due_schedules_task()` — daily beat task (`recurring.tasks.process_due_schedules`).

---

## 13. App: `corporate`

B2B accounts, quotes, invoices, and recurring bulk orders.

### 13.1 `corporate/models.py`
- `CorporateQuoteStatus` — Requested / Approved / … .
- `CorporateOrder` / `CorporateOrderItem` — quote/order header + lines.
- `CorporateInvoice` — generated invoice record.

### 13.2 `corporate/views.py` / `urls.py`
- `corporate_dashboard_view(request)` → `corporate/dashboard.html` (or `JsonResponse` when `Accept: application/json`); `@login_required`, `@require_GET`. Route `dashboard/` name `dashboard`.

### 13.3 `corporate/selectors.py` / `services.py` / `recurrence.py`
- `CorporateDashboardContext` (frozen dataclass) + `get_corporate_dashboard(...)` — paginated quotes/recurring/invoices (6 queries).
- `request_corporate_quote(...)` — create REQUESTED order (+ optional schedule), notify admins (atomic).
- `approve_and_convert_to_order(*, corporate_order)` — convert approved quote to retail Order via `checkout.place_order` (atomic, idempotent).
- `execute_corporate_order_recurrence(*, schedule)` — recurrence handler: rebuild cart, place order (atomic).
- `generate_corporate_invoice(*, corporate_order, pdf_url)` — record invoice (atomic).
- `recurrence.register()` — register the `CorporateOrder` handler at import.

---

## 14. App: `marketing`

Promotions engine (no HTTP surface).

### 14.1 `marketing/models.py`
| Model / choices | Purpose |
|-----------------|---------|
| `CouponDiscountType` / `Coupon` / `CouponRedemption` | Coupons (%/fixed, limits, scope) + redemption ledger. |
| `GiftCard` | Internal gift card / voucher balance. |
| `FlashSale` | Time-boxed product discounts. |
| `AbandonedCartRecovery` | Abandoned-cart tracking record. |
| `Referral` | Referral record. |
| `NewsletterSubscriber` | Newsletter list. |

### 14.2 `marketing/selectors.py`
- `get_active_flash_sale_price(*, product_id, base_price)` — flash-adjusted price (PDP).
- `get_flash_sale_discounts_for_products(*, product_prices)` — highest active discount per product (PLP, single query).
- `get_active_flash_sales()` — active sales w/ prefetched products.

### 14.3 `marketing/services.py` / `services_abandoned.py` / `tasks.py`
- `validate_coupon_for_cart(...)` — validate date window/limits/min order/category scope; return discount.
- `record_coupon_redemption(...)` — record redemption after placement (atomic).
- `redeem_gift_voucher(*, code, amount)` — deduct from gift card via `select_for_update` (atomic).
- `subscribe_newsletter` / `unsubscribe_newsletter` — newsletter list mutation (atomic).
- `scan_abandoned_carts()` — find stale carts, dispatch recovery notifications (`ABANDONED_CART_HOURS`).
- `scan_abandoned_carts_task()` — hourly beat task.

---

## 15. App: `cms`

CMS-driven homepage + content models. Cache-first (0 DB queries on cache hit).

### 15.1 `cms/models.py`
| Model / choices | Purpose |
|-----------------|---------|
| `HomepageSectionType` | Enum of all section types. |
| `PublishableModel` | Abstract publish state base. |
| `HomepageSection` | Configurable homepage section (type, order, active, JSON config). |
| `HeroSlide` | Hero slider media. |
| `BlogPost` | Blog post (SEO, publishable). |
| `Page` | Static CMS page (SEO). |
| `FAQItem` | FAQ entry. |
| `PolicyDocument` | Policy/legal document (SEO). |

### 15.2 `cms/views.py` / `urls.py`
- `homepage_view(request)` → `cms/homepage.html`; `@require_GET`; each section → `cms/sections/<section_type>.html`. Route `` name `homepage`.

### 15.3 `cms/selectors.py` / `services.py` / `section_context.py`
- `get_active_homepage_sections()` — ordered active sections from Redis snapshot (`cms:homepage_sections:active:v1`, TTL 300).
- `get_hero_slides()` — active hero media (skips slides w/o file).
- `build_homepage_sections_snapshot()` / `refresh_homepage_cache()` — build + write the snapshot.
- `get_section_render_context(*, section, product_rails=None)` — delegates to `build_section_context`.
- `section_context.build_section_context(...)` — dispatch by `section_type` to a per-type builder (`_hero_slider`, `_shop_by_occasion`, `_trending`, `_best_sellers`, `_featured_brands`, `_banner`, `_reviews`, `_instagram`, `_newsletter`, …), each pulling from `catalog.selectors`.

### 15.4 `cms/tasks.py` / `signals.py` / `forms.py` / `homepage_forms.py`
- `refresh_homepage_cache_task()` — rebuild Redis snapshot.
- Signals: refresh homepage cache on save/delete of `HomepageSection`, `BlogPost`, `Page`, `FAQItem`, `PolicyDocument`.
- `HomepageSectionAdminForm` — structured per-type config editing (not raw JSON).
- `homepage_forms.py` — per-type config form registry (`SECTION_CONFIG_FORMS`) + `get_section_config_form`, `config_from_form`, `_flatten_config_for_form`.

---

## 16. App: `notifications`

No views/urls — pure service/task/signal layer consumed cross-app.

### 16.1 `notifications/models.py`
- `Notification` — in-app notification (user, title, body, read flag).

### 16.2 `notifications/selectors.py` / `services.py`
- `get_unread_notification_count(*, user)` — unread count.
- `send_sms` / `send_email` / `send_whatsapp` — provider-agnostic dispatch stubs (log payload).
- `create_notification(*, user, title, body="")` — persist in-app notification.

### 16.3 `notifications/tasks.py` / `signals.py`
- `dispatch_sms(...)` — async SMS.
- `dispatch_order_status_notification(*, order_id, old_status, new_status)` — create notification + email/SMS/WhatsApp per prefs.
- `dispatch_gift_reminder_notification(*, reminder_id)` — gift reminder dispatch.
- Signals: `order_status_changed` → enqueue order-status notification; `gift_reminder_due` → enqueue reminder (keeps orders/accounts→notifications boundary via signals).

---

## 17. App: `reports`

Pre-aggregated analytics (nightly). Storefront exposes one role-gated JSON endpoint; the admin dashboard consumes the selectors directly.

### 17.1 `reports/models.py`
`DailySalesReport`, `DailyProductPerformance`, `DailyCustomerReport`, `InventorySnapshot` — pre-aggregated daily rollup tables.

### 17.2 `reports/views.py` / `urls.py`
- `admin_dashboard_view(request)` → `JsonResponse` (`@role_required("SuperAdmin","StoreAdmin")`, `@require_GET`); summary + last 7 days sales. Route `admin/dashboard/` name `admin-dashboard`.

### 17.3 `reports/selectors.py` / `services.py` / `tasks.py`
- `get_daily_sales_reports(...)` / `get_daily_product_performance(...)` / `get_daily_customer_reports(...)` / `get_inventory_snapshots(...)` — paginated report reads.
- `get_admin_dashboard_summary()` — cached 5 min (`reports:admin_dashboard:today`); historical from rollups + today's live exception.
- `aggregate_daily_reports(*, report_date=None)` — populate all rollup tables for a day (defaults to yesterday).
- `aggregate_daily_reports_task()` — nightly beat task.

---

## 18. Templates

Project templates live in `templates/`; app-local templates live under `<app>/templates/`.

### 18.1 Shared shell
| Path | Purpose |
|------|---------|
| `templates/base.html` | Root storefront layout (Bootstrap 5.3 + HTMX 2.0.4, RTL, header/footer/mobile-nav, `shell_only` toggle). |
| `templates/includes/header.html` | Global header (nav, mega menu, language/currency/country, cart). |
| `templates/includes/footer.html` | Global footer. |
| `templates/includes/mobile_nav.html` | Mobile navigation. |
| `templates/includes/seo_head.html` | SEO/meta/OG/JSON-LD head partial. |

### 18.2 CMS / homepage
- `templates/cms/homepage.html` — renders section partials in order.
- `templates/cms/sections/*.html` — one partial per section type: `hero_slider, shop_by_occasion, shop_by_recipient, shop_by_category, premium_collection, seasonal_collection, luxury_collection, same_day_delivery, trending, best_sellers, featured_brands, corporate_gifts_banner, subscription_banner, marketing_features, reviews, instagram_gallery, newsletter`, plus shared `_section_title.html`.

### 18.3 Catalog
- `templates/catalog/plp.html`, `pdp.html`.
- `templates/catalog/partials/`: `product_card`, `product_grid` (HTMX-swappable), `product_rail`, `plp_filters`, `search_suggestions`, `pdp_gallery`, `pdp_delivery`.

### 18.4 Cart / checkout / gifting / orders / accounts / corporate
| Path | Purpose |
|------|---------|
| `templates/cart/partials/drawer.html` | Cart drawer (lines, gift badges, totals). |
| `templates/cart/partials/count_badge.html` | Header cart count. |
| `templates/checkout/checkout.html` | Multi-step checkout. |
| `templates/checkout/confirmation.html` | Post-order confirmation. |
| `templates/checkout/partials/errors.html` | Form-error list (place-order 400). |
| `templates/gifting/builder.html` | Full-page gift builder. |
| `templates/gifting/partials/message_preview.html` | Live message preview + counter. |
| `templates/gifting/partials/order_preview.html` | Order Preview (shared across cart/checkout/order). |
| `templates/orders/tracking.html` | Order tracking + status timeline. |
| `templates/accounts/register.html` / `login.html` / `dashboard.html` | Customer auth + account area. |
| `accounts/templates/accounts/corporate_register.html` | B2B registration. |
| `templates/corporate/dashboard.html` | Corporate portal dashboard. |

---

## 19. Static Assets — `static/`

| Path | Purpose |
|------|---------|
| `static/css/main.css` | Main storefront stylesheet. |
| `static/css/rtl.css` | RTL (Arabic) overrides. |
| `static/js/main.js` | Global JS (HTMX helpers incl. CSRF header, toasts). |
| `static/js/pdp.js` | Product detail page JS. |
| `static/js/gift_builder.js` | Gift builder interactions. |
| `static/img/product-placeholder.svg` | Fallback product image. |
| `static/dashboard/...` | Admin dashboard assets (see admin dashboard doc). |

Serving strategy is **no-build**: CDN for Bootstrap/HTMX/icons, committed CSS/JS for the rest; production uses `collectstatic` + optional S3/CDN.

---

## 20. Internationalization — `locale/`

- `locale/en/LC_MESSAGES/django.po` — English catalog.
- `locale/ar/LC_MESSAGES/django.po` — Arabic catalog.
- Content translation via `django-modeltranslation` (translatable model fields, en default, AR→EN fallback); UI strings via Django's gettext with `LocaleMiddleware` + `i18n_patterns`.

---

## 21. Supporting Directories

| Path | Purpose |
|------|---------|
| `scripts/scaffold_apps.py` | One-off generator that scaffolds the layered file set for all business apps (origin of the stub docstrings). |
| `deploy/gunicorn/gunicorn.conf.py` | Gunicorn config (unix socket, `(2*CPU)+1` workers, timeout 120s, request recycling). |
| `deploy/nginx/samruddhi.conf` | Nginx site (gunicorn upstream socket, gzip, static/media aliases, proxy headers). |
| `deploy/systemd/samruddhi.service` | systemd unit running Gunicorn (`www-data`, EnvironmentFile, prod settings, auto-restart). |
| `deploy/docs/BACKUP_RESTORE.md` | DB/media backup & restore runbook. |
| `loadtests/locustfile.py` | Locust load test (`StorefrontUser`: weighted homepage/PLP/PDP/checkout tasks). |
| `manage.py` | Django CLI (default settings = dev). |
| `requirements.txt` | Runtime + dev/CI dependencies. |
| `requirements-dev.txt` | `-r requirements.txt`. |
| `pyproject.toml` | Black (line-length 100) + isort (black profile) config. |
| `setup.cfg` | flake8 config (max-line 100, ignore E203/W503, exclude migrations/scripts). |
| `.env.example` | Sample environment variables. |

---

## 22. Cross-App Interaction Map

```
catalog ──price/stock──▶ cart ──coupon──▶ marketing
   ▲                      │                  ▲
   │                      ├──delivery charge─┴─▶ delivery
gifting ◀── snapshot ─────┤
   (shared read-path)     ▼
                       checkout ──place_order──▶ orders ──signal──▶ notifications
                          │                        │  (order_status_changed)
                          └──process_payment──▶ payments
                          └──reserve slot──────▶ delivery

recurring ◀─register─ accounts (subscriptions), corporate (bulk orders)
accounts ──signal──▶ notifications (gift_reminder_due)
reports ◀── nightly aggregation ── orders / catalog / accounts
cms ── section builders ──▶ catalog / marketing selectors
```

Key boundaries:
- **Reads** cross apps via `selectors`; **writes** via `services`; **fire-and-forget side effects** via **signals** (`order_status_changed`, `gift_reminder_due`).
- The **gift snapshot** (`gifting.selectors.get_gift_customization_snapshot`) is the single shared read-path for cart, checkout, and order confirmation.
- **Idempotency + atomicity** guard order placement, stock decrement, and slot reservation.
