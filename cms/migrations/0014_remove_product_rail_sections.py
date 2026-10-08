from django.core.cache import cache
from django.db import migrations, models

from cms.selectors import HOMEPAGE_SECTIONS_CACHE_KEY

REMOVED_TYPES = ["featured_products", "new_arrivals", "best_sellers"]


def delete_rail_sections(apps, schema_editor):
    """The flag-driven product rails are gone; the home page lists collections instead."""
    HomepageSection = apps.get_model("cms", "HomepageSection")
    HomepageSection.objects.filter(section_type__in=REMOVED_TYPES).delete()
    #bulk deletes fire no signals; drop the cached snapshot so removed sections are not served
    try:
        cache.delete(HOMEPAGE_SECTIONS_CACHE_KEY)
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0013_collection_sections"),
    ]

    operations = [
        migrations.RunPython(delete_rail_sections, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="homepagesection",
            name="section_type",
            field=models.CharField(
                choices=[
                    ("hero_slider", "Hero Slider"),
                    ("shop_by_collection", "Shop by Collection"),
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
    ]
