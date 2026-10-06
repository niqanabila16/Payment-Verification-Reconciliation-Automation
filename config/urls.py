"""Root URL configuration. Each app owns its own urls.py."""

from django.urls import include, path

handler403 = "apps.core.views.permission_denied"

urlpatterns = [
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("teller/", include("apps.receipts.urls")),
    path("finance/", include("apps.reconciliation.urls")),
    path("__reload__/", include("django_browser_reload.urls")),
]
