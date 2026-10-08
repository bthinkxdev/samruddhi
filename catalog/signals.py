"""Cache invalidation signals for catalog models."""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from catalog.models import Collection
from catalog.selectors import invalidate_collection_tree_cache


@receiver(post_save, sender=Collection)
@receiver(post_delete, sender=Collection)
def collection_changed(sender, instance: Collection, **kwargs) -> None:
    invalidate_collection_tree_cache()
