"""Marketing management: coupons, gift cards, flash sales, newsletter."""

from __future__ import annotations

from dashboard import forms
from dashboard.views.base import (
    DashboardCreateView,
    DashboardDeleteView,
    DashboardListView,
    DashboardUpdateView,
)
from marketing.models import Coupon, FlashSale, NewsletterSubscriber


class CouponListView(DashboardListView):
    model = Coupon
    nav_section = "coupons"
    url_basename = "coupon"
    singular_name = "Coupon"
    plural_name = "Coupons"
    search_fields = ["code"]
    columns = [
        {"label": "Code", "name": "code"},
        {"label": "Type", "name": "get_discount_type_display"},
        {"label": "Value", "name": "discount_value", "type": "money"},
        {"label": "Valid until", "name": "valid_until", "type": "datetime"},
        {"label": "Active", "name": "is_currently_active", "type": "bool"},
    ]


class CouponCreateView(DashboardCreateView):
    model = Coupon
    form_class = forms.CouponForm
    nav_section = "coupons"
    url_basename = "coupon"
    singular_name = "Coupon"

    def form_valid(self, form):
        from django.contrib import messages
        from django.utils import timezone
        
        response = super(DashboardCreateView, self).form_valid(form)
        
        now = timezone.now()
        is_expired = self.object.valid_until and self.object.valid_until < now
        
        if is_expired:
            messages.warning(self.request, f"'{self.object}' created successfully, but it is inactive because the expiration date has passed.")
        else:
            messages.success(self.request, f"'{self.object}' created successfully.")
            
        return response


class CouponUpdateView(DashboardUpdateView):
    model = Coupon
    form_class = forms.CouponForm
    nav_section = "coupons"
    url_basename = "coupon"
    singular_name = "Coupon"

    def form_valid(self, form):
        from django.contrib import messages
        from django.utils import timezone
        
        response = super(DashboardUpdateView, self).form_valid(form)
        
        now = timezone.now()
        is_expired = self.object.valid_until and self.object.valid_until < now
        
        if is_expired:
            messages.warning(self.request, f"'{self.object}' updated successfully, but it is inactive because the expiration date has passed.")
        else:
            messages.success(self.request, f"'{self.object}' updated successfully.")
            
        return response


class CouponDeleteView(DashboardDeleteView):
    model = Coupon
    nav_section = "coupons"
    url_basename = "coupon"
    singular_name = "Coupon"


class FlashSaleListView(DashboardListView):
    model = FlashSale
    nav_section = "flashsales"
    url_basename = "flashsale"
    singular_name = "Flash Sale"
    plural_name = "Flash Sales"
    search_fields = ["name"]
    columns = [
        {"label": "Name", "name": "name"},
        {"label": "Discount %", "name": "discount_percentage"},
        {"label": "Starts", "name": "starts_at", "type": "datetime"},
        {"label": "Ends", "name": "ends_at", "type": "datetime"},
        {"label": "Active", "name": "is_currently_active", "type": "bool"},
    ]


class FlashSaleCreateView(DashboardCreateView):
    model = FlashSale
    form_class = forms.FlashSaleForm
    nav_section = "flashsales"
    url_basename = "flashsale"
    singular_name = "Flash Sale"
    template_name = "dashboard/marketing/flashsale_form.html"

    def form_valid(self, form):
        from django.contrib import messages
        from django.utils import timezone
        
        response = super(DashboardCreateView, self).form_valid(form)
        
        now = timezone.now()
        is_expired = self.object.ends_at and self.object.ends_at < now
        
        if is_expired:
            messages.warning(self.request, f"'{self.object}' created successfully, but it is inactive because the expiration date has passed.")
        else:
            messages.success(self.request, f"'{self.object}' created successfully.")
            
        return response


class FlashSaleUpdateView(DashboardUpdateView):
    model = FlashSale
    form_class = forms.FlashSaleForm
    nav_section = "flashsales"
    url_basename = "flashsale"
    singular_name = "Flash Sale"
    template_name = "dashboard/marketing/flashsale_form.html"

    def form_valid(self, form):
        from django.contrib import messages
        from django.utils import timezone
        
        response = super(DashboardUpdateView, self).form_valid(form)
        
        now = timezone.now()
        is_expired = self.object.ends_at and self.object.ends_at < now
        
        if is_expired:
            messages.warning(self.request, f"'{self.object}' updated successfully, but it is inactive because the expiration date has passed.")
        else:
            messages.success(self.request, f"'{self.object}' updated successfully.")
            
        return response


class FlashSaleDeleteView(DashboardDeleteView):
    model = FlashSale
    nav_section = "flashsales"
    url_basename = "flashsale"
    singular_name = "Flash Sale"


class NewsletterListView(DashboardListView):
    model = NewsletterSubscriber
    nav_section = "newsletter"
    url_basename = "newsletter"
    singular_name = "Subscriber"
    plural_name = "Newsletter Subscribers"
    search_fields = ["email"]
    columns = [
        {"label": "Email", "name": "email"},
        {"label": "Active", "name": "is_active", "type": "bool"},
        {"label": "Subscribed", "name": "created_at", "type": "datetime"},
    ]


class NewsletterCreateView(DashboardCreateView):
    model = NewsletterSubscriber
    form_class = forms.NewsletterSubscriberForm
    nav_section = "newsletter"
    url_basename = "newsletter"
    singular_name = "Subscriber"


class NewsletterUpdateView(DashboardUpdateView):
    model = NewsletterSubscriber
    form_class = forms.NewsletterSubscriberForm
    nav_section = "newsletter"
    url_basename = "newsletter"
    singular_name = "Subscriber"


class NewsletterDeleteView(DashboardDeleteView):
    model = NewsletterSubscriber
    nav_section = "newsletter"
    url_basename = "newsletter"
    singular_name = "Subscriber"
