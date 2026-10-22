"""ModelForms used by the admin dashboard CRUD screens."""

from __future__ import annotations

import copy
from datetime import timedelta

from django import forms
from django.forms.models import InlineForeignKeyField
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import CustomerProfile
from catalog.models import (
    Brand,
    Collection,
    Label,
    Product,
    ProductImage,
    ProductSpecification,
    ProductVariant,
    Review,
    SizeChart,
)
from cms.services import next_homepage_section_order
from dashboard.uploads import RetainUploadsMixin
from cms.models import BlogPost, FAQItem, HeroSlide, HomepageSection, Page, PolicyDocument
from core.models import SiteSettings, Currency

from marketing.models import Coupon, FlashSale, NewsletterSubscriber
from whatsapp.models import WhatsAppTemplate

_DATE = forms.DateInput(attrs={"type": "date"})
_DATETIME = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
_TIME = forms.TimeInput(attrs={"type": "time"})


class FutureDateRangeMixin:

    date_range_fields: tuple[str, str] = ("", "")
    #allow for the time spent filling the form after picking "now"
    PAST_GRACE = timedelta(minutes=5)
    _PICKER_FORMAT = "%Y-%m-%dT%H:%M"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        now = timezone.localtime().replace(second=0, microsecond=0)
        start_name, end_name = self.date_range_fields
        for name in (start_name, end_name):
            saved = self._saved_value(name)
            earliest = min(now, timezone.localtime(saved)) if saved else now
            self.fields[name].widget.attrs["min"] = earliest.strftime(self._PICKER_FORMAT)
        self.fields[end_name].widget.attrs["data-min-from"] = self[start_name].auto_id

    def _saved_value(self, name):
        if self.instance and self.instance.pk:
            return getattr(self.instance, name, None)
        return None

    def clean(self):
        cleaned = super().clean()
        cutoff = timezone.now() - self.PAST_GRACE
        start_name, end_name = self.date_range_fields
        for name in (start_name, end_name):
            value = cleaned.get(name)
            if value and value < cutoff and value != self._saved_value(name):
                self.add_error(name, "Date and time can't be in the past.")
        start, end = cleaned.get(start_name), cleaned.get(end_name)
        if start and end and end <= start:
            self.add_error(end_name, "End date must be after the start date.")
        return cleaned


class SlugAutoMixin(forms.ModelForm):
    """Auto-populate an empty ``slug`` from ``name``/``title`` on save."""

    def clean(self):
        cleaned = super().clean()
        if "slug" in self.fields and not cleaned.get("slug"):
            source = cleaned.get("name") or cleaned.get("title")
            if source:
                cleaned["slug"] = slugify(source)
        return cleaned


def _inactive_suffix(obj) -> str:
    return "" if getattr(obj, "is_active", True) else " (inactive)"


class CollectionChoiceField(forms.ModelMultipleChoiceField):
    """Collection checkboxes labelled with their parent ("Parent › Child")."""

    def label_from_instance(self, obj: Collection) -> str:
        name = f"{obj.parent.name} › {obj.name}" if obj.parent_id else obj.name
        return name + _inactive_suffix(obj)


class LabelChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: Label) -> str:
        return obj.name + _inactive_suffix(obj)


class SizeChartChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj: SizeChart) -> str:
        return str(obj) + _inactive_suffix(obj)


def find_sku_owner(sku: str, *, exclude_product_pk=None) -> str:
    """
    Describe where a SKU is already used outside the given product.

    """
    products = Product.objects.filter(sku__iexact=sku)
    variants = ProductVariant.objects.filter(sku_suffix__iexact=sku).select_related("product")
    if exclude_product_pk:
        products = products.exclude(pk=exclude_product_pk)
        variants = variants.exclude(product_id=exclude_product_pk)
    product = products.first()
    if product:
        return f'product "{product.name}"'
    variant = variants.first()
    if variant:
        return f'a variant of "{variant.product.name}"'
    return ""


