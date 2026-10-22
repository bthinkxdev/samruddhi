from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from whatsapp import conf
from whatsapp.exceptions import InvalidPhoneNumber
from whatsapp.models import MessageStatus
from whatsapp.services import send_adhoc_message


class Command(BaseCommand):
    help = "Send a test WhatsApp message through the Gupshup WhatsApp Business API."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--to", required=True, help="Recipient phone (10-digit or international)."
        )
        parser.add_argument("--template", default="", help="Gupshup template ID (UUID).")
        parser.add_argument("--params", default="", help="Comma-separated body parameters.")
        parser.add_argument("--text", default="", help="Send free text instead of a template.")

    def handle(self, *args, **options) -> None:
        if not conf.is_configured():
            raise CommandError(
                "Set GUPSHUP_API_KEY, GUPSHUP_SOURCE_NUMBER and GUPSHUP_APP_NAME in .env first."
            )

        params = [p.strip() for p in options["params"].split(",") if p.strip()]
        try:
            message = send_adhoc_message(
                to=options["to"],
                template_id=options["template"],
                body_params=params,
                text=options["text"],
            )
        except InvalidPhoneNumber as exc:
            raise CommandError(str(exc)) from exc

        if message.status == MessageStatus.SENT:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sent to {message.phone} — provider message id {message.provider_message_id}"
                )
            )
        else:
            raise CommandError(
                f"Not sent ({message.status}): [{message.error_code}] {message.error_message}"
            )
