from django.urls import path

from . import master, views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home_redirect"),
    path("notifications/", views.notification_list, name="notifications"),
    path("notifications/poll/", views.notification_poll, name="notification_poll"),
    path("manage/master-data/<slug:kind>/", master.master_list, name="master_list"),
    path("manage/master-data/<slug:kind>/<int:pk>/edit/", master.master_edit, name="master_edit"),
    path("manage/master-data/<slug:kind>/<int:pk>/toggle/", master.master_toggle, name="master_toggle"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("healthz/", views.healthz, name="healthz"),
]
