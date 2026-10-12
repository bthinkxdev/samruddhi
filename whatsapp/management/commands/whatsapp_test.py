from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from whatsapp import conf
from whatsapp.exceptions import InvalidPhoneNumber
from whatsapp.models import MessageStatus
from whatsapp.services import send_adhoc_message


class Command(BaseCommand):
    help = "Send a test WhatsApp message through the Meta Cloud API."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--to", required=True, help="Recipient phone (10-digit or international)."
        )
        parser.add_argument("--template", default="hello_world")
        parser.add_argument("--lang", default="en_US")
        parser.add_argument("--params", default="", help="Comma-separated body parameters.")
        parser.add_argument("--text", default="", help="Send free text instead of a template.")

    def handle(self, *args, **options) -> None:
        if not conf.is_configured():
            raise CommandError(
                "Set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID in .env first."
            )

        params = [p.strip() for p in options["params"].split(",") if p.strip()]
        try:
            message = send_adhoc_message(
                to=options["to"],
                template_name=options["template"],
                language_code=options["lang"],
                body_params=params,
                text=options["text"],
            )
        except InvalidPhoneNumber as exc:
            raise CommandError(str(exc)) from exc

        if message.status == MessageStatus.SENT:
            self.stdout.write(
                self.style.SUCCESS(f"Sent to {message.phone} — wamid {message.wamid}")
            )
        else:
            raise CommandError(
                f"Not sent ({message.status}): [{message.error_code}] {message.error_message}"
            )
