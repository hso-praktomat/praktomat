from accounts.authentication import require_user, resolve_user
from configuration import get_settings

from django.contrib.auth import logout
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.middleware import (
    AuthenticationMiddleware as DjangoAuthenticationMiddleware,
    get_user,
    auser,
)
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.functional import SimpleLazyObject
from asgiref.sync import sync_to_async
from functools import partial
from typing import cast


async def application_auser(request: HttpRequest) -> AbstractBaseUser | AnonymousUser:
    user = await sync_to_async(resolve_user)(await auser(request))
    setattr(request, '_acached_user', user)
    return user


class AuthenticationMiddleware(DjangoAuthenticationMiddleware):
    """ Get user subclass insted of baseclass in request.user"""
    def process_request(self, request: HttpRequest) -> None:
        super().process_request(request)
        # Django's lazy proxy delegates to this user but is not its static subtype.
        request.user = cast(
            AbstractBaseUser | AnonymousUser,
            SimpleLazyObject(lambda: resolve_user(get_user(request))),
        )
        request.auser = partial(application_auser, request)

class LogoutInactiveUserMiddleware(MiddlewareMixin):
    """ Logout users who have been set to inactive so they can't use their sessions to operate on the site. """
    def process_request(
        self, request: HttpRequest
    ) -> HttpResponseRedirect | None:
        if not request.user.is_authenticated:
            return
        if not request.user.is_active:
            logout(request)
            return HttpResponseRedirect(reverse('registration_deactivated'))

class DisclaimerAcceptanceMiddleware(MiddlewareMixin):
    """ Make users accept the disclaimer (if required by the settings) before using the site. """
    def process_request(
        self, request: HttpRequest
    ) -> HttpResponseRedirect | None:
        if not request.user.is_authenticated:
            return
        if not get_settings().requires_disclaimer_acceptance:
            return
        user = require_user(request)
        if not user.accepted_disclaimer:
            # prevent infinite redirects or catching logout requests
            if request.path not in {reverse('accept_disclaimer'), reverse('logout')}:
                return HttpResponseRedirect(reverse('accept_disclaimer'))
