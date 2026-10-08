"""Django forms for the cms app."""

from __future__ import annotations

from django import forms

from cms.homepage_forms import config_from_form, get_section_config_form
from cms.models import HomepageSection


class HomepageSectionAdminForm(forms.ModelForm):
    """
    Model form with structured per-type config fields (not raw JSON).

    Mirrors Phase 5 gifting pattern: one form class per section_type in a registry.
    """

    class Meta:
        model = HomepageSection
        fields = ("section_type", "title", "display_order", "is_active")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        section_type = (
            self.data.get("section_type")
            if self.data
            else (self.instance.section_type if self.instance.pk else "")
        )
        initial_config = self.instance.config if self.instance.pk else {}
        self.config_form = get_section_config_form(
            section_type=section_type,
            initial=initial_config,
        )
        if self.data:
            prefix = "config_"
            config_data = {
                key[len(prefix) :]: value
                for key, value in self.data.items()
                if key.startswith(prefix)
            }
            self.config_form = get_section_config_form(
                section_type=section_type,
                initial=initial_config,
            )
            self.config_form = type(self.config_form)(data=config_data)
        for name, field in self.config_form.fields.items():
            self.fields[f"config_{name}"] = field
            if self.instance.pk and not self.data:
                self.fields[f"config_{name}"].initial = self.config_form.initial.get(name)

    def clean(self) -> dict:
        cleaned = super().clean()
        section_type = cleaned.get("section_type", "")
        prefix = "config_"
        config_data = {}
        for key in self.fields:
            if key.startswith(prefix):
                config_data[key[len(prefix) :]] = cleaned.get(key)
        self.config_form = get_section_config_form(section_type=section_type)
        self.config_form = type(self.config_form)(data=config_data)
        if not self.config_form.is_valid():
            raise forms.ValidationError(self.config_form.errors)
        cleaned["config"] = config_from_form(section_type=section_type, form=self.config_form)
        return cleaned

    def save(self, commit: bool = True) -> HomepageSection:
        instance = super().save(commit=False)
        if "config" in self.cleaned_data:
            instance.config = self.cleaned_data["config"]
        if commit:
            instance.save()
        return instance
