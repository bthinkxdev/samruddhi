# Technical Documentation — Admin Dashboard

**Product:** Floward Clone — operational admin dashboard (Django app `dashboard`)
**Scope:** Every folder, file, function, view, form, template, and asset of the `dashboard` app, plus how it plugs into the rest of the platform. The storefront is documented in [`docs/TECH_STOREFRONT.md`](TECH_STOREFRONT.md); product intent in [`docs/PRD_CLIENT_VIEW.md`](PRD_CLIENT_VIEW.md).

---

## 1. Overview

The `dashboard` app is the **staff-facing operations console** mounted at `/dashboard/`. It provides authentication, a KPI/analytics overview, order fulfillment, catalog management, customer/corporate management, marketing, CMS, delivery configuration, reports with CSV export, and site settings.

### Design principles

| Principle | Implementation |
|-----------|----------------|
| **Reuse, don't duplicate** | Reads use the storefront's `selectors`; writes go through Django `ModelForm`s or the owning app's `services` (e.g. `orders.services.transition_order_status`). The dashboard adds **no new business models**. |
| **Generic CRUD** | A small set of generic class-based views (`DashboardListView/Create/Update/Delete`) drives ~15 management screens; each entity declares only its columns, form, and URL basename. |
| **Role-gated** | Every view requires `SuperAdmin`/`StoreAdmin` group membership (or superuser) via a shared mixin/decorator. |
| **No-build frontend** | Bootstrap 5 + Tabler Icons + ApexCharts via CDN; committed `dashboard.css`/`dashboard.js`. Charts read data from `json_script` tags. |
| **Cheap chrome** | The notification context processor short-circuits on non-dashboard requests so the storefront pays no cost. |

### Directory layout

```
dashboard/
├── apps.py                     # AppConfig (verbose_name "Dashboard")
├── admin.py                    # Intentionally empty (other apps register models)
├── models.py                   # Docstring only — no dashboard-owned models
├── tests.py                    # Docstring only
├── access.py                   # RBAC: mixin + decorator + helper
├── context_processors.py       # Topbar notifications (dashboard requests only)
├── selectors.py                # Read helpers for home + report charts
├── forms.py                    # ModelForms + inline formsets for CRUD screens
├── urls.py                     # Full route table (+ _crud helper)
├── views/                      # View package (see §6)
│   ├── __init__.py
│   ├── base.py                 # Generic CRUD base classes + mixins
│   ├── auth.py                 # Staff login/logout
│   ├── home.py                 # Overview / KPIs
│   ├── orders.py               # Order list/detail/transition
│   ├── catalog.py              # Products/categories/occasions/brands/recipients/reviews
│   ├── customers.py            # Customers + corporate accounts
│   ├── marketing.py            # Coupons/gift cards/flash sales/newsletter
│   ├── cms.py                  # Homepage sections/hero/blog/pages/FAQ/policies
│   ├── delivery.py             # Cities/slots
│   └── misc.py                 # Site settings + read-only payments
├── templatetags/
│   └── dashboard_extras.py     # cell_value, row_action_url, get_item
├── management/commands/
│   └── seed_dashboard_roles.py # Create SuperAdmin/StoreAdmin groups
└── templates/dashboard/        # Templates (see §10)
```

---

## 2. Wiring into the project

| Location | Change |
|----------|--------|
| `config/settings/base.py` → `INSTALLED_APPS` | `"dashboard"` added. |
| `config/settings/base.py` → `TEMPLATES` context processors | `"dashboard.context_processors.dashboard_chrome"` added. |
| `config/settings/base.py` → `MESSAGE_TAGS` | Maps Django `ERROR` → Bootstrap `danger`. |
| `config/urls.py` | `path("dashboard/", include("dashboard.urls"))` (non-i18n prefix). |

`dashboard/apps.py` defines `DashboardConfig` (`name="dashboard"`, `verbose_name="Dashboard"`, `default_auto_field=BigAutoField`).

---

## 3. Access Control — `dashboard/access.py`

`DASHBOARD_GROUPS = ("SuperAdmin", "StoreAdmin")`.

