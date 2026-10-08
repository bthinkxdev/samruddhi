"""Write operations and business rules for the catalog app."""

from __future__ import annotations

from typing import Union

from django.contrib.auth.models import User
from django.db import transaction

from accounts.models import CustomerProfile
from catalog.exceptions import InsufficientStockError
from catalog.models import (
    ModerationStatus,
    Product,
    ProductVariant,
    Review,
)


@transaction.atomic
def adjust_stock(
    *,
    target: Union[Product, ProductVariant],
    delta: int,
    reason: str,
) -> Union[Product, ProductVariant]:
    """
    Atomically adjust stock using select_for_update to prevent race conditions.

    Params:
        target: Product or ProductVariant instance to adjust.
        delta: Positive or negative integer change.
        reason: Audit reason string (logged in Phase 4 inventory module).
    Returns:
        Updated target instance.
    Raises:
        InsufficientStockError: When adjustment would make stock negative.
    """
    if isinstance(target, Product):
        locked = Product.objects.select_for_update().get(pk=target.pk)
        new_quantity = locked.stock_quantity + delta
        if new_quantity < 0:
            raise InsufficientStockError(f"Insufficient stock for product {locked.sku}: {reason}")
        locked.stock_quantity = new_quantity
        locked.save(update_fields=["stock_quantity", "updated_at"])
        return locked

    locked = ProductVariant.objects.select_for_update().get(pk=target.pk)
    new_quantity = locked.stock_quantity + delta
    if new_quantity < 0:
        raise InsufficientStockError(f"Insufficient stock for variant {locked}: {reason}")
    locked.stock_quantity = new_quantity
    locked.save(update_fields=["stock_quantity", "updated_at"])
    return locked


@transaction.atomic
def submit_review(
    *,
    product: Product,
    customer: CustomerProfile,
    rating: int,
    title: str,
    body: str,
    is_verified_purchase: bool = False,
) -> Review:
    """
    Create a review in PENDING moderation state and notify admins via Celery.

    Params:
        product: Reviewed product.
        customer: Author customer profile.
        rating: Star rating 1–5.
        title: Review headline.
        body: Review body text.
        is_verified_purchase: Whether the customer bought this product.
    Returns:
        Created Review in PENDING status.
    """
    from catalog.tasks import notify_review_moderation

    review = Review.objects.create(
        product=product,
        customer=customer,
        rating=rating,
        title=title,
        body=body,
        is_verified_purchase=is_verified_purchase,
        moderation_status=ModerationStatus.PENDING,
    )
    notify_review_moderation.delay(review_id=review.pk)
    return review


@transaction.atomic
def moderate_review(
    *,
    review_id: int,
    decision: str,
    moderator: User,
) -> Review:
    """
    Transition a review's moderation_status to APPROVED or REJECTED.

    Params:
        review_id: Primary key of the review.
        decision: ModerationStatus value (approved or rejected).
        moderator: Admin user performing moderation.
    Returns:
        Updated Review instance.
    """
    if decision not in (ModerationStatus.APPROVED, ModerationStatus.REJECTED):
        raise ValueError(f"Invalid moderation decision: {decision}")

    review = Review.objects.select_for_update().get(pk=review_id)
    review.moderation_status = decision
    review.moderated_by = moderator
    review.save(update_fields=["moderation_status", "moderated_by", "updated_at"])
    
    #dismiss the notification for all admins
    from notifications.models import Notification
    body_text = f'Review "{review.title}" on {review.product.name} awaits approval.'
    Notification.objects.filter(
        title="Review pending moderation", 
        body=body_text,
        is_read=False
    ).update(is_read=True)

    return review
