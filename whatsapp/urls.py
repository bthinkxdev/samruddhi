from django.urls import path

from whatsapp.views import webhook

app_name = "whatsapp"

urlpatterns = [
    path("webhook/", webhook, name="webhook"),
    path("webhook", webhook, name="webhook-no-slash"),
]
