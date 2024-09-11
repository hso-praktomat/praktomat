from django.urls import *
from django.views.generic.base import TemplateView

from django.conf import settings   # for switching via ACCOUNT_CHANGE_POSSIBLE

import accounts.shib_views
import accounts.views

# Uncomment the next two lines to enable the admin:
from django.contrib import admin

# for some reason include('django.contrib.auth.urls') wouldn't work with {% url ... %} aka reverse()
from django.contrib.auth import views as auth_views

# TODO check if URLS are working after solving merge conflicts
urlpatterns = [
    re_path(r'^shib_login/$', accounts.shib_views.shib_login, name='shib_login'),
    re_path(r'^shib_hello/$', accounts.shib_views.shib_hello, name='shib_hello'),
    re_path(r'^login/$', auth_views.LoginView.as_view(), {'template_name': 'registration/login.html'}, name='login'),
    re_path(r'^logout/$', auth_views.logout_then_login, name='logout'),
    #re_path(r'^change/$', accounts.views.change, name='registration_change'),
    re_path(r'^view/$', accounts.views.view, name='registration_view'),
    #re_path(r'^password/change/$', auth_views.PasswordChangeView.as_view(), name='password_change'),
    #re_path(r'^password/change/done/$', auth_views.PasswordChangeDoneView.as_view(), name='password_change_done'),
    #re_path(r'^password/reset/$', auth_views.PasswordResetView.as_view(), name='password_reset'),
    re_path(r'^accept_disclaimer/$', accounts.views.accept_disclaimer, name='accept_disclaimer'),
]
if settings.ACCOUNT_CHANGE_POSSIBLE:
    urlpatterns += [
        re_path(r'^change/$', accounts.views.change, name='registration_change'),
        re_path(r'^password/change/$', auth_views.PasswordChangeView.as_view(), name='password_change'),
        re_path(r'^password/change/done/$', auth_views.PasswordChangeDoneView.as_view(), name='password_change_done'),
        re_path(r'^password/reset/$', auth_views.PasswordResetView.as_view(), name='password_reset'),
        re_path(r'^password/reset/confirm/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
            auth_views.PasswordResetConfirmView.as_view(),
            name='password_reset_confirm'),
        re_path(r'^password/reset/complete/$', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
        re_path(r'^password/reset/done/$', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
        re_path(r'^register/$', accounts.views.register, name='registration_register'),
        re_path(r'^register/complete/$', TemplateView.as_view(template_name='registration/registration_complete.html'), name='registration_complete'),
        re_path(r'^register/allow/(?P<user_id>\d+)/$', accounts.views.activation_allow, name='activation_allow'),
        re_path(r'^activate/(?P<activation_key>.+)/$', accounts.views.activate, name='registration_activate'),
        re_path(r'^deactivated/$', accounts.views.deactivated, name='registration_deactivated'),
    ]
