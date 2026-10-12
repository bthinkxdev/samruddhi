"""Root URL configuration for config."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import index, sitemap
from django.urls import include, path

from core.sitemaps import (
    BlogPostSitemap,
    CollectionSitemap,
    PageSitemap,
    ProductSitemap,
)

sitemaps = {
    "products": ProductSitemap,
    "collections": CollectionSitemap,
    "blog": BlogPostSitemap,
    "pages": PageSitemap,
}

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sitemap.xml", index, {"sitemaps": sitemaps}, name="sitemap-index"),
    path(
        "sitemap-<section>.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("marketing/", include("marketing.urls")),
    path("", include("cms.urls")),
    path("shop/", include("catalog.urls")),
    path("cart/", include("cart.urls")),
    path("checkout/", include("checkout.urls")),
    path("orders/", include("orders.urls")),
    path("payments/", include("payments.urls")),
    path("reports/", include("reports.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("delhivery/", include("delhivery.urls")),
    path("whatsapp/", include("whatsapp.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
