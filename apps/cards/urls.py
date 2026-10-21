from django.urls import path

from . import views

app_name = "cards"

urlpatterns = [
    path("", views.dashboard_page, name="dashboard"),
    path("dashboard.json", views.dashboard_data, name="dashboard_data"),
    path("report/", views.report, name="report"),
    path("cs/cards/", views.cs_cards, name="cs_cards"),
    path("cs/cards/upload/", views.cs_upload, name="cs_upload"),
    path("cs/cards/deliver/", views.cs_deliver, name="cs_deliver"),
    path("cs/cards/block/", views.cs_block, name="cs_block"),
    path("cs/activation/", views.cs_requests, name="cs_requests"),
    path("cs/activation/<int:pk>/status/", views.cs_request_status, name="cs_request_status"),
    path("teller/activation/", views.teller_requests, name="teller_requests"),
    path("teller/activation/submit/", views.teller_submit, name="teller_submit"),
    path("teller/activation/suggest/", views.card_suggest, name="card_suggest"),
    path("teller/activation/<int:pk>/resubmit/", views.teller_resubmit, name="teller_resubmit"),
    path("teller/cards/", views.teller_cards, name="teller_cards"),
    path("teller/cards/accept/", views.teller_accept, name="teller_accept"),
    path("file/<int:pk>/", views.request_file, name="request_file"),
]
