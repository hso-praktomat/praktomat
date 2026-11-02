from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser, User as BasicUser
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from accounts.models import User


def resolve_user(
    user: AbstractBaseUser | AnonymousUser,
) -> AbstractBaseUser | AnonymousUser:
    """Resolve the multi-table user child without treating authentication as proof."""
    if isinstance(user, User) or not isinstance(user, BasicUser):
        return user
    try:
        return User.objects.get(pk=user.pk)
    except User.DoesNotExist:
        return user


def require_user(request: HttpRequest) -> User:
    user = resolve_user(request.user)
    if not isinstance(user, User):
        raise PermissionDenied("A Praktomat user account is required.")
    return user
