import django.core.validators
from django.db import migrations, models

#old flag -> (label name, slug, badge colour, order)
FLAG_LABELS = {
    "is_bestseller": ("Bestseller", "bestseller", "#B45309", 1),
    "is_new_arrival": ("New Arrival", "new-arrival", "#0F766E", 2),
    "is_featured": ("Featured", "featured", "#111827", 3),
}


def flags_to_labels(apps, schema_editor):
    """Turn each product flag that is in use into a label assigned to those products."""
    Product = apps.get_model("catalog", "Product")
    Label = apps.get_model("catalog", "Label")
    Membership = Product.labels.through

    for flag, (name, slug, colour, order) in FLAG_LABELS.items():
        product_ids = list(Product.objects.filter(**{flag: True}).values_list("pk", flat=True))
        if not product_ids:
            continue
        label = Label.objects.create(
            name=name, slug=slug, background_color=colour, display_order=order
        )
        Membership.objects.bulk_create(
            [Membership(product_id=pk, label_id=label.pk) for pk in product_ids]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0026_collections"),
    ]

    operations = [
        migrations.CreateModel(
            name="Label",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text="Timestamp when this record was first created.",
                        verbose_name="Created at",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        db_index=True,
                        help_text="Timestamp when this record was last modified.",
                        verbose_name="Updated at",
                    ),
                ),
                (
                    "name",
                    models.CharField(help_text="Text shown on the badge.", max_length=40, verbose_name="Name"),
                ),
                (
                    "slug",
                    models.SlugField(
                        help_text="Used in shop filter links, e.g. /shop/?label=bestseller.",
                        max_length=50,
                        unique=True,
                        verbose_name="Slug",
                    ),
                ),
                (
                    "background_color",
                    models.CharField(
                        default="#111827",
                        max_length=7,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^#[0-9A-Fa-f]{6}$", "Enter a hex colour such as #1A2B3C."
                            )
                        ],
                        verbose_name="Badge colour",
                    ),
                ),
                (
                    "text_color",
                    models.CharField(
                        default="#FFFFFF",
                        max_length=7,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^#[0-9A-Fa-f]{6}$", "Enter a hex colour such as #1A2B3C."
                            )
                        ],
                        verbose_name="Text colour",
                    ),
                ),
                (
                    "display_order",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Lower values appear first when a product has several labels.",
                        verbose_name="Display order",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        help_text="Inactive labels are hidden from the storefront but stay assigned.",
                        verbose_name="Is active",
                    ),
                ),
            ],
            options={
                "verbose_name": "Label",
                "verbose_name_plural": "Labels",
                "ordering": ["display_order", "name"],
            },
        ),
        migrations.AddField(
            model_name="product",
            name="labels",
            field=models.ManyToManyField(
                blank=True, related_name="products", to="catalog.label", verbose_name="Labels"
            ),
        ),
        migrations.RunPython(flags_to_labels, migrations.RunPython.noop),
        migrations.RemoveIndex(model_name="product", name="cat_prod_active_bestseller_idx"),
        migrations.RemoveIndex(model_name="product", name="cat_prod_active_new_idx"),
        migrations.RemoveIndex(model_name="product", name="cat_prod_featured_idx"),
        migrations.RemoveField(model_name="product", name="is_bestseller"),
        migrations.RemoveField(model_name="product", name="is_featured"),
        migrations.RemoveField(model_name="product", name="is_new_arrival"),
    ]
