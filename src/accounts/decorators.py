from django.contrib.auth.decorators import user_passes_test
from django.conf import settings
from django.http import Http404
from django.http import HttpResponseBase
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from accounts.authentication import resolve_user
from accounts.models import User

P = ParamSpec('P')
R = TypeVar('R')

def shibboleth_support_required(the_func: Callable[P, R]) -> Callable[P, R]:
    """
    Decorator for views that are only meaningful if SHIB_ENABLED is True
    """
    @wraps(the_func)
    def _decorated(*args: P.args, **kwargs: P.kwargs) -> R:
        if settings.SHIB_ENABLED:
            return the_func(*args, **kwargs)
        else:
            raise Http404("Shibboleth support is disabled in this praktomat instance")
    return _decorated


def is_shibboleth_user(user: AbstractBaseUser | AnonymousUser) -> bool:
    user = resolve_user(user)
    return isinstance(user, User) and user.is_shibboleth_user()


def is_local_user(user: AbstractBaseUser | AnonymousUser) -> bool:
    user = resolve_user(user)
    return isinstance(user, User) and not user.is_shibboleth_user()


def shibboleth_user_required(
    login_url: str | None = None,
) -> Callable[[Callable[P, HttpResponseBase]], Callable[P, HttpResponseBase]]:
    """
    Decorator for views that checks that the user is logged in and is a
    shibboleth user.
    """
    return user_passes_test(is_shibboleth_user, login_url=login_url)

def local_user_required(
    func: Callable[P, HttpResponseBase],
) -> Callable[P, HttpResponseBase]:
    """
    Decorator for views that checks that the user is logged in and not a
    shibboleth user.
    """
    decorator = user_passes_test(is_local_user)
    return decorator(func)
