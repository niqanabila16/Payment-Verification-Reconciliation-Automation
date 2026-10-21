"""Role based access control for views."""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def role_required(*roles: str):
    """
    Allow only signed-in users whose role is in `roles`.
    Anonymous users are sent to the sign-in page; other roles get a 403 page.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def cs_permission_required(flag: int):
    """Allow only Customer service accounts that hold the permission `flag` (see accounts.models.CsPerm)."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not request.user.can_cs(flag):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
