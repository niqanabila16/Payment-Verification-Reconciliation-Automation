from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.SignInView.as_view(), name="login"),
    path("logout/", views.sign_out, name="logout"),
    path("forgot-password/", views.ForgotPasswordView.as_view(), name="forgot_password"),
    path("forgot-password/sent/", views.forgot_password_sent, name="forgot_password_sent"),
    path("forgot-password/resend/", views.forgot_password_resend, name="forgot_password_resend"),
    path("reset/<uidb64>/<token>/", views.NewPasswordView.as_view(), name="password_reset_confirm"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/delete/", views.user_delete, name="user_delete"),
    path("users/<int:pk>/toggle-active/", views.user_toggle_active, name="user_toggle_active"),
    path("users/<int:pk>/reset-password/", views.user_reset_password, name="user_reset_password"),
    path("audit/", views.audit_log, name="audit_log"),
]
