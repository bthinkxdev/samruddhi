"""Write operations and business rules for the notifications app."""

from __future__ import annotations

import logging

from django.contrib.auth.models import User

from notifications.models import Notification

logger = logging.getLogger(__name__)


def send_sms(*, phone: str, message: str) -> None:
    """Dispatch an SMS — provider-agnostic stub that logs the payload."""
    logger.info("SMS to %s: %s", phone, message)


def send_email(*, email: str, subject: str, message: str) -> None:
    """Dispatch an email via Django's configured backend (console in dev, SMTP in production)."""
    from django.core.mail import send_mail
    from django.conf import settings
    from core.services import get_site_settings
    
    logger.info("Email to %s [%s]: %s", email, subject, message)
    
    site_settings = get_site_settings()
    if site_settings.site_name:
        from_email = f'"{site_settings.site_name}" <{settings.DEFAULT_FROM_EMAIL}>'
    else:
        from_email = settings.DEFAULT_FROM_EMAIL
    
    send_mail(
        subject=subject,
        message=message,
        from_email=from_email,
        recipient_list=[email],
        fail_silently=False,
    )


def send_whatsapp(*, phone: str, message: str) -> None:
    """Dispatch a WhatsApp message — provider-agnostic stub that logs the payload."""
    logger.info("WhatsApp to %s: %s", phone, message)


def create_notification(*, user: User, title: str, body: str = "") -> Notification:
    """
    Persist an in-app notification for a user.

    Params:
        user: Recipient Django User.
        title: Notification headline.
        body: Optional full message body.
    Returns:
        Created Notification instance.
    """
    return Notification.objects.create(user=user, title=title, body=body)
