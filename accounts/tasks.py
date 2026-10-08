"""Celery tasks for the accounts app."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="accounts.tasks.send_otp_sms")
def send_otp_sms(*, phone: str, otp_code: str) -> None:
    """Dispatch OTP SMS via the notifications app's send_sms service."""
    from core.services import get_site_settings
    from notifications.tasks import dispatch_sms

    site_name = get_site_settings().site_name
    dispatch_sms.delay(phone=phone, message=f"Your {site_name} verification code is: {otp_code}")


