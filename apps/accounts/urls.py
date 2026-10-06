from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.SignInView.as_view(), name="login"),
    path("logout/", views.sign_out, name="logout"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/toggle-active/", views.user_toggle_active, name="user_toggle_active"),
    path("users/<int:pk>/reset-password/", views.user_reset_password, name="user_reset_password"),
    path("audit/", views.audit_log, name="audit_log"),
]