| Symbol | Purpose |
|--------|---------|
| `user_can_access_dashboard(user) -> bool` | True for superusers or members of a dashboard staff group; False for anonymous. |
| `DashboardAccessMixin(AccessMixin)` | Gates class-based views. Anonymous → redirect to `dashboard:login`; authenticated-but-unauthorized → 403 (`raise_exception=True`). `login_url = reverse_lazy("dashboard:login")`. |
| `dashboard_required(view_func)` | Decorator for function-based views. Anonymous → `redirect_to_login`; unauthorized → `PermissionDenied` (403). |

Every dashboard view is protected: class-based views inherit `DashboardAccessMixin` (via `DashboardContextMixin`), function-based views wear `@dashboard_required`. The login view itself is intentionally public.

---

## 4. Roles seeding — `management/commands/seed_dashboard_roles.py`

`python manage.py seed_dashboard_roles [--user <username_or_email>]`

- Creates the `SuperAdmin` and `StoreAdmin` groups if missing.
- Optionally assigns a given user to both groups so they can log in immediately.

---

## 5. Read layer — `dashboard/selectors.py`

Dashboard-specific read helpers for the overview and report charts. (Broader analytics reuse `reports.selectors`.)

| Function | Purpose |
|----------|---------|
| `get_sales_series(*, days=14)` | Ordered date labels + revenue + order counts for the last N days from `DailySalesReport` (zero-fills missing days). |
| `get_customer_split()` | `[new%, returning%]` from the most recent `DailyCustomerReport`. |
| `get_top_products(*, limit=5)` | Top products by revenue on the latest day with `DailyProductPerformance` data. |
| `get_low_stock_products(*, limit=5)` | Active products at/below their `low_stock_threshold` (`F()` comparison). |
| `get_recent_orders(*, limit=6)` | Most recent orders with customer preloaded (`select_related`). |
| `get_dashboard_counts()` | Cheap counts: active products, customers, orders. |

---

## 6. View layer — `dashboard/views/`

### 6.1 Generic CRUD base — `views/base.py`

