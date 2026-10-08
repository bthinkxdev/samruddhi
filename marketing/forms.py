"""Django forms for the marketing app."""

from __future__ import annotations

from django import forms


class NewsletterSignupForm(forms.Form):
    """Public-facing newsletter signup form."""

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"}),
    )