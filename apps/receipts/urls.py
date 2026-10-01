from django.urls import path

from . import views

app_name = "receipts"

urlpatterns = [
    path("", views.new_receipt, name="new"),
    path("receipts/", views.receipt_list, name="list"),
    path("receipts/<int:pk>/", views.receipt_detail, name="detail"),
    path("receipts/<int:pk>/edit/", views.receipt_edit, name="edit"),
]