| Class | Role |
|-------|------|
| `DashboardContextMixin(DashboardAccessMixin)` | Adds `nav_section` + `page_title` to context; carries RBAC gating into every screen. |
| `DashboardListView(DashboardContextMixin, ListView)` | Generic paginated (25/page) searchable list. Declarative attrs: `columns`, `search_fields`, `select_related`, `prefetch_related`, `url_basename`, `singular_name`, `plural_name`, `can_create/edit/delete`, `default_ordering=["-pk"]`. `get_queryset()` applies select/prefetch, `q` search over `search_fields` (OR'd `icontains`), and a default ordering if unordered (prevents `UnorderedObjectListWarning`). `get_context_data()` exposes columns, names, search state, create URL, and a `page`-stripped querystring. |
| `_FormStyleMixin` | `get_form()` applies Bootstrap classes (`form-control` / `form-select` / `form-check-input`) to plain `ModelForm` widgets at render time. |
| `DashboardCreateView(_FormStyleMixin, DashboardContextMixin, CreateView)` | Template `crud/form.html`; success message + redirect to `<basename>-list`; context `form_mode="create"`, cancel URL. |
| `DashboardUpdateView(...)` | Same as create with `form_mode="edit"`. |
| `DashboardDeleteView(DashboardContextMixin, DeleteView)` | Template `crud/confirm_delete.html`; success message + redirect to list. |

All CRUD screens render one of three shared templates (`crud/list.html`, `crud/form.html`, `crud/confirm_delete.html`).

### 6.2 Auth — `views/auth.py`
| View | Behavior |
|------|----------|
| `login_view(request)` | `@never_cache`. Renders/processes `dashboard/login.html`. Accepts username **or** email (`_resolve_username`), authenticates, rejects non-staff with a message, honors `?next=`, redirects already-authorized users to `dashboard:home`. |
| `logout_view(request)` | `@never_cache`. Logs out and redirects to `dashboard:login`. |
| `_resolve_username(identifier)` | Maps an email to its username for `authenticate()`. |

### 6.3 Home — `views/home.py`
- `home_view(request)` — `@dashboard_required`, `@require_GET`. Renders `dashboard/home.html` with: `reports.get_admin_dashboard_summary()`, `get_sales_series(days=14)`, `get_customer_split()`, `get_dashboard_counts()`, `get_top_products`, `get_low_stock_products`, `get_recent_orders`.

### 6.4 Orders — `views/orders.py`
| View | Behavior |
|------|----------|
| `order_list(request)` | `@dashboard_required`, GET. Paginated (25) order list; filter by `status`, search by `order_number`; `select_related` customer/currency. Template `orders/list.html`. |
| `order_detail(request, pk)` | `@dashboard_required`, GET. Order + line items + status history + payments + proof of delivery; computes **allowed next statuses** from `ALLOWED_STATUS_TRANSITIONS`. Template `orders/detail.html`. |
| `order_transition(request, pk)` | `@dashboard_required`, `@require_POST`. Calls `orders.services.transition_order_status(order, new_status, actor, note)`; catches `InvalidOrderStatusTransitionError` into a message; redirects to detail. |

Order status changes go **through the orders service state machine**, which emits `order_status_changed` → notifications fire automatically.

### 6.5 Catalog — `views/catalog.py`
- **Products** (custom, for inline formsets): `ProductListView` (list), `product_create` / `product_update` (function views, `@dashboard_required` + GET/POST) rendering `catalog/product_form.html` via `_render_product_form(request, product, mode)` which validates `ProductForm` + `ProductVariantFormSet` + `ProductImageFormSet` together and saves atomically; `ProductDeleteView`. Helper `_style(form)` applies Bootstrap classes (also reused by `misc.py`).
- **Categories / Occasions / Brands / Recipients**: full `List/Create/Update/Delete` generic CRUD.
- **Reviews** (moderation only, `can_create=False`): `ReviewListView`, `ReviewUpdateView` (sets `moderated_by = request.user` in `form_valid`), `ReviewDeleteView`.

### 6.6 Customers — `views/customers.py`
| View | Behavior |
|------|----------|
| `CustomerListView` | Generic list of `CustomerProfile` (`can_create=False`, `can_delete=False`); search by email/username/phone. |
| `customer_detail(request, pk)` | `@dashboard_required`. Profile + addresses + last 10 orders. Template `customers/detail.html`. |
| `CustomerUpdateView` | Edit profile via `CustomerProfileForm`. |
| `CorporateListView` | List `CorporateAccount` with an extra **status filter** (`get_queryset`/`get_context_data` add `approval_status` filtering + `extra_filters`). |
| `CorporateUpdateView` | Edit via `CorporateAccountForm`; `form_valid` stamps `approved_by = request.user` when status becomes Approved/Rejected. |

### 6.7 Marketing — `views/marketing.py`
Generic CRUD for `Coupon`, `GiftCard`, `FlashSale`, `NewsletterSubscriber` (`CouponListView/Create/Update/Delete`, etc.).

### 6.8 CMS — `views/cms.py`
Generic CRUD for `HomepageSection`, `HeroSlide`, `BlogPost`, `Page`, `FAQItem`, `PolicyDocument`.

### 6.9 Delivery — `views/delivery.py`
Generic CRUD for `City` and `DeliverySlot`.

### 6.10 Misc — `views/misc.py`
| View | Behavior |
|------|----------|
| `settings_view(request)` | `@dashboard_required`, GET/POST. Edits the `SiteSettings` singleton via `SiteSettingsForm`; template `settings.html`. |
| `payment_list(request)` | `@dashboard_required`, GET. Read-only paginated `PaymentTransaction` list; filter by `status`, search by order number; template `payments/list.html`. |

---

## 7. Forms — `dashboard/forms.py`

Shared widgets: `_DATE`, `_DATETIME`, `_TIME` (native HTML5 inputs).

| Form | Model | Notes |
|------|-------|-------|
| `SlugAutoMixin` | — | Auto-fills empty `slug` from `name`/`title` in `clean()`. |
| `ProductForm` | `Product` | Full product fields incl. flags + SEO; `slug` optional. |
| `CategoryForm` | `Category` | Slug optional; parent, order, SEO. |
| `OccasionForm` | `Occasion` | Date widgets for active window. |
| `BrandForm` | `Brand` | Logo, featured flag. |
| `RecipientForm` | `Recipient` | Icon, order, active. |
| `ReviewForm` | `Review` | Moderation status only. |
| `ProductVariantFormSet` | `ProductVariant` | Inline formset (type, name, price delta, sku suffix, stock). |
| `ProductImageFormSet` | `ProductImage` | Inline formset (image, alt, order, is_primary). |
| `CustomerProfileForm` | `CustomerProfile` | Phone, verification, language/currency, notify prefs. |
| `CorporateAccountForm` | `CorporateAccount` | Company, license, approval status. |
| `CouponForm` | `Coupon` | Discount config, usage limits, validity window, category scope. |
| `GiftCardForm` | `GiftCard` | Code, balances, active. |
| `FlashSaleForm` | `FlashSale` | Products, discount %, window. |
| `NewsletterSubscriberForm` | `NewsletterSubscriber` | Email, active. |
| `HomepageSectionForm` | `HomepageSection` | Type, title, order, active, raw `config`. |
| `HeroSlideForm` | `HeroSlide` | Media + poster + order. |
| `BlogPostForm` | `BlogPost` | Slug optional, publish window, SEO. |
| `PageForm` | `Page` | Slug optional, publish window, SEO. |
| `FAQItemForm` | `FAQItem` | Q/A, order, publish. |
| `PolicyDocumentForm` | `PolicyDocument` | Slug optional, policy type, SEO. |
| `CityForm` | `City` | Slug optional, delivery charge, same-day cutoff. |
| `DeliverySlotForm` | `DeliverySlot` | Time widgets, capacity, type. |
| `SiteSettingsForm` | `SiteSettings` | Branding, socials, defaults, tax/shipping. |
| `OrderStatusForm` | — | Free-standing form; `new_status` choices injected via `allowed_choices` kwarg + optional note. |

---

## 8. Context processor — `dashboard/context_processors.py`

`dashboard_chrome(request)`:
- Returns `{}` (no queries) for non-`/dashboard/` requests or anonymous users.
- Otherwise returns `dashboard_notifications` (latest 5 unread) and `dashboard_unread_count` for the topbar bell.

---

## 9. Template tags — `dashboard/templatetags/dashboard_extras.py`

| Tag/filter | Purpose |
|------------|---------|
| `cell_value(obj, column)` (simple tag) | Resolve a column value supporting dotted attribute paths and callables (e.g. `user.get_full_name`, `get_moderation_status_display`). |
| `row_action_url(basename, action, pk)` (simple tag) | Build `dashboard:<basename>-<action>` URLs for list-row action buttons. |
| `get_item(dictionary, key)` (filter) | Variable-key dict lookup inside templates. |

Column dicts support a `type` hint (`money`, `bool`, `badge`, `datetime`, `image`) that the list template renders appropriately.

---

## 10. Templates — `dashboard/templates/dashboard/`

| Template | Purpose |
|----------|---------|
| `base.html` | Dashboard layout: Bootstrap 5, Tabler Icons, Poppins, `dashboard.css`/`dashboard.js` via CDN; content/title/extra-CSS/JS blocks; includes sidebar/topbar/messages. |
| `login.html` | Staff login page. |
| `home.html` | Overview: KPI cards (revenue, orders, customers, low stock), ApexCharts (sales trend, customer split), top/low-stock/recent-order lists. Chart data via `json_script`. |
| `settings.html` | `SiteSettings` editor. |
| `partials/_sidebar.html` | Dynamic sidebar nav; highlights active `nav_section`. |
| `partials/_topbar.html` | Toggle buttons, notification bell (`dashboard_chrome`), user dropdown (logout, Django admin). |
| `partials/_pagination.html` | Generic pagination preserving query params. |
| `partials/_messages.html` | Bootstrap-styled Django messages. |
| `crud/list.html` | Generic list screen (search, columns, row actions, pagination). |
| `crud/form.html` | Generic create/edit form screen. |
| `crud/confirm_delete.html` | Generic delete confirmation. |
| `catalog/product_form.html` | Product create/edit with inline variant + image formsets. |
| `orders/list.html` | Order list with status filter + search. |
| `orders/detail.html` | Order detail: items, totals, status history, payments, POD, status-transition form. |
| `customers/detail.html` | Customer profile: contact, addresses, recent orders. |
| `payments/list.html` | Read-only payment transactions list. |
| `reports/index.html` | Reports: date-range filter, KPI cards, sales ApexChart, daily sales + customer tables, CSV export + recompute. |

---

## 11. Static assets — `static/dashboard/`

| File | Purpose |
|------|---------|
| `css/dashboard.css` | Hand-ported theme CSS: Bootstrap variable overrides (orange primary, Poppins), sidebar/topbar layout, icon shapes, avatars. |
| `js/dashboard.js` | Plain JS (no ES modules): sidebar toggle, Bootstrap form validation, ApexCharts init reading `json_script` data. |
| `images/logo.svg`, `logo-icon.svg`, `logo-1.svg` | Dashboard branding. |

Bootstrap, Tabler Icons, and ApexCharts load from CDN (no Node build step), consistent with the storefront's no-build strategy.

---

## 12. Route table — `dashboard/urls.py` (`app_name="dashboard"`)

`_crud(basename, list_v, create_v, update_v, delete_v)` returns the four standard patterns (`-list`, `-create`, `-update`, `-delete`) for an entity.

### Explicit routes
| Route | View | Name |
|-------|------|------|
| `login/` | `auth.login_view` | `login` |
| `logout/` | `auth.logout_view` | `logout` |
| `` | `home.home_view` | `home` |
| `orders/` | `orders.order_list` | `order-list` |
| `orders/<int:pk>/` | `orders.order_detail` | `order-detail` |
| `orders/<int:pk>/transition/` | `orders.order_transition` | `order-transition` |
| `reports/` | `reports.reports_view` | `reports` |
| `reports/export/` | `reports.reports_export_csv` | `reports-export` |
| `reports/recompute/` | `reports.reports_recompute` | `reports-recompute` |
| `product/` | `catalog.ProductListView` | `product-list` |
| `product/create/` | `catalog.product_create` | `product-create` |
| `product/<int:pk>/edit/` | `catalog.product_update` | `product-update` |
| `product/<int:pk>/delete/` | `catalog.ProductDeleteView` | `product-delete` |
| `review/` | `catalog.ReviewListView` | `review-list` |
| `review/<int:pk>/edit/` | `catalog.ReviewUpdateView` | `review-update` |
| `review/<int:pk>/delete/` | `catalog.ReviewDeleteView` | `review-delete` |
| `customer/` | `customers.CustomerListView` | `customer-list` |
| `customer/<int:pk>/` | `customers.customer_detail` | `customer-detail` |
| `customer/<int:pk>/edit/` | `customers.CustomerUpdateView` | `customer-update` |
| `corporate/` | `customers.CorporateListView` | `corporate-list` |
| `corporate/<int:pk>/edit/` | `customers.CorporateUpdateView` | `corporate-update` |
| `settings/` | `misc.settings_view` | `settings` |
| `payment/` | `misc.payment_list` | `payment-list` |

### Generic CRUD entities (via `_crud`)
Each provides `<basename>-list`, `-create`, `-update`, `-delete`:

`category`, `occasion`, `brand`, `recipient` (catalog) · `coupon`, `giftcard`, `flashsale`, `newsletter` (marketing) · `homepagesection`, `heroslide`, `blogpost`, `page`, `faq`, `policy` (cms) · `city`, `slot` (delivery).

---

## 13. Request flow (example: advancing an order)

```
Staff clicks "Mark as Preparing" on orders/detail.html
  → POST /dashboard/orders/<pk>/transition/
     → @dashboard_required (RBAC check)
     → orders.services.transition_order_status(order, new_status, actor=user, note=...)
          → validates against ALLOWED_STATUS_TRANSITIONS (atomic)
          → writes OrderStatusHistory
          → emits order_status_changed signal
               → notifications enqueue email/SMS/WhatsApp/in-app to customer
     → success/error message
  → redirect to dashboard:order-detail
```

The dashboard is a thin operations skin: it **never bypasses** the storefront's services or state machines, guaranteeing the same invariants (idempotency, atomic stock/slot handling, valid status transitions, review moderation) whether an action originates from a customer or from staff.

---

## 14. Notes & conventions

- `dashboard/models.py`, `dashboard/tests.py`, and `dashboard/admin.py` are intentionally content-free (docstring/comment only) — the dashboard owns no models and relies on other apps' `admin.py` registrations as a fallback UI.
- Reads for list screens use the ORM directly inside generic views (with `select_related`/`prefetch_related` declared per screen) rather than storefront selectors, since these are back-office queries; **analytics and order/state writes always reuse the owning app's selectors/services**.
- Lint/format compliance: Black (line-length 100), isort (black profile), flake8 — the app passes CI checks.
- Access is group-based; run `seed_dashboard_roles` (and assign a user) before first login.
