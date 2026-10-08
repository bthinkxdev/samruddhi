# Phase 10 QA Checklist

Mapped against Phases 1–9 modules. Status as of 2026-07-07.

| Module | Requirement | Status |
|--------|-------------|--------|
| **core** | TimeStampedModel, SoftDelete, SEOModel, Currency | PASS |
| **core** | SiteSettings singleton (pk=1) | PASS |
| **accounts** | Email/OTP/Google auth | PASS |
| **accounts** | OTP rate limit (3/10min Redis) | PASS |
| **accounts** | Login rate limit (10/10min) | PASS |
| **accounts** | Addresses paginated (page_size=50) | PASS |
| **accounts** | Corporate pending approvals RBAC | PASS |
| **catalog** | PLP paginated (24/page) | PASS |
| **catalog** | PDP bounded queries | PASS |
| **catalog** | SEO meta on product/category | PASS |
| **catalog** | Flash sale price in selectors | PASS |
| **gifting** | Builder structured forms | PASS |
| **gifting** | HTMX CSRF on POST | PASS |
| **cart** | Coupon via marketing service | PASS |
| **cart** | HTMX drawer CSRF | PASS |
| **checkout** | place_order idempotent | PASS |
| **checkout** | Delivery slot reservation | PASS |
| **payments** | Gateway registry, no raw card data | PASS |
| **payments** | confirm_payment_success convergence | PASS |
| **orders** | Status transitions + signals | PASS |
| **delivery** | Slot capacity enforcement | PASS |
| **corporate** | Dashboard lists paginated | PASS |
| **recurring** | Shared schedule engine | PASS |
| **marketing** | Coupon limits enforced | PASS |
| **marketing** | Abandoned cart Celery task | PASS |
| **cms** | Homepage structured admin forms | PASS |
| **cms** | Cache refresh on CMS saves | PASS |
| **reports** | Pre-aggregated nightly tables | PASS |
| **reports** | Admin dashboard RBAC | PASS |
| **notifications** | Order status signal dispatch | PASS |
| **SEO** | Meta, canonical, hreflang | PASS |
| **SEO** | JSON-LD Product on PDP | PASS |
| **SEO** | XML sitemap (5 sections) | PASS |
| **Performance** | Homepage rails single fetch | PASS |
| **Performance** | Category tree + currency cached | PASS |
| **Performance** | PLP duplicate category query fixed | PASS |
| **Deployment** | Gunicorn + Nginx + systemd | PASS |
| **Deployment** | Sentry wired (prod) | PASS |
| **Deployment** | Backup restore drill documented | PASS |

## Critical / High open items

None.

## Notes

- Lighthouse scores require running against a deployed URL with real assets; see `docs/PHASE10_REPORT.md`.
- Locust load test: run `locust -f loadtests/locustfile.py --host=<url>` for p50/p95/p99.
