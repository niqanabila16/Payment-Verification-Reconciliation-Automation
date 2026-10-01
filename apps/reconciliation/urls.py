from django.urls import path

from . import views

app_name = "reconciliation"

urlpatterns = [
    path("", views.queue, name="queue"),
    path("matches/<int:pk>/", views.detail, name="detail"),
    path("matches/<int:pk>/confirm/", views.confirm, name="confirm"),
    path("matches/<int:pk>/reject/", views.reject, name="reject"),
    path("matches/<int:pk>/feedback/", views.feedback, name="feedback"),
    path("matches/<int:pk>/link/", views.link, name="link"),
    path("matches/<int:pk>/close/", views.close, name="close"),
    path("matches/<int:pk>/reassign/", views.reassign, name="reassign"),
    path("matches/<int:pk>/comment/", views.comment, name="comment"),
    path("imports/", views.import_list, name="import_list"),
    path("imports/<int:pk>/", views.import_detail, name="import_detail"),
    path("imports/<int:pk>/status/", views.import_status, name="import_status"),
    path("rerun/", views.rerun, name="rerun"),
]
