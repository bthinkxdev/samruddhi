from django.urls import path
from delhivery.views import delhivery_webhook

app_name = 'delhivery'

urlpatterns = [
    path('webhook/', delhivery_webhook, name='webhook'),
    #Delhivery's integration doesn't reliably send the trailing slash, and a POST
    #redirected by APPEND_SLASH gets replayed as GET by most HTTP clients (curl
    #included), which then 405s against @require_POST. Serve both forms directly
    #instead of relying on the redirect.
    path('webhook', delhivery_webhook, name='webhook-no-slash'),
]
