"""Cache invalidation signals for catalog models."""

from __future__ import annotations

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from catalog.models import Collection, Product
from catalog.selectors import invalidate_collection_tree_cache


@receiver(post_save, sender=Collection)
@receiver(post_delete, sender=Collection)
def collection_changed(sender, instance: Collection, **kwargs) -> None:
    invalidate_collection_tree_cache()


@receiver(post_save, sender=Product)
@receiver(post_delete, sender=Product)
def product_changed(sender, instance: Product, **kwargs) -> None:
    invalidate_collection_tree_cache()


@receiver(m2m_changed, sender=Product.collections.through)
def product_collections_changed(sender, action: str, **kwargs) -> None:
    if action in ("post_add", "post_remove", "post_clear"):
        invalidate_collection_tree_cache()
