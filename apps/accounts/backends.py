"""Authentication backend."""
from django.contrib.auth.backends import ModelBackend


class ActiveAwareBackend(ModelBackend):
    """
    - authenticate(): lets deactivated users reach the form validation so they see the helpful message
      "This account has been deactivated" (only shown after the CORRECT password, so it reveals nothing to outsiders).
    - get_user(): rejects deactivated users on every request, so deactivating an account ends its
      existing sessions immediately.
    """

    def user_can_authenticate(self, user):
        return True

    def get_user(self, user_id):
        user = super().get_user(user_id)
        return user if user is not None and user.is_active else None
