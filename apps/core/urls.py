from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home_redirect"),
    path("architecture/", views.architecture, name="architecture"),
    path("notifications/", views.notification_list, name="notifications"),
    path("notifications/poll/", views.notification_poll, name="notification_poll"),
    path("notifications/<int:pk>/read/", views.notification_read, name="notification_read"),
    path("notifications/read-all/", views.notification_read_all, name="notification_read_all"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("healthz/", views.healthz, name="healthz"),
]