class ProductForm(RetainUploadsMixin, SlugAutoMixin):
    retained_upload_fields = ("og_image",)

    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "sku",
            "collections",
            "brand",
            "size_chart",
            "base_price",
            "mrp",
            "purchase_price",

            "color",
            "stock_quantity",
            "low_stock_threshold",
            "is_active",
            "labels",
            "meta_title",
            "meta_description",
            "og_image",
            "weight",
            "length",
            "width",
            "height",
        ]
        field_classes = {
            "collections": CollectionChoiceField,
            "labels": LabelChoiceField,
            "size_chart": SizeChartChoiceField,
        }
        widgets = {
            "collections": forms.CheckboxSelectMultiple,
            "labels": forms.CheckboxSelectMultiple,
        }
        error_messages = {
            "name": {"required": "Product name is required."},
            "sku": {"required": "SKU is required."},
            "base_price": {"required": "Base price is required."},
            "mrp": {"required": "MRP is required."},
            "purchase_price": {"required": "Purchase price is required."},
            "stock_quantity": {"required": "Stock quantity is required."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.db.models import Q

        editing = bool(self.instance and self.instance.pk)

        size_charts = Q(is_active=True)
        if editing and self.instance.size_chart_id:
            size_charts |= Q(pk=self.instance.size_chart_id)
        self.fields["size_chart"].queryset = SizeChart.objects.filter(size_charts).order_by("name")
        self.fields["size_chart"].empty_label = "No Size Chart"

        collections = Q(is_active=True)
        labels = Q(is_active=True)
        if editing:
            collections |= Q(pk__in=self.instance.collections.values("pk"))
            labels |= Q(pk__in=self.instance.labels.values("pk"))
        self.fields["collections"].queryset = (
            Collection.objects.filter(collections).select_related("parent").order_by("display_order", "name")
        )
        self.fields["labels"].queryset = Label.objects.filter(labels).order_by("display_order", "name")
        self.fields["slug"].required = False
        self.fields["base_price"].required = False
        self.fields["mrp"].required = False
        self.fields["purchase_price"].required = False
        self.fields["stock_quantity"].required = False
        self.fields["low_stock_threshold"].required = False

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip()
        unchanged = self.instance.pk and sku.lower() == (self.instance.sku or "").lower()
        if sku and not unchanged:
            owner = find_sku_owner(sku, exclude_product_pk=self.instance.pk)
            if owner.startswith("a variant"):
                raise forms.ValidationError(f'SKU "{sku}" is already used by {owner}.')
        return sku

    def clean(self):
        cleaned = super().clean()
        for field in ["base_price", "mrp", "purchase_price", "stock_quantity", "low_stock_threshold"]:
            if cleaned.get(field) is None:
                cleaned[field] = 0
        return cleaned


class CollectionForm(RetainUploadsMixin, SlugAutoMixin):
    """Collection details plus its product membership (managed from the collection side)."""

    retained_upload_fields = ("image", "banner_image")

    products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.all(),
        required=False,
        widget=forms.MultipleHiddenInput,
    )

    class Meta:
        model = Collection
        fields = [
            "name",
            "slug",
            "parent",
            "description",
            "image",
            "banner_image",
            "display_order",
            "is_active",
            "show_on_homepage",
            "homepage_product_limit",
            "meta_title",
            "meta_description",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "banner_image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["homepage_product_limit"].required = False
        #only top-level collections can be parents (the navigation is two levels deep)
        parents = Collection.objects.filter(parent__isnull=True)
        if self.instance.pk:
            parents = parents.exclude(pk=self.instance.pk)
            self.initial["products"] = list(self.instance.products.values_list("pk", flat=True))
        self.fields["parent"].queryset = parents.order_by("display_order", "name")

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if parent and self.instance.pk and self.instance.children.exists():
            raise forms.ValidationError(
                "This collection has sub-collections, so it cannot be nested under another one."
            )
        return parent

    def clean_homepage_product_limit(self):
        limit = self.cleaned_data.get("homepage_product_limit")
        if limit is None:
            return self._meta.model._meta.get_field("homepage_product_limit").default
        return limit

    def _save_m2m(self):
        super()._save_m2m()
        self.instance.products.set(self.cleaned_data["products"])


class LabelForm(SlugAutoMixin):
    class Meta:
        model = Label
        fields = ["name", "slug", "background_color", "text_color", "display_order", "is_active"]
        widgets = {
            "background_color": forms.TextInput(attrs={"type": "color", "class": "form-control-color"}),
            "text_color": forms.TextInput(attrs={"type": "color", "class": "form-control-color"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False


class BrandForm(SlugAutoMixin):
    class Meta:
        model = Brand
        fields = ["name", "slug", "logo", "is_featured"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False


class SizeChartForm(forms.ModelForm):
    class Meta:
        model = SizeChart
        fields = ["name", "content_html", "image", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["content_html"].widget.attrs["class"] = "tinymce-editor"
        self.fields["content_html"].widget.attrs["style"] = "visibility: hidden; height: 300px;"


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["moderation_status"]


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["variant_type", "name", "base_price", "mrp", "purchase_price", "sku_suffix", "stock_quantity", "low_stock_threshold", "is_default"]
        widgets = {
            "variant_type": forms.TextInput(attrs={
                "list": "variant-type-list",
                "class": "form-control",
                "placeholder": "e.g. Size, Packaging, Color"
            }),
        }
        error_messages = {
            "variant_type": {"required": "Variant type is required."},
            "name": {"required": "Name is required."},
            "base_price": {"required": "Base price is required."},
            "mrp": {"required": "MRP is required."},
            "purchase_price": {"required": "Purchase price is required."},
            "stock_quantity": {"required": "Stock quantity is required."},
            "low_stock_threshold": {"required": "Low stock threshold is required."},
        }

    REQUIRED_PRICES = (("base_price", "Base price"), ("mrp", "MRP"))
    #fields the "Add variant" template pre-fills with the model defaults
    PREFILLED_DEFAULT_FIELDS = ("stock_quantity", "low_stock_threshold")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if not self.instance.pk:
            for name in [name for name, _label in self.REQUIRED_PRICES] + ["purchase_price"]:
                self.initial[name] = None

    def clean(self):
        cleaned = super().clean()
        for name, label in self.REQUIRED_PRICES:
            value = cleaned.get(name)
            if value is not None and value <= 0:
                self.add_error(name, f"{label} must be greater than 0.")
        return cleaned

    def has_changed(self):
        """
        A row counts as "touched" if any field was submitted with a non-blank
        value — deliberately not deferring to the default has_changed(), which
        compares against the new instance's own field defaults (stock_quantity
        0, low_stock_threshold 5) and so would call an explicitly-filled-in row
        matching those defaults "unchanged", silently dropping it.
        """
        for name, field in self.fields.items():
            if name in ("id", "DELETE", "ORDER") or isinstance(field, InlineForeignKeyField):
                continue
            prefixed_name = self.add_prefix(name)
            val = self.data.get(prefixed_name)
            if val in (None, ""):
                continue
            if (
                not self.instance.pk
                and name in self.PREFILLED_DEFAULT_FIELDS
                and str(val).strip() == str(self.get_initial_for_field(field, name)).strip()
            ):
                continue
            return True
        return False

class ProductVariantInlineFormSet(forms.BaseInlineFormSet):
    """
    Cross-row validation that a single form can't do on its own: dedupe
    variant_type casing within a product, reject SKU-suffix collisions, and
    enforce at most one default variant. Deliberately application-level only
    (no DB constraint/migration) so it can't fail against any duplicate/blank
    data already sitting in production.
    """

    @staticmethod
    def _sku_is_new_or_changed(form, sku: str) -> bool:
        
        saved = (form.instance.sku_suffix or "").strip() if form.instance.pk else None
        return saved is None or saved.lower() != sku.lower()

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        #a product being created is unsaved and has no existing variants to
        #collide with; filtering by it would raise ValueError.
        existing_variants = (
            ProductVariant.objects.filter(product=self.instance)
            if self.instance.pk
            else ProductVariant.objects.none()
        )
        seen_types: dict[str, str] = {}
        seen_skus: dict[str, int] = {}
        default_count = 0
        #the parent product's SKU as submitted (set by the product view; falls
        #back to the saved SKU) - a variant may not reuse its own product's SKU
        product_sku = (getattr(self, "product_sku", None) or self.instance.sku or "").strip()

        for form in self.forms:
            if not getattr(form, "cleaned_data", None) or form.cleaned_data.get("DELETE"):
                continue

            variant_type = (form.cleaned_data.get("variant_type") or "").strip()
            if variant_type:
                key = variant_type.lower()
                canonical = seen_types.get(key)
                if canonical is None:
                    existing = existing_variants.filter(
                        variant_type__iexact=variant_type
                    ).exclude(pk=form.instance.pk).first()
                    canonical = existing.variant_type if existing else variant_type
                    seen_types[key] = canonical
                form.cleaned_data["variant_type"] = canonical
                form.instance.variant_type = canonical

            sku_suffix = (form.cleaned_data.get("sku_suffix") or "").strip()
            if sku_suffix:
                key = sku_suffix.lower()
                if product_sku and key == product_sku.lower():
                    form.add_error(
                        "sku_suffix",
                        f'SKU "{sku_suffix}" is already used as this product\'s SKU. Use a different SKU for the variant.',
                    )
                elif key in seen_skus:
                    form.add_error("sku_suffix", "This SKU suffix is used by another variant in this submission.")
                else:
                    seen_skus[key] = 1
                    conflict = existing_variants.filter(
                        sku_suffix__iexact=sku_suffix
                    ).exclude(pk=form.instance.pk).first()
                    if conflict:
                        form.add_error("sku_suffix", f'SKU suffix "{sku_suffix}" is already used by another variant of this product.')
                    elif self._sku_is_new_or_changed(form, sku_suffix):
                        owner = find_sku_owner(sku_suffix, exclude_product_pk=self.instance.pk)
                        if owner:
                            form.add_error("sku_suffix", f'SKU "{sku_suffix}" is already used by {owner}.')

            if form.cleaned_data.get("is_default"):
                default_count += 1
                if default_count > 1:
                    form.add_error("is_default", "Only one variant can be marked as default.")

ProductVariantFormSet = forms.inlineformset_factory(
    Product,
    ProductVariant,
    form=ProductVariantForm,
    formset=ProductVariantInlineFormSet,
    extra=0,
    can_delete=True,
)

class ProductImageForm(RetainUploadsMixin, forms.ModelForm):
    retained_upload_fields = ("image",)

    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "display_order", "is_primary"]
        error_messages = {
            "image": {"required": "Image file is required."},
            "alt_text": {"required": "Alt text is required."},
            "display_order": {"required": "Display order is required."},
        }

ProductImageFormSet = forms.inlineformset_factory(
    Product,
    ProductImage,
    form=ProductImageForm,
    #no starter blank row: rows appear only for saved items, or when the admin
    #clicks "Add" (same as variants)
    extra=0,
    can_delete=True,
)
class ProductSpecificationForm(forms.ModelForm):
    class Meta:
        model = ProductSpecification
        fields = ["name", "value", "display_order"]
        error_messages = {
            "name": {"required": "Specification name is required."},
            "value": {"required": "Value is required."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["display_order"].required = False
        if not self.instance.pk:
            self.initial["display_order"] = None

    def clean_display_order(self):
        val = self.cleaned_data.get("display_order")
        return val if val is not None else 0


ProductSpecificationFormSet = forms.inlineformset_factory(
    Product,
    ProductSpecification,
    form=ProductSpecificationForm,
    #no starter blank row: rows appear only for saved items, or when the admin
    #clicks "Add" (same as variants)
    extra=0,
    can_delete=True,
)


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = CustomerProfile
        fields = [
            "phone",
            "phone_verified",
            "notify_via_email",
            "notify_via_sms",
            "notify_via_whatsapp",
        ]



class CouponForm(FutureDateRangeMixin, forms.ModelForm):
    date_range_fields = ("valid_from", "valid_until")

    class Meta:
        model = Coupon
        fields = [
            "code",
            "discount_type",
            "discount_value",
            "min_order_value",
            "max_uses",
            "max_uses_per_customer",
            "valid_from",
            "valid_until",
            "applicable_collections",
            "is_active",
        ]
        widgets = {"valid_from": _DATETIME, "valid_until": _DATETIME}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            from django.utils import timezone
            now = timezone.now()
            if self.instance.valid_until and self.instance.valid_until < now:
                self.initial["is_active"] = False

    def clean(self):
        cleaned_data = super().clean()
        valid_until = cleaned_data.get("valid_until")
        is_active = cleaned_data.get("is_active")
        
        from django.utils import timezone
        now = timezone.now()
        
        if valid_until and valid_until < now and is_active:
            cleaned_data["is_active"] = False
            
        return cleaned_data



class FlashSaleForm(FutureDateRangeMixin, forms.ModelForm):
    date_range_fields = ("starts_at", "ends_at")

    class Meta:
        model = FlashSale
        fields = ["name", "products", "discount_percentage", "starts_at", "ends_at", "is_active"]
        widgets = {"starts_at": _DATETIME, "ends_at": _DATETIME}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            from django.utils import timezone
            now = timezone.now()
            if self.instance.ends_at and self.instance.ends_at < now:
                self.initial["is_active"] = False

    def clean(self):
        cleaned_data = super().clean()
        ends_at = cleaned_data.get("ends_at")
        is_active = cleaned_data.get("is_active")
        
        from django.utils import timezone
        now = timezone.now()
        
        if ends_at and ends_at < now and is_active:
            cleaned_data["is_active"] = False
            
        return cleaned_data


class NewsletterSubscriberForm(forms.ModelForm):
    class Meta:
        model = NewsletterSubscriber
        fields = ["email", "is_active"]


class HomepageSectionForm(forms.ModelForm):
    """
    Section content; the position is arranged by drag and drop on the list page.

    """

    BANNER_TYPE = "subscription_banner"
    BANNER_PREFIX = "banner_"
    CARD_IMAGE_MAX_BYTES = 5 * 1024 * 1024
    CARD_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
    MAX_CARDS = 12

    instagram_handle = forms.CharField(
        max_length=30, required=False, label="Instagram username",
        help_text="Without the @, e.g. samruddhi.official. Empty = the Instagram link from Site Settings.",
    )
    reviews_limit = forms.IntegerField(
        min_value=1, max_value=12, required=False, initial=6, label="Number of reviews",
        help_text="How many of the latest approved reviews to show (1-12).",
    )
    newsletter_subtitle = forms.CharField(
        max_length=200, required=False, label="Text",
        help_text="Line under the heading. Empty = default text.",
    )
    newsletter_placeholder = forms.CharField(
        max_length=80, required=False, label="Email box placeholder",
        help_text='Hint shown inside the email box, e.g. "Your email address".',
    )
    featured_brand_ids = forms.ModelMultipleChoiceField(
        queryset=None, required=False, widget=forms.CheckboxSelectMultiple,
        label="Brands to show",
        help_text="Tick the brands to show. Leave all unticked to show every brand marked Featured.",
    )

    class Meta:
        model = HomepageSection
        fields = ["section_type", "title", "is_active", "config"]
        widgets = {"config": forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from catalog.models import Brand
        from cms.homepage_forms import BannerConfigForm, get_section_config_form

        self.fields["config"].required = False
        saved_type = self.instance.section_type if self.instance.pk else ""
        config = (self.instance.config or {}) if self.instance.pk else {}

        #subscription banner fields
        banner_initial = get_section_config_form(
            section_type=self.BANNER_TYPE,
            initial=config if saved_type == self.BANNER_TYPE else {},
        ).initial
        for name, field in BannerConfigForm.base_fields.items():
            field = copy.deepcopy(field)
            field.initial = banner_initial.get(name, "")
            self.fields[self.BANNER_PREFIX + name] = field

        #per-type initial values from the saved config
        if saved_type == "instagram_gallery":
            self.fields["instagram_handle"].initial = config.get("instagram_handle", "")
        if saved_type == "reviews":
            self.fields["reviews_limit"].initial = config.get("limit", 6)
        if saved_type == "newsletter":
            self.fields["newsletter_subtitle"].initial = config.get("subtitle", "")
            self.fields["newsletter_placeholder"].initial = config.get("placeholder", "")
        self.fields["featured_brand_ids"].queryset = Brand.objects.filter(is_featured=True).order_by("name")
        if saved_type == "featured_brands":
            self.fields["featured_brand_ids"].initial = config.get("brand_ids") or []

        self.card_errors: dict[str, list[str]] = {}
        self._pending_card_uploads: dict[str, object] = {}
        self._saved_cards = config.get("cards", []) if saved_type == "marketing_features" else []

    @staticmethod
    def _normalise_media_url(url: str) -> str:
        url = (url or "").strip()
        if url and not url.startswith(("/", "http://", "https://")):
            url = "/" + url  #old configs stored "media/..." without the leading slash
        return url

    def _posted_cards(self) -> list[dict]:
        order = [uid for uid in (self.data.get("cards_order") or "").split(",") if uid.strip()]
        rows = []
        for uid in order[: self.MAX_CARDS + 1]:
            key = f"cards-{uid}-"
            rows.append({
                "uid": uid,
                "title": (self.data.get(key + "title") or "").strip(),
                "url": (self.data.get(key + "url") or "").strip(),
                "image": self._normalise_media_url(self.data.get(key + "image") or ""),
                "file": self.files.get(key + "image_file") if self.files else None,
            })
        return rows

    @property
    def card_rows(self) -> list[dict]:
        """Rows for the template: what was posted (on a validation error) or what is saved."""
        if self.is_bound and self.data.get("section_type") == "marketing_features":
            rows = self._posted_cards()
        else:
            rows = [
                {"uid": str(i), "title": c.get("title", ""), "url": c.get("url", ""),
                 "image": self._normalise_media_url(c.get("image", ""))}
                for i, c in enumerate(self._saved_cards) if isinstance(c, dict)
            ]
        for row in rows:
            row["errors"] = self.card_errors.get(row["uid"], [])
            row.pop("file", None)
        return rows

    def _validate_card_image(self, upload) -> str | None:
        name = (upload.name or "").lower()
        if not name.endswith(self.CARD_IMAGE_EXTENSIONS):
            return "Upload a JPG, PNG, WEBP or GIF image."
        if upload.size > self.CARD_IMAGE_MAX_BYTES:
            return "Image must be 5 MB or smaller."
        try:
            from PIL import Image

            Image.open(upload).verify()
            upload.seek(0)
        except Exception:
            return "This file is not a valid image."
        return None

    def _clean_cards(self) -> list[dict]:
        from cms.homepage_forms import _validate_link

        rows = self._posted_cards()
        if len(rows) > self.MAX_CARDS:
            self.add_error(None, f"You can add at most {self.MAX_CARDS} feature cards.")
            rows = rows[: self.MAX_CARDS]
        cards = []
        for row in rows:
            errors = []
            if not row["title"]:
                errors.append("Title is required.")
            try:
                _validate_link(row["url"])
            except forms.ValidationError as exc:
                errors.extend(exc.messages)
            if row["file"]:
                problem = self._validate_card_image(row["file"])
                if problem:
                    errors.append(problem)
                else:
                    self._pending_card_uploads[row["uid"]] = row["file"]
            elif not row["image"]:
                errors.append("Add an image.")
            if errors:
                self.card_errors[row["uid"]] = errors
            cards.append({"uid": row["uid"], "title": row["title"], "url": row["url"], "image": row["image"]})
        if self.card_errors:
            self.add_error(None, "Please fix the highlighted feature cards.")
        return cards

    # ----- assemble config -----------------------------------------------
    def clean_instagram_handle(self):
        import re

        handle = (self.cleaned_data.get("instagram_handle") or "").strip().lstrip("@")
        if "instagram.com/" in handle:
            handle = handle.rstrip("/").rsplit("/", 1)[-1]
        if handle and not re.fullmatch(r"[A-Za-z0-9._]{1,30}", handle):
            raise forms.ValidationError("Use only letters, numbers, dots and underscores.")
        return handle

    def clean(self):
        cleaned = super().clean()
        section_type = cleaned.get("section_type")
        previous = (self.instance.config or {}) if self.instance.pk else {}

        if section_type == self.BANNER_TYPE:
            from cms.homepage_forms import BannerConfigForm

            config = {
                name: (cleaned.get(self.BANNER_PREFIX + name) or "").strip()
                for name in BannerConfigForm.base_fields
            }
        elif section_type == "marketing_features":
            config = {"cards": self._clean_cards()}
        elif section_type == "instagram_gallery":
            config = {"instagram_handle": cleaned.get("instagram_handle") or ""}
        elif section_type == "reviews":
            config = {"limit": cleaned.get("reviews_limit") or 6}
        elif section_type == "newsletter":
            config = {
                "subtitle": (cleaned.get("newsletter_subtitle") or "").strip(),
                "placeholder": (cleaned.get("newsletter_placeholder") or "").strip(),
            }
        elif section_type == "featured_brands":
            config = {"brand_ids": [b.pk for b in cleaned.get("featured_brand_ids") or []]}
        elif section_type in ("hero_slider", "shop_by_collection", "collection_products"):
            #content comes from Hero Slides / Collections; keep any legacy data untouched
            config = previous if self.instance.pk and self.instance.section_type == section_type else {}
        else:
            config = previous
        cleaned["config"] = config
        return cleaned

    def save(self, commit=True):
        from django.core.files.storage import default_storage
        from django.utils.text import get_valid_filename

        config = self.cleaned_data.get("config") or {}
        if self.cleaned_data.get("section_type") == "marketing_features":
            cards = []
            for card in config.get("cards", []):
                upload = self._pending_card_uploads.get(card.pop("uid", None))
                if upload:
                    stored = default_storage.save(
                        "cms/sections/" + get_valid_filename(upload.name), upload
                    )
                    card["image"] = default_storage.url(stored)
                cards.append(card)
            config = {"cards": cards}
        self.instance.config = config
        if self.instance._state.adding:
            self.instance.display_order = next_homepage_section_order()
        return super().save(commit)


class HeroSlideForm(forms.ModelForm):
    class Meta:
        model = HeroSlide
        fields = ["title", "image", "video", "poster", "display_order", "is_active"]

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image:
            from django.core.files.images import get_image_dimensions
            width, height = get_image_dimensions(image)
            
            # Enforce approximately 2:1 aspect ratio, allowing a small tolerance limit
            aspect_ratio = width / height
            if not (1.95 <= aspect_ratio <= 2.05):
                raise forms.ValidationError(
                    f"Banner image must have approximately a 2:1 aspect ratio. "
                    f"Uploaded image is {width}x{height}."
                )
            
            #enforce a minimum resolution for quality
            if width < 1000:
                raise forms.ValidationError(
                    f"Banner image must be at least 1000px wide for good quality. Uploaded image is {width}px wide."
                )
                
        return image

    def clean_poster(self):
        poster = self.cleaned_data.get("poster")
        if poster:
            from django.core.files.images import get_image_dimensions
            width, height = get_image_dimensions(poster)
            
            if width != height * 2:
                raise forms.ValidationError(
                    f"Poster image must have exactly a 2:1 aspect ratio. Uploaded image is {width}x{height}."
                )
            
            if width < 1200:
                raise forms.ValidationError(
                    f"Poster image must be at least 1200px wide. Uploaded image is {width}px wide."
                )
                
        return poster


class BlogPostForm(SlugAutoMixin):
    class Meta:
        model = BlogPost
        fields = [
            "title",
            "slug",
            "excerpt",
            "body",
            "is_published",
            "publish_at",
            "meta_title",
            "meta_description",
            "og_image",
        ]
        widgets = {"publish_at": _DATETIME}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False


class PageForm(SlugAutoMixin):
    class Meta:
        model = Page
        fields = [
            "title",
            "slug",
            "body",
            "is_published",
            "publish_at",
            "meta_title",
            "meta_description",
            "og_image",
        ]
        widgets = {"publish_at": _DATETIME}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False


class FAQItemForm(forms.ModelForm):
    class Meta:
        model = FAQItem
        fields = ["question", "answer", "display_order", "is_published", "publish_at"]
        widgets = {"publish_at": _DATETIME}


class WhatsAppTemplateForm(forms.ModelForm):
    class Meta:
        model = WhatsAppTemplate
        fields = ["event", "template_id", "body_variables", "button_url_variable", "is_active"]


class PolicyDocumentForm(SlugAutoMixin):
    class Meta:
        model = PolicyDocument
        fields = [
            "title",
            "slug",
            "policy_type",
            "body",
            "is_published",
            "publish_at",
            "meta_title",
            "meta_description",
            "og_image",
        ]
        widgets = {"publish_at": _DATETIME}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False








class SiteSettingsForm(forms.ModelForm):
    default_currency = forms.ModelChoiceField(
        queryset=Currency.objects.all(),
        required=False,
        empty_label="--- Select Default Currency ---",
        help_text="Select the store's default currency."
    )

    field_order = [
        "site_name",
        "tagline",
        "logo",
        "favicon",
        "og_image",
        "contact_phone",
        "address",
        "primary_color",
        "secondary_color",
        "font_family",
        "facebook_url",
        "instagram_url",
        "twitter_url",
        "whatsapp_number",
        "vendor_email",
        "order_notification_email",
        "tax_rate_percent",
        "cod_delivery_charge",
        "default_currency",
        "razorpay_key_id",
        "razorpay_key_secret",
        "meta_pixel_id",
        "meta_capi_access_token",
        "clear_meta_capi_access_token",
        "whatsapp_otp_template_id",
    ]

    clear_meta_capi_access_token = forms.BooleanField(
        required=False,
        label="Remove the saved access token",
    )

    class Meta:
        model = SiteSettings
        fields = [
            "site_name",
            "tagline",
            "logo",
            "favicon",
            "og_image",
            "contact_phone",
            "address",
            "primary_color",
            "secondary_color",
            "font_family",
            "facebook_url",
            "instagram_url",
            "twitter_url",
            "whatsapp_number",
            "vendor_email",
            "order_notification_email",
            "tax_rate_percent",
            "cod_delivery_charge",
            "razorpay_key_id",
            "razorpay_key_secret",
            "meta_pixel_id",
            "meta_capi_access_token",
            "whatsapp_otp_template_id",
        ]
        labels = {
            "vendor_email": "Email",
            "order_notification_email": "New Order Notification Email",
        }
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            #never echo the stored token back into the page source
            "meta_capi_access_token": forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
        }

    def clean_meta_pixel_id(self):
        value = self.cleaned_data.get("meta_pixel_id", "").strip()
        if value and not value.isdigit():
            raise forms.ValidationError("Pixel ID must contain digits only.")
        return value

    def clean(self):
        cleaned = super().clean()
        #runs after every field is cleaned (the clear checkbox is declared after the token).
        #A blank token means "unchanged" — the field is a write-only password input.
        token = (cleaned.get("meta_capi_access_token") or "").strip()
        if cleaned.get("clear_meta_capi_access_token"):
            token = ""
        elif not token:
            token = self.instance.meta_capi_access_token
        cleaned["meta_capi_access_token"] = token
        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.meta_capi_access_token:
            self.fields["meta_capi_access_token"].help_text = (
                "A token is saved. Leave blank to keep it, or enter a new one to replace it."
            )
        default_curr = Currency.objects.filter(is_default=True).first()
        if default_curr:
            self.fields["default_currency"].initial = default_curr.pk
        for field_name, field in self.fields.items():
            if field_name != "logo":
                if "class" in field.widget.attrs:
                    field.widget.attrs["class"] += " form-control"
                else:
                    field.widget.attrs["class"] = "form-control"

    def save(self, commit=True):
        instance = super().save(commit)
        new_default = self.cleaned_data.get("default_currency")
        if new_default:
            Currency.objects.update(is_default=False)
            new_default.is_default = True
            new_default.save()
            from core.selectors import invalidate_default_currency_cache
            invalidate_default_currency_cache()
        return instance


class OrderStatusForm(forms.Form):
    """Free-standing form for applying an order status transition."""

    new_status = forms.ChoiceField(choices=[])
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, allowed_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_status"].choices = allowed_choices or []
