"""WhatsApp template management: maps store events to Gupshup template IDs."""

from __future__ import annotations

from dashboard import forms
from dashboard.views.base import (
    DashboardCreateView,
    DashboardDeleteView,
    DashboardListView,
    DashboardUpdateView,
)
from whatsapp.models import WhatsAppTemplate


class WhatsAppTemplateListView(DashboardListView):
    model = WhatsAppTemplate
    nav_section = "whatsapptemplates"
    url_basename = "whatsapptemplate"
    singular_name = "WhatsApp Template"
    plural_name = "WhatsApp Templates"
    search_fields = ["event", "template_id"]
    columns = [
        {"label": "Event", "name": "get_event_display"},
        {"label": "Template ID", "name": "template_id"},
        {"label": "Active", "name": "is_active", "type": "bool"},
    ]


class WhatsAppTemplateCreateView(DashboardCreateView):
    model = WhatsAppTemplate
    name_object_in_messages = False
    form_class = forms.WhatsAppTemplateForm
    nav_section = "whatsapptemplates"
    url_basename = "whatsapptemplate"
    singular_name = "WhatsApp Template"


class WhatsAppTemplateUpdateView(DashboardUpdateView):
    model = WhatsAppTemplate
    name_object_in_messages = False
    form_class = forms.WhatsAppTemplateForm
    nav_section = "whatsapptemplates"
    url_basename = "whatsapptemplate"
    singular_name = "WhatsApp Template"


class WhatsAppTemplateDeleteView(DashboardDeleteView):
    model = WhatsAppTemplate
    name_object_in_messages = False
    nav_section = "whatsapptemplates"
    url_basename = "whatsapptemplate"
    singular_name = "WhatsApp Template"
