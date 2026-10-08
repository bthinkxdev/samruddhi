"""Cross-app signal handlers for the cms app (side effects only)."""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from cms.models import BlogPost, FAQItem, HomepageSection, Page, PolicyDocument
from cms.tasks import refresh_homepage_cache_task


def _refresh_homepage_cache() -> None:
    from cms.services import refresh_homepage_cache

    refresh_homepage_cache()
    try:
        refresh_homepage_cache_task.delay()
    except Exception:
        pass


@receiver(post_save, sender=HomepageSection)
def homepage_section_saved(sender, instance: HomepageSection, **kwargs) -> None:
    _refresh_homepage_cache()


@receiver(post_delete, sender=HomepageSection)
def homepage_section_deleted(sender, instance: HomepageSection, **kwargs) -> None:
    _refresh_homepage_cache()


for _sender in (BlogPost, Page, FAQItem, PolicyDocument):
    post_save.connect(
        lambda sender, instance, **kwargs: _refresh_homepage_cache(),
        sender=_sender,
    )
    post_delete.connect(
        lambda sender, instance, **kwargs: _refresh_homepage_cache(),
        sender=_sender,
    )
