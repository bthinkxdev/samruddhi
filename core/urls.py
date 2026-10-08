"""URL routing for the core app."""

from __future__ import annotations

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("health/", views.health_view, name="health"),
    path("preferences/currency/", views.set_currency_view, name="set-currency"),
    path("preferences/country/", views.set_country_view, name="set-country"),
    path("about-us/", views.about_us_view, name="about-us"),
    path("privacy-policy/", views.privacy_policy_view, name="privacy-policy"),
    path("shipping-policy/", views.shipping_policy_view, name="shipping-policy"),
    path("terms-of-service/", views.terms_of_service_view, name="terms-of-service"),
    path("refund-policy/", views.refund_policy_view, name="refund-policy"),
    path("contact-us/", views.contact_us_view, name="contact-us"),
    path("contact-us/submit/", views.submit_inquiry_view, name="submit-inquiry"),
    path("faq/", views.faq_view, name="faq"),
    path("blog/", views.blog_view, name="blog"),
    path("p/<slug:slug>/", views.page_view, name="page"),
    path("captcha/<slug:scope>.png", views.ImageCaptchaImageView.as_view(), name="image_captcha"),
]
