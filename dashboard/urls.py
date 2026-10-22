"""URL routing for the admin dashboard."""

from __future__ import annotations

from django.urls import path

from dashboard.views import (
    auth,
    catalog,
    cms,
    customers,
    home,
    marketing,
    misc,
    orders,
    reports,
    whatsapp,
)

app_name = "dashboard"


def _crud(basename, list_v, create_v, update_v, delete_v):
    """Return the four standard CRUD url patterns for an entity."""
    return [
        path(f"{basename}/", list_v.as_view(), name=f"{basename}-list"),
        path(f"{basename}/create/", create_v.as_view(), name=f"{basename}-create"),
        path(f"{basename}/<int:pk>/edit/", update_v.as_view(), name=f"{basename}-update"),
        path(f"{basename}/<int:pk>/delete/", delete_v.as_view(), name=f"{basename}-delete"),
    ]


urlpatterns = [
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),
    path("", home.home_view, name="home"),
    path("orders/", orders.order_list, name="order-list"),
    path("orders/<int:pk>/", orders.order_detail, name="order-detail"),
    path("orders/<int:pk>/invoice/", orders.order_invoice_detail, name="order-invoice"),
    path("orders/bulk-invoice/", orders.order_bulk_invoice_detail, name="order-bulk-invoice"),
    path("orders/<int:pk>/transition/", orders.order_transition, name="order-transition"),
    path("orders/<int:pk>/payment-transition/", orders.order_payment_transition, name="order-payment-transition"),
    path("orders/<int:pk>/tracking-update/", orders.order_tracking_update, name="order-tracking-update"),
    path("orders/<int:pk>/address/", orders.order_address_update, name="order-address-update"),
    path("reports/", reports.reports_view, name="reports"),
    path("reports/export/", reports.reports_export_csv, name="reports-export"),
    path("reports/recompute/", reports.reports_recompute, name="reports-recompute"),
    path("product/", catalog.ProductListView.as_view(), name="product-list"),
    path("product/create/", catalog.product_create, name="product-create"),
    path("product/<int:pk>/edit/", catalog.product_update, name="product-update"),
    path("product/<int:pk>/home-toggle/", catalog.product_home_toggle, name="product-home-toggle"),
    path("product/<int:pk>/delete/", catalog.ProductDeleteView.as_view(), name="product-delete"),
    path("review/", catalog.ReviewListView.as_view(), name="review-list"),
    path("review/<int:pk>/edit/", catalog.ReviewUpdateView.as_view(), name="review-update"),
    path("review/<int:pk>/delete/", catalog.ReviewDeleteView.as_view(), name="review-delete"),
    path("customer/", customers.CustomerListView.as_view(), name="customer-list"),
    path("customer/<int:pk>/", customers.customer_detail, name="customer-detail"),
    path("customer/<int:pk>/edit/", customers.CustomerUpdateView.as_view(), name="customer-update"),

    path("inquiry/", customers.ContactInquiryListView.as_view(), name="inquiry-list"),
    path("inquiry/<int:pk>/", customers.inquiry_detail, name="inquiry-detail"),
    path("inquiry/<int:pk>/delete/", customers.ContactInquiryDeleteView.as_view(), name="inquiry-delete"),
    path("settings/", misc.settings_view, name="settings"),
    path("payment/", misc.payment_list, name="payment-list"),
]

urlpatterns += [
    path(
        "collection/product-search/",
        catalog.collection_product_search,
        name="collection-product-search",
    ),
]
urlpatterns += _crud(
    "collection",
    catalog.CollectionListView,
    catalog.CollectionCreateView,
    catalog.CollectionUpdateView,
    catalog.CollectionDeleteView,
)

urlpatterns += _crud(
    "label",
    catalog.LabelListView,
    catalog.LabelCreateView,
    catalog.LabelUpdateView,
    catalog.LabelDeleteView,
)

urlpatterns += _crud(
    "brand",
    catalog.BrandListView,
    catalog.BrandCreateView,
    catalog.BrandUpdateView,
    catalog.BrandDeleteView,
)

urlpatterns += _crud(
    "sizechart",
    catalog.SizeChartListView,
    catalog.SizeChartCreateView,
    catalog.SizeChartUpdateView,
    catalog.SizeChartDeleteView,
)

urlpatterns += _crud(
    "coupon",
    marketing.CouponListView,
    marketing.CouponCreateView,
    marketing.CouponUpdateView,
    marketing.CouponDeleteView,
)

urlpatterns += _crud(
    "flashsale",
    marketing.FlashSaleListView,
    marketing.FlashSaleCreateView,
    marketing.FlashSaleUpdateView,
    marketing.FlashSaleDeleteView,
)
urlpatterns += _crud(
    "newsletter",
    marketing.NewsletterListView,
    marketing.NewsletterCreateView,
    marketing.NewsletterUpdateView,
    marketing.NewsletterDeleteView,
)
urlpatterns += [
    path(
        "homepagesection/reorder/",
        cms.homepage_section_reorder,
        name="homepagesection-reorder",
    ),
]
urlpatterns += _crud(
    "homepagesection",
    cms.HomepageSectionListView,
    cms.HomepageSectionCreateView,
    cms.HomepageSectionUpdateView,
    cms.HomepageSectionDeleteView,
)
urlpatterns += _crud(
    "heroslide",
    cms.HeroSlideListView,
    cms.HeroSlideCreateView,
    cms.HeroSlideUpdateView,
    cms.HeroSlideDeleteView,
)
urlpatterns += _crud(
    "blogpost",
    cms.BlogPostListView,
    cms.BlogPostCreateView,
    cms.BlogPostUpdateView,
    cms.BlogPostDeleteView,
)
urlpatterns += _crud(
    "page",
    cms.PageListView,
    cms.PageCreateView,
    cms.PageUpdateView,
    cms.PageDeleteView,
)
urlpatterns += _crud(
    "faq",
    cms.FAQItemListView,
    cms.FAQItemCreateView,
    cms.FAQItemUpdateView,
    cms.FAQItemDeleteView,
)
urlpatterns += _crud(
    "whatsapptemplate",
    whatsapp.WhatsAppTemplateListView,
    whatsapp.WhatsAppTemplateCreateView,
    whatsapp.WhatsAppTemplateUpdateView,
    whatsapp.WhatsAppTemplateDeleteView,
)
urlpatterns += _crud(
    "policy",
    cms.PolicyDocumentListView,
    cms.PolicyDocumentCreateView,
    cms.PolicyDocumentUpdateView,
    cms.PolicyDocumentDeleteView,
)


