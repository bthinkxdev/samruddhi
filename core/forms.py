"""Django forms for the core app."""

from __future__ import annotations

from django import forms

from core.models import Currency


class CurrencyAdminForm(forms.ModelForm):
    """Admin form for Currency with uppercase code normalization."""

    class Meta:
        model = Currency
        fields = ("code", "symbol", "exchange_rate_to_base", "is_default")

    def clean_code(self) -> str:
        """Normalize currency code to uppercase."""
        return self.cleaned_data["code"].upper()


class ContactInquiryForm(forms.ModelForm):
    """Form for standard contact inquiries and quote requests."""

    class Meta:
        from core.models import ContactInquiry
        model = ContactInquiry
        fields = ("name", "email", "message")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Your Name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Your Email"}),
            "message": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Your Message"}),
        }
