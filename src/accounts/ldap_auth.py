from collections.abc import Callable, Iterable
from importlib import import_module
from typing import TypedDict, TypeVar, cast

import ldap
from ldap.filter import escape_filter_chars
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest

from accounts.models import User
from configuration import get_settings


class LDAPUser(TypedDict):
    dn: str
    uid: str
    mail: str
    firstName: str
    lastName: str
    displayName: str
    personalTitle: str
    uniqueIdentifier: str
    givenName: str
    sn: str
    password_ok: bool


def load_ldap_group_adapters() -> list[Callable[[User], object]]:
    modules: object = getattr(settings, 'LDAP_GROUP_ADAPTERS', ())
    if not isinstance(modules, (list, tuple)):
        raise ImproperlyConfigured("LDAP_GROUP_ADAPTERS must be a list or tuple of module names")
    adapters: list[Callable[[User], object]] = []
    for module_name in cast(Iterable[object], modules):
        if not isinstance(module_name, str):
            raise ImproperlyConfigured("LDAP_GROUP_ADAPTERS entries must be module names")
        module = import_module(f'{module_name}.ldap_group_adapter')
        adapter: object = getattr(module, 'ldap_group_adapter')
        if not callable(adapter):
            raise ImproperlyConfigured(f"LDAP group adapter {module_name} is not callable")
        adapters.append(cast(Callable[[User], object], adapter))
    return adapters


_ldap_group_adapters = load_ldap_group_adapters()


class LDAPBackend:
    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
    ) -> User | None:
        if not username:
            return None
        username = username.lower()
        try:
            localuser = User.objects.get(username=username)
        except User.DoesNotExist:
            localuser = None
        if localuser and localuser.password != 'LDAP_AUTH':
            return None
        ldap_user = fetch_ldapuser_dict(uid=username, password=password)
        if ldap_user is None or not ldap_user['password_ok']:
            return None
        if localuser:
            localuser.email = ldap_user['mail']
            localuser.first_name = _name([ldap_user['firstName'], ldap_user['givenName']])
            localuser.last_name = _name([ldap_user['lastName'], ldap_user['sn']])
            localuser.save()
        else:
            if not get_settings().new_users_via_sso:
                return None
            localuser = create_localuser_from_ldapuser(username, ldap_user)
        for adapter in _ldap_group_adapters:
            adapter(localuser)
        if localuser.groups.count() == 0:
            localuser.groups.add(Group.objects.get(name='User'))
        return localuser

    def get_user(self, user_id: int) -> User | None:
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


Attribute = TypeVar('Attribute', str, bytes)


def _select_attribute(values: Iterable[Attribute]) -> Attribute | None:
    return min((value for value in values if value), key=len, default=None)


def _name(values: Iterable[str]) -> str:
    return _select_attribute(values) or ''


def fetch_ldapuser_dict(uid: str, password: str | None = '') -> LDAPUser | None:
    connection = ldap.initialize(settings.LDAP_URI)
    attributes_requested = [
        'dn', 'mail', 'firstName', 'lastName', 'displayName',
        'personalTitle', 'uniqueIdentifier', 'givenName', 'sn',
    ]
    try:
        results = connection.search_st(
            settings.LDAP_BASE, ldap.SCOPE_SUBTREE,
            'uid=%s' % escape_filter_chars(uid), attributes_requested, timeout=5,
        )
        if len(results) != 1:
            return None
        entry = results[0]
        if entry[0] is None:
            return None
        dn, attributes = entry

        def decoded(name: str) -> str:
            value = _select_attribute(attributes.get(name, []))
            return value.decode('utf-8') if value is not None else ''

        mail = attributes.get('mail', [])
        user: LDAPUser = {
            'dn': dn, 'uid': uid, 'mail': mail[0].decode('utf-8') if mail else '',
            'firstName': decoded('firstName'), 'lastName': decoded('lastName'),
            'displayName': decoded('displayName'), 'personalTitle': decoded('personalTitle'),
            'uniqueIdentifier': decoded('uniqueIdentifier'), 'givenName': decoded('givenName'),
            'sn': decoded('sn'), 'password_ok': False,
        }
        if password:
            try:
                connection.simple_bind_s(dn, password)
                user['password_ok'] = True
            except ldap.INVALID_CREDENTIALS:
                pass
        return user
    finally:
        connection.unbind()


def create_localuser_from_ldapuser(username: str, ldapUser: LDAPUser) -> User:
    try:
        localuser = User.objects.get(username=username)
    except User.DoesNotExist:
        localuser = User.objects.create_user(username=username, password='', email=ldapUser['mail'])
    localuser.password = 'LDAP_AUTH'
    localuser.email = ldapUser['mail']
    localuser.first_name = _name([ldapUser['firstName'], ldapUser['givenName']])
    localuser.last_name = _name([ldapUser['lastName'], ldapUser['sn']])
    localuser.is_staff = False
    localuser.is_superuser = False
    localuser.save()
    return localuser
