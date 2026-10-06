from django.urls import path

from . import views

app_name = "reconciliation"

urlpatterns = [
    path("", views.queue, name="queue"),
    path("matches/<int:pk>/", views.detail, name="detail"),
    path("matches/<int:pk>/confirm/", views.confirm, name="confirm"),
    path("matches/<int:pk>/reject/", views.reject, name="reject"),
    path("matches/<int:pk>/feedback/", views.feedback, name="feedback"),
    path("matches/<int:pk>/reassign/", views.reassign, name="reassign"),
    path("uploads/", views.import_list, name="import_list"),
    path("uploads/<int:pk>/", views.import_detail, name="import_detail"),
    path("uploads/<int:pk>/status/", views.import_status, name="import_status"),
]
