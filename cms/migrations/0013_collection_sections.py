from django.core.cache import cache
from django.db import migrations, models

from cms.selectors import HOMEPAGE_SECTIONS_CACHE_KEY

SECTION_TYPE_RENAMES = {
    "shop_by_category": "shop_by_collection",
    "category_products": "collection_products",
}


def convert_sections(apps, schema_editor):
    """
    Rename the section types and keep the home page looking the same.

    The old product-grid section showed every top-level category (or the slugs in
    its config); those collections are now flagged "List on home page" instead.
    """
    HomepageSection = apps.get_model("cms", "HomepageSection")
    Collection = apps.get_model("catalog", "Collection")

    for section in HomepageSection.objects.filter(section_type="category_products"):
        wanted = section.config.get("category_slug", "all")
        roots = Collection.objects.filter(is_active=True, parent__isnull=True)
        if wanted != "all":
            slugs = wanted.split(",") if isinstance(wanted, str) else wanted
            roots = Collection.objects.filter(is_active=True, slug__in=[s.strip() for s in slugs])
        roots.update(show_on_homepage=True)
        section.config = {}
        section.save(update_fields=["config"])

    for old, new in SECTION_TYPE_RENAMES.items():
        HomepageSection.objects.filter(section_type=old).update(section_type=new)

    #bulk updates fire no signals; drop the cached snapshot so old type names are not served
    try:
        cache.delete(HOMEPAGE_SECTIONS_CACHE_KEY)
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0026_collections"),
        ("cms", "0012_alter_homepagesection_section_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="homepagesection",
            name="section_type",
            field=models.CharField(
                choices=[
                    ("hero_slider", "Hero Slider"),
                    ("shop_by_collection", "Shop by Collection"),
                    ("featured_products", "Featured Products"),
                    ("new_arrivals", "New Arrivals"),
                    ("best_sellers", "Best Sellers"),
                    ("featured_brands", "Featured Brands"),
                    ("subscription_banner", "Subscription Banner"),
                    ("marketing_features", "Marketing Feature Cards"),
                    ("reviews", "Reviews"),
                    ("instagram_gallery", "Instagram Gallery"),
                    ("newsletter", "Newsletter"),
                    ("collection_products", "Collection Product Grids"),
                ],
                db_index=True,
                max_length=40,
                verbose_name="Section type",
            ),
        ),
        migrations.RunPython(convert_sections, migrations.RunPython.noop),
    ]
