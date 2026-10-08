import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def link_products_to_collections(apps, schema_editor):
    """Each product keeps its single former grouping as a collection membership."""
    Product = apps.get_model("catalog", "Product")
    Membership = Product.collections.through
    Membership.objects.bulk_create(
        [
            Membership(product_id=product_id, collection_id=collection_id)
            for product_id, collection_id in Product.objects.values_list("pk", "category_id")
        ]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0025_productvariant_is_default"),
        #marketing must have created its coupon link to the old model before the rename
        ("marketing", "0004_delete_giftcard"),
    ]

    operations = [
        migrations.RenameModel(old_name="Category", new_name="Collection"),
        migrations.RemoveIndex(model_name="collection", name="cat_category_is_active_idx"),
        migrations.RemoveField(model_name="collection", name="og_image"),
        migrations.AlterModelOptions(
            name="collection",
            options={
                "ordering": ["display_order", "name"],
                "verbose_name": "Collection",
                "verbose_name_plural": "Collections",
            },
        ),
        migrations.AlterField(
            model_name="collection",
            name="name",
            field=models.CharField(
                help_text="Display name of the collection.", max_length=120, verbose_name="Name"
            ),
        ),
        migrations.AlterField(
            model_name="collection",
            name="slug",
            field=models.SlugField(
                help_text="URL-friendly collection identifier.",
                max_length=120,
                unique=True,
                verbose_name="Slug",
            ),
        ),
        migrations.AlterField(
            model_name="collection",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                help_text="Parent node in the collection tree; empty for top-level.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="children",
                to="catalog.collection",
                verbose_name="Parent collection",
            ),
        ),
        migrations.AlterField(
            model_name="collection",
            name="is_active",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text="When False, the collection is hidden from the storefront.",
                verbose_name="Is active",
            ),
        ),
        migrations.AddField(
            model_name="collection",
            name="description",
            field=models.TextField(
                blank=True,
                help_text="Shown on the collection page and used as the SEO description fallback.",
                verbose_name="Description",
            ),
        ),
        migrations.AddField(
            model_name="collection",
            name="image",
            field=models.ImageField(
                default="",
                help_text="Square-ish thumbnail shown in collection rails and navigation.",
                upload_to="collections/images/",
                verbose_name="Image",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="collection",
            name="banner_image",
            field=models.ImageField(
                default="",
                help_text="Wide banner shown at the top of the collection page and used for social sharing.",
                upload_to="collections/banners/",
                verbose_name="Banner image",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="collection",
            name="show_on_homepage",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Show this collection as a product grid in the home page collection section.",
                verbose_name="List on home page",
            ),
        ),
        migrations.AddField(
            model_name="collection",
            name="homepage_product_limit",
            field=models.PositiveSmallIntegerField(
                default=8,
                help_text="How many products of this collection to list on the home page.",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(48),
                ],
                verbose_name="Products on home page",
            ),
        ),
        migrations.AddIndex(
            model_name="collection",
            index=models.Index(fields=["is_active"], name="cat_collection_is_active_idx"),
        ),
        migrations.AddField(
            model_name="product",
            name="collections",
            field=models.ManyToManyField(
                blank=True,
                related_name="products",
                to="catalog.collection",
                verbose_name="Collections",
            ),
        ),
        migrations.RunPython(link_products_to_collections, migrations.RunPython.noop),
        migrations.RemoveIndex(model_name="product", name="cat_prod_active_category_idx"),
        migrations.RemoveField(model_name="product", name="category"),
    ]
