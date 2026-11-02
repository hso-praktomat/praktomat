import datetime
from collections.abc import Mapping
from typing import Any as _Any

from codecs import decode, encode

from django.http import (
    HttpRequest as _HttpRequest,
    HttpResponseBase as _HttpResponseBase,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.template import loader
from django.shortcuts import render, resolve_url
from django.contrib.auth import login
from django.conf import settings
from django.db import transaction

from accounts.models import User
from django.contrib.auth.models import Group
from accounts.decorators import *

from configuration import get_settings

def parse_attributes(
    META: Mapping[str, object],
) -> tuple[dict[str, str | None], bool]:
    shib_attrs: dict[str, str | None] = {}
    error = False
    for header, attr in settings.SHIB_ATTRIBUTE_MAP.items():
        required, name = attr
        values = META.get(header, None)
        value = None
        if values:
            # If multiple attributes releases just care about the 1st one
            if not isinstance(values, str):
                raise TypeError(f"Expected a string Shibboleth header: {header}")
            value = values.split(';')[0]

        if not value or value == '':
            if required:
                error = True
        else:
            value = decode(encode(value,"latin-1"), "utf8")
        shib_attrs[name] = value
    return shib_attrs, error


def render_forbidden(
    request: _HttpRequest, template_name: str, context: dict[str, _Any]
) -> HttpResponseForbidden:
    return HttpResponseForbidden(loader.render_to_string(template_name, context, request))

@shibboleth_support_required
def shib_hello(request: _HttpRequest) -> _HttpResponseBase:
    context: dict[str, object] = {}
    if 'next' in request.GET:
        context['next'] = request.GET['next']
    context['title'] = "Login via shibboleth"
    context['provider'] = settings.SHIB_PROVIDER
    return render(request, 'registration/shib_hello.html', context)

@shibboleth_support_required
@transaction.atomic
def shib_login(request: _HttpRequest) -> _HttpResponseBase:
    attr, error = parse_attributes(request.META)

    was_redirected = False
    if "next" in request.GET:
        was_redirected = True
    redirect_url = request.GET.get('next', resolve_url(settings.LOGIN_REDIRECT_URL))
    context = {'shib_attrs': attr,
               'was_redirected': was_redirected}
    if error:
        return render_forbidden(request, 'registration/shib_error.html', context)
    username = attr.get(settings.SHIB_USERNAME)
    if not username:
        return render_forbidden(request, 'registration/shib_error.html', context)

    mat_number = attr.get('matriculationNumber')
    try:
        number = int(mat_number) if mat_number is not None else None
    except ValueError:
        return render_forbidden(request, 'registration/shib_error.html', context)

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        try:
            if number is not None:
                user = User.objects.get(mat_number=number)
            else:
                raise User.DoesNotExist
        except User.DoesNotExist:
            if get_settings().new_users_via_sso:
                if get_settings().deny_registration_from < datetime.datetime.now():
                    extra_context: dict[str, object] = {}
                    extra_context['deny_registration_from'] = get_settings().deny_registration_from
                    extra_context['admins'] = User.objects.filter(is_superuser=True)
                    extra_context['trainers'] = User.objects.filter(groups=Group.objects.get(name="Trainer"))
                    return render(request, 'registration/registration_form.html', extra_context)
                user = User.objects.create_user(
                    username, '',
                    last_login=datetime.datetime.now())
                user_group = Group.objects.get(name='User')
                user.groups.add(user_group)
                if get_settings().account_manual_validation:
                    user.is_active = False
            else:
                return render_forbidden(request, 'registration/shib_not_allowed.html', context)


    # This needs to be made more general smarter
    user.first_name = attr['first_name']          if attr['first_name'] is not None else user.first_name
    user.last_name = attr['last_name']            if attr['last_name']  is not None else user.last_name
    user.email = attr['email']                    if attr['email']      is not None else user.email
    user.mat_number = number if number is not None else user.mat_number
    user.programme  = attr['programme']           if attr['programme']  is not None else user.programme
    user.save()

    user.backend = settings.AUTH_BACKEND
    login(request, user)

    if not redirect_url or '//' in redirect_url or ' ' in redirect_url:
        redirect_url = settings.LOGIN_REDIRECT_URL

    return HttpResponseRedirect(redirect_url)
