"""Django forms for the orders app."""

from __future__ import annotations

from django import forms


class OrderAddressForm(forms.Form):
    """
    Edit an order's frozen ``delivery_address_snapshot``.

    Not a ModelForm — the target is a JSON snapshot captured at checkout, not a
    live ``accounts.Address`` row. Field set mirrors ``accounts.forms.AddressForm``.
    """

    name = forms.CharField(max_length=255, required=False)
    email = forms.EmailField(max_length=255, required=False)
    phone = forms.CharField(max_length=20, required=False)
    line1 = forms.CharField(max_length=255, label="Address line 1")
    line2 = forms.CharField(max_length=255, required=False, label="Address line 2")
    city = forms.CharField(max_length=120)
    state = forms.CharField(max_length=120, required=False)
    pincode = forms.CharField(max_length=20, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
