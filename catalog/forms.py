"""Django forms for the catalog app."""

from __future__ import annotations

from django import forms
from catalog.models import Review

class ReviewSubmissionForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "title", "body"]
        widgets = {
            "rating": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 5}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Brief summary of your review"}),
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "What did you think about this product?"}),
        }
