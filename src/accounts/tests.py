from utilities.TestSuite import TestCase

from accounts.models import Tutorial, User, validate_mat_number
from django.contrib.auth.models import Group
from django.contrib.auth.models import User as BasicUser
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import serializers
from django.test import RequestFactory, override_settings
from django.http import Http404, HttpRequest, HttpResponse
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import reverse
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import ldap
from accounts.ldap_auth import load_ldap_group_adapters, create_localuser_from_ldapuser, fetch_ldapuser_dict, LDAPBackend, LDAPUser
from asgiref.sync import async_to_sync
from accounts.authentication import require_user, resolve_user
from accounts.decorators import local_user_required, shibboleth_user_required, shibboleth_support_required
from accounts.middleware import AuthenticationMiddleware, DisclaimerAcceptanceMiddleware, LogoutInactiveUserMiddleware
from solutions.models import SolutionFile
from accounts.forms import AdminUserChangeForm, AdminUserCreationForm, MyRegistrationForm
from accounts.shib_views import parse_attributes
from accounts.views import require_uploaded_file
from django import forms


class TestAccountHTTPContracts(TestCase):
    def setUp(self) -> None:
        self.client.force_login(User.objects.get(username='trainer'))

    @override_settings(REGISTRATION_POSSIBLE=False)
    def test_disabled_registration_lists_custom_user_trainers(self) -> None:
        response = self.client.get(reverse('registration_register'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['trainers']), [User.objects.get(username='trainer')])

    def test_uploaded_file_boundary_rejects_non_files(self) -> None:
        upload = SimpleUploadedFile('test.csv', b'12345')
        self.assertIs(require_uploaded_file(upload), upload)
        with self.assertRaisesRegex(TypeError, 'uploaded file'):
            require_uploaded_file([upload])

    def test_csv_assignment_accepts_both_identifier_columns(self) -> None:
        student = User.objects.get(username='user')
        target = Tutorial.objects.create(name='HTTP import tutorial')
        for kind, identifier in (('username', student.username), ('mat_number', str(student.mat_number))):
            with self.subTest(kind=kind):
                response = self.client.post(reverse('admin:import_tutorial_assignment'), {
                    'csv_file': SimpleUploadedFile('assignments.csv', f'{target.name};{identifier}'.encode()),
                    'delimiter': ';', 'quotechar': '|', 'name_column': 0,
                    'user_id_column': 1, 'user_id_type': kind,
                })
                self.assertEqual(response.status_code, 302)
                student.refresh_from_db()
                self.assertEqual(student.tutorial, target)

    def test_user_text_csv_import_and_decode_error(self) -> None:
        response = self.client.post(reverse('admin:import_user_texts'), {
            'csv_file': SimpleUploadedFile('texts.csv', '11111;Grüße'.encode()),
            'delimiter': ';', 'quotechar': '|',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(username='user').user_text, 'Grüße')
        response = self.client.post(reverse('admin:import_user_texts'), {
            'csv_file': SimpleUploadedFile('bad.csv', b'\xff'),
            'delimiter': ';', 'quotechar': '|',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Import failed')

    def test_matriculation_import_creates_string_username(self) -> None:
        group = Group.objects.get(name='User')
        response = self.client.post(reverse('admin:import_matriculation_list', args=[group.pk]), {
            'mat_number_file': SimpleUploadedFile('numbers.csv', b'54321'),
            'create_users': True,
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='54321')
        self.assertEqual(user.mat_number, 54321)
        self.assertIn(group, user.groups.all())

    def test_reactivation_template_uses_django_context(self) -> None:
        user = User.objects.get(username='user')
        with patch('accounts.models.User.import_user', return_value=User.objects.filter(pk=user.pk)):
            with patch('accounts.views.send_mail') as send:
                response = self.client.post(reverse('admin:user_import'), {
                    'file': SimpleUploadedFile('users.xml', b'placeholder'),
                    'require_reactivation': True, 'send_reactivation_email': True,
                    'meassagetext': 'Hello {{ user.username }} at {{ domain }}',
                })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(send.call_args.args[1], 'Hello user at testserver')
        user.refresh_from_db()
        self.assertFalse(user.is_active)


@override_settings(
    SHIB_ENABLED=True, SHIB_USERNAME='username',
    SHIB_ATTRIBUTE_MAP={
        'HTTP_SHIB_USERNAME': (True, 'username'),
        'HTTP_SHIB_EMAIL': (False, 'email'),
        'HTTP_SHIB_FIRST_NAME': (False, 'first_name'),
        'HTTP_SHIB_LAST_NAME': (False, 'last_name'),
        'HTTP_SHIB_MAT_NUMBER': (False, 'matriculationNumber'),
        'HTTP_SHIB_PROGRAMME': (False, 'programme'),
    },
)
class TestShibbolethHTTPContracts(TestCase):
    def test_new_users_keep_manual_validation_and_role_policy(self) -> None:
        from datetime import datetime, timedelta
        for manual in (False, True):
            username = f'http-sso-created-{manual}'
            with self.subTest(manual=manual), patch('accounts.shib_views.get_settings', return_value=SimpleNamespace(
                new_users_via_sso=True,
                deny_registration_from=datetime.now() + timedelta(days=1),
                account_manual_validation=manual,
            )):
                response = self.client.get(reverse('shib_login'), HTTP_SHIB_USERNAME=username, HTTP_SHIB_MAT_NUMBER='54321')
            self.assertEqual(response.status_code, 302)
            user = User.objects.get(username=username)
            self.assertEqual(user.mat_number, 54321)
            self.assertEqual(user.is_active, not manual)
            self.assertTrue(user.groups.filter(name='User').exists())
            self.client.logout()
            user.mat_number = None
            user.save()

    def test_registration_deadline_renders_contacts_without_creating_user(self) -> None:
        from datetime import datetime, timedelta
        with patch('accounts.shib_views.get_settings', return_value=SimpleNamespace(
            new_users_via_sso=True, deny_registration_from=datetime.now() - timedelta(days=1),
        )):
            response = self.client.get(reverse('shib_login'), HTTP_SHIB_USERNAME='too-late-sso')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['trainers']), [User.objects.get(username='trainer')])
        self.assertFalse(User.objects.filter(username='too-late-sso').exists())

    def test_redirect_policy_retains_local_destinations(self) -> None:
        for target, expected in (('/tasks/', '/tasks/'), ('https://example.com/', None), ('//example.com/', None), ('/has space/', None)):
            with self.subTest(target=target):
                response = self.client.get(reverse('shib_login'), {'next': target}, HTTP_SHIB_USERNAME='user')
                if expected is None:
                    from django.conf import settings
                    expected = settings.LOGIN_REDIRECT_URL
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response['Location'], expected)

    def test_attributes_use_first_value_and_decode_wsgi_headers(self) -> None:
        attributes, error = parse_attributes({
            'HTTP_SHIB_USERNAME': 'first;second',
            'HTTP_SHIB_FIRST_NAME': 'Jörg'.encode().decode('latin-1'),
        })
        self.assertFalse(error)
        self.assertEqual(attributes['username'], 'first')
        self.assertEqual(attributes['first_name'], 'Jörg')
        self.assertIsNone(attributes['email'])
        self.assertTrue(parse_attributes({})[1])
        with self.assertRaises(TypeError):
            parse_attributes({'HTTP_SHIB_USERNAME': 123})

    def test_invalid_number_returns_forbidden_without_creating_user(self) -> None:
        response = self.client.get(reverse('shib_login'), HTTP_SHIB_USERNAME='invalid-new-user', HTTP_SHIB_MAT_NUMBER='invalid')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username='invalid-new-user').exists())

    def test_existing_number_resolves_account_and_updates_integer_number(self) -> None:
        response = self.client.get(reverse('shib_login'), HTTP_SHIB_USERNAME='renamed-external-user', HTTP_SHIB_MAT_NUMBER='11111')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), User.objects.get(username='user').pk)
        self.assertFalse(User.objects.filter(username='renamed-external-user').exists())

    def test_database_failure_is_not_treated_as_a_missing_user(self) -> None:
        from django.db import DatabaseError
        with patch('accounts.models.User.objects.get', side_effect=DatabaseError('offline')):
            with self.assertRaisesRegex(DatabaseError, 'offline'):
                self.client.get(reverse('shib_login'), HTTP_SHIB_USERNAME='new-user')

    def test_missing_username_and_disallowed_new_user_are_forbidden(self) -> None:
        self.assertEqual(self.client.get(reverse('shib_login')).status_code, 403)
        with patch('accounts.shib_views.get_settings', return_value=SimpleNamespace(new_users_via_sso=False)):
            response = self.client.get(reverse('shib_login'), HTTP_SHIB_USERNAME='disallowed-user')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username='disallowed-user').exists())


class TestAccountFormContracts(TestCase):
    @staticmethod
    def change_form() -> AdminUserChangeForm:
        class GroupForm(AdminUserChangeForm):
            class Meta(AdminUserChangeForm.Meta):
                fields = '__all__'

        return GroupForm(instance=User.objects.get(username='user'))

    @override_settings(DUMMY_MAT_NUMBERS=False)
    def test_user_group_requires_mat_number_and_removes_invalid_cleaned_value(self) -> None:
        form = self.change_form()
        form.cleaned_data = {'groups': Group.objects.filter(name='User'), 'mat_number': None}
        self.assertIs(form.clean(), form.cleaned_data)
        self.assertTrue(form.has_error('mat_number'))
        self.assertNotIn('mat_number', form.cleaned_data)

    @override_settings(DUMMY_MAT_NUMBERS=False)
    def test_other_group_or_valid_mat_number_needs_no_error(self) -> None:
        for group, number in (('Trainer', None), ('User', 12345)):
            with self.subTest(group=group):
                form = self.change_form()
                form.cleaned_data = {'groups': Group.objects.filter(name=group), 'mat_number': number}
                form.clean()
                self.assertFalse(form.errors)

    @override_settings(DUMMY_MAT_NUMBERS=True)
    def test_dummy_number_setting_allows_missing_mat_number(self) -> None:
        form = self.change_form()
        form.cleaned_data = {'groups': Group.objects.filter(name='User'), 'mat_number': None}
        form.clean()
        self.assertFalse(form.errors)

    def test_missing_groups_has_one_error_even_if_field_validation_already_failed(self) -> None:
        form = self.change_form()
        form.cleaned_data = {'mat_number': None}
        form.clean()
        self.assertEqual(len(form.errors['groups']), 1)
        form.clean()
        self.assertEqual(len(form.errors['groups']), 1)

    @patch('django.contrib.auth.forms.UserChangeForm.clean', return_value=None)
    def test_optional_parent_clean_result_uses_actual_cleaned_data(self, clean: Mock) -> None:
        form = self.change_form()
        form.cleaned_data = {'groups': Group.objects.filter(name='Trainer')}
        self.assertIs(form.clean(), form.cleaned_data)
        self.assertFalse(form.errors)
        clean.assert_called_once()

    def test_invalid_group_value_raises_validation_error(self) -> None:
        form = self.change_form()
        form.cleaned_data = {'groups': ['User']}
        with self.assertRaisesRegex(forms.ValidationError, 'Invalid groups'):
            form.clean()

    @override_settings(DUMMY_MAT_NUMBERS=False)
    def test_bound_admin_form_keeps_field_errors_without_clean_crashing(self) -> None:
        form = AdminUserChangeForm(
            {'username': 'user', 'first_name': 'First', 'last_name': 'Last',
             'email': 'user@example.org', 'groups': ['not-a-pk'], 'mat_number': 'not-a-number'},
            instance=User.objects.get(username='user'),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('groups', form.errors)
        self.assertIn('mat_number', form.errors)
        self.assertEqual(len(form.errors['groups']), 1)
        self.assertNotIn('groups', form.cleaned_data)
        self.assertNotIn('mat_number', form.cleaned_data)

    def test_form_metadata_keeps_existing_fields_and_widgets(self) -> None:
        registration = MyRegistrationForm()
        self.assertEqual(
            list(registration.fields),
            ['username', 'first_name', 'last_name', 'email', 'mat_number', 'password1', 'password2', 'usable_password'],
        )
        creation = AdminUserCreationForm()
        self.assertIn('is_staff', creation.fields)
        self.assertIn('groups', creation.fields)
        self.assertIn('mat_number', creation.fields)
        self.assertIsInstance(AdminUserChangeForm().fields['user_text'].widget, forms.Textarea)

    @patch('accounts.models.User.is_activated', return_value=True)
    def test_duplicate_registration_number_lists_trainers(self, activated: Mock) -> None:
        User.objects.filter(username='user').update(mat_number=12345)
        form = MyRegistrationForm()
        form.cleaned_data = {'mat_number': 12345}
        with self.assertRaises(forms.ValidationError) as error:
            form.clean_mat_number()
        self.assertIn('Please contact a trainer:', str(error.exception))
        trainer = User.objects.get(username='trainer')
        self.assertIn(trainer.email, str(error.exception))
        activated.assert_called()


@override_settings(LDAP_URI='ldap://test.invalid', LDAP_BASE='dc=test')
class TestLDAPBoundary(TestCase):
    @patch('accounts.ldap_auth.ldap.initialize')
    def test_attributes_are_decoded_without_mutating_search_results(self, initialize: Mock) -> None:
        attributes = {
            'mail': [b'user@example.com'], 'givenName': [b'Long name', b'Short'],
            'sn': [b'Name'], 'firstName': [], 'lastName': [],
        }
        connection = initialize.return_value
        connection.search_st.return_value = [('uid=user,dc=test', attributes)]
        result = fetch_ldapuser_dict('user', 'password')
        assert result is not None
        self.assertEqual(result['mail'], 'user@example.com')
        self.assertEqual(result['givenName'], 'Short')
        self.assertEqual(result['firstName'], '')
        self.assertTrue(result['password_ok'])
        self.assertEqual(attributes['mail'], [b'user@example.com'])
        connection.unbind.assert_called_once()

    @patch('accounts.ldap_auth.ldap.initialize')
    def test_missing_or_referral_results_are_not_users(self, initialize: Mock) -> None:
        results: list[list[tuple[str, dict[str, list[bytes]]] | tuple[None, list[str]]]] = [
            [], [(None, ['ldap://referral'])], [('a', {}), ('b', {})],
        ]
        for result in results:
            with self.subTest(result=result):
                connection = initialize.return_value
                connection.reset_mock()
                connection.search_st.return_value = result
                self.assertIsNone(fetch_ldapuser_dict('user'))
                connection.unbind.assert_called_once()

    @patch('accounts.ldap_auth.ldap.initialize')
    def test_only_invalid_credentials_become_authentication_failure(self, initialize: Mock) -> None:
        connection = initialize.return_value
        connection.search_st.return_value = [('uid=user', {})]
        connection.simple_bind_s.side_effect = ldap.INVALID_CREDENTIALS()
        result = fetch_ldapuser_dict('user', 'wrong')
        assert result is not None
        self.assertFalse(result['password_ok'])
        connection.reset_mock()
        connection.simple_bind_s.side_effect = ldap.SERVER_DOWN()
        with self.assertRaises(ldap.SERVER_DOWN):
            fetch_ldapuser_dict('user', 'password')
        connection.unbind.assert_called_once()

    @patch('accounts.ldap_auth.ldap.initialize')
    def test_search_and_decode_errors_still_close_connection(self, initialize: Mock) -> None:
        connection = initialize.return_value
        connection.search_st.side_effect = ldap.SERVER_DOWN()
        with self.assertRaises(ldap.SERVER_DOWN):
            fetch_ldapuser_dict('user')
        connection.unbind.assert_called_once()
        connection.reset_mock()
        connection.search_st.side_effect = None
        connection.search_st.return_value = [('uid=user', {'mail': [b'\xff']})]
        with self.assertRaises(UnicodeDecodeError):
            fetch_ldapuser_dict('user')
        connection.unbind.assert_called_once()

    @patch('accounts.ldap_auth.ldap.initialize')
    def test_filter_values_are_escaped(self, initialize: Mock) -> None:
        initialize.return_value.search_st.return_value = []
        fetch_ldapuser_dict('name*(x)\\')
        self.assertEqual(
            initialize.return_value.search_st.call_args.args[2],
            r'uid=name\2a\28x\29\5c',
        )

    @patch('accounts.ldap_auth.fetch_ldapuser_dict')
    def test_missing_username_does_not_query_directory(self, fetch: Mock) -> None:
        self.assertIsNone(LDAPBackend().authenticate(None, username=None, password='secret'))
        fetch.assert_not_called()

class TestLDAPAccountIntegration(TestCase):
    @staticmethod
    def ldap_user() -> LDAPUser:
        return {
            'dn': 'uid=external,dc=example', 'uid': 'external',
            'mail': 'external@example.org', 'firstName': 'First',
            'lastName': 'Last', 'displayName': 'First Last', 'personalTitle': '',
            'uniqueIdentifier': '123', 'givenName': 'First', 'sn': 'Last',
            'password_ok': True,
        }

    def test_account_creation_retains_ldap_marker_and_no_privileges(self) -> None:
        user = create_localuser_from_ldapuser('external', self.ldap_user())
        self.assertEqual(user.email, 'external@example.org')
        self.assertEqual(user.first_name, 'First')
        self.assertEqual(user.last_name, 'Last')
        self.assertEqual(user.password, 'LDAP_AUTH')
        self.assertFalse(user.check_password('LDAP_AUTH'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    @patch('accounts.ldap_auth.fetch_ldapuser_dict')
    def test_local_password_account_never_uses_ldap(self, fetch: Mock) -> None:
        User.objects.create_user(username='external', password='local-password')
        self.assertIsNone(LDAPBackend().authenticate(None, username='EXTERNAL', password='ldap-password'))
        fetch.assert_not_called()

    @patch('accounts.ldap_auth.fetch_ldapuser_dict')
    def test_existing_account_profile_groups_and_privileges_are_preserved(self, fetch: Mock) -> None:
        user = User.objects.create_user(username='external', password='LDAP_AUTH', first_name='Old', is_staff=True)
        user.password = 'LDAP_AUTH'
        user.save()
        fetch.return_value = self.ldap_user()
        adapter = Mock()
        with patch('accounts.ldap_auth._ldap_group_adapters', [adapter]):
            authenticated = LDAPBackend().authenticate(None, username='EXTERNAL', password='ldap-password')
        self.assertEqual(authenticated, user)
        adapter.assert_called_once_with(user)
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'First')
        self.assertEqual(user.email, 'external@example.org')
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['User'])

    @patch('accounts.ldap_auth.get_settings')
    @patch('accounts.ldap_auth.fetch_ldapuser_dict')
    def test_disabled_creation_and_failed_password_never_create_accounts(self, fetch: Mock, config: Mock) -> None:
        config.return_value.new_users_via_sso = False
        fetch.return_value = self.ldap_user()
        self.assertIsNone(LDAPBackend().authenticate(None, username='external', password='ldap-password'))
        config.return_value.new_users_via_sso = True
        fetch.return_value = dict(self.ldap_user(), password_ok=False)
        self.assertIsNone(LDAPBackend().authenticate(None, username='external', password='bad'))
        self.assertFalse(User.objects.filter(username='external').exists())

    @patch('accounts.views.fetch_ldapuser_dict')
    def test_admin_import_is_all_or_nothing_for_unknown_uids(self, fetch: Mock) -> None:
        self.client.force_login(User.objects.get(username='trainer'))
        fetch.side_effect = [self.ldap_user(), None]
        response = self.client.post(
            reverse('admin:ldap_user_import'), {'uids': 'external missing', 'tutorial': ''},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Unknown UIDs: missing')
        self.assertFalse(User.objects.filter(username='external').exists())
        fetch.side_effect = None
        fetch.return_value = self.ldap_user()
        response = self.client.post(
            reverse('admin:ldap_user_import'), {'uids': 'external', 'tutorial': ''},
        )
        self.assertRedirects(response, reverse('admin:accounts_user_changelist'), fetch_redirect_response=False)
        user = User.objects.get(username='external')
        self.assertEqual(user.email, 'external@example.org')
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['User'])

    @override_settings(LDAP_GROUP_ADAPTERS=['example'])
    @patch('accounts.ldap_auth.import_module')
    def test_configured_group_adapter_is_loaded_and_invalid_adapter_is_visible(self, load: Mock) -> None:
        adapter = Mock()
        load.return_value.ldap_group_adapter = adapter
        self.assertEqual(load_ldap_group_adapters(), [adapter])
        load.assert_called_once_with('example.ldap_group_adapter')
        load.return_value.ldap_group_adapter = None
        with self.assertRaises(ImproperlyConfigured):
            load_ldap_group_adapters()
        load.side_effect = ModuleNotFoundError('missing adapter')
        with self.assertRaises(ModuleNotFoundError):
            load_ldap_group_adapters()


class TestAuthenticationBoundary(TestCase):
    def test_anonymous_domain_views_keep_login_redirects(self) -> None:
        paths = [
            reverse('task_list'),
            reverse('task_detail', args=[1]),
            reverse('solution_list', args=[1]),
            reverse('solution_detail', args=[1]),
            reverse('attestation_list', args=[1]),
            reverse('view_attestation', args=[1]),
            reverse('rating_overview'),
            reverse('upload_test_solution', args=[1]),
        ]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn('next=', response.headers['Location'])

    def test_domain_views_reject_authenticated_base_only_accounts(self) -> None:
        self.client.login(username='trainer', password='demo')
        paths = [
            reverse('task_list'),
            reverse('task_detail', args=[1]),
            reverse('solution_list', args=[1]),
            reverse('solution_detail', args=[1]),
            reverse('attestation_list', args=[1]),
            reverse('view_attestation', args=[1]),
            reverse('rating_overview'),
            reverse('upload_test_solution', args=[1]),
            reverse('admin:task_import'),
            reverse('model_solution', args=[1]),
        ]
        with patch('accounts.authentication.User.objects.get', side_effect=User.DoesNotExist):
            for path in paths:
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 403)

    def test_domain_view_role_permissions_are_preserved(self) -> None:
        cases = [
            (reverse('task_list'), (200, 200, 200)),
            (reverse('task_detail', args=[1]), (200, 200, 200)),
            (reverse('solution_detail', args=[1]), (200, 200, 200)),
            (reverse('attestation_list', args=[1]), (403, 200, 200)),
            (reverse('rating_overview'), (403, 403, 200)),
            (reverse('upload_test_solution', args=[1]), (403, 200, 200)),
            (reverse('upload_test_solution_student', args=[1]), (200, 200, 200)),
        ]
        for index, username in enumerate(('user', 'tutor', 'trainer')):
            self.client.login(username=username, password='demo')
            for path, statuses in cases:
                with self.subTest(username=username, path=path):
                    self.assertEqual(self.client.get(path).status_code, statuses[index])
            self.client.logout()

    def test_disclaimer_submission_requires_custom_user_and_persists(self) -> None:
        path = reverse('accept_disclaimer')
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(
            self.client.post(path, {'accept_disclaimer': True}).status_code, 403
        )
        self.client.login(username='user', password='demo')
        response = self.client.post(path, {'accept_disclaimer': True})
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)
        self.assertTrue(User.objects.get(username='user').accepted_disclaimer)

    @override_settings(MOD_XSENDFILE_V1_0=False)
    def test_stored_solution_file_permissions_are_preserved(self) -> None:
        file = SolutionFile.objects.get(solution__task_id=1)
        path = '/upload/' + str(file.file.name)
        self.assertEqual(self.client.get(path).status_code, 302)
        for username in ('user', 'tutor', 'trainer'):
            self.client.login(username=username, password='demo')
            with self.subTest(username=username):
                self.assertEqual(self.client.get(path).status_code, 200)
            self.client.logout()
        User.objects.create_user('unrelated-user', password='demo')
        self.client.login(username='unrelated-user', password='demo')
        self.assertEqual(self.client.get(path).status_code, 403)
        self.client.logout()
        self.client.login(username='trainer', password='demo')
        with patch('accounts.authentication.User.objects.get', side_effect=User.DoesNotExist):
            self.assertEqual(self.client.get(path).status_code, 403)

    def test_tutor_without_edit_permission_cannot_upload_for_student(self) -> None:
        self.client.login(username='tutor', password='demo')
        student = User.objects.get(username='user')
        with patch('accounts.models.get_settings', return_value=SimpleNamespace(
            tutors_can_edit_solutions=False
        )):
            response = self.client.get(reverse('solution_list', args=[1, student.pk]))
        self.assertEqual(response.status_code, 403)

    def test_authenticated_request_resolves_custom_user(self) -> None:
        self.client.login(username='user', password='demo')
        response = self.client.get(reverse('task_list'))
        user = response.wsgi_request.user
        assert isinstance(user, User)
        self.assertEqual(user.username, 'user')

    def test_authentication_does_not_modify_request_class(self) -> None:
        request = RequestFactory().get('/')
        SessionMiddleware(lambda request: HttpResponse()).process_request(request)
        before = vars(type(request)).get('user')
        AuthenticationMiddleware(lambda request: HttpResponse()).process_request(request)
        self.assertIs(vars(type(request)).get('user'), before)
        self.assertIsInstance(request.user, AnonymousUser)

    def test_authentication_requires_session_middleware(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            AuthenticationMiddleware(lambda request: HttpResponse()).process_request(
                RequestFactory().get('/')
            )

    def test_lazy_user_is_resolved_once_per_request(self) -> None:
        request = RequestFactory().get('/')
        SessionMiddleware(lambda request: HttpResponse()).process_request(request)
        user = User.objects.get(username='user')
        basic_user = BasicUser.objects.get(pk=user.pk)
        with patch('accounts.middleware.get_user', return_value=basic_user) as lookup:
            AuthenticationMiddleware(lambda request: HttpResponse()).process_request(request)
            lookup.assert_not_called()
            with self.assertNumQueries(1):
                self.assertEqual(request.user.pk, user.pk)
                self.assertEqual(request.user.pk, user.pk)
            lookup.assert_called_once_with(request)

    def test_async_user_resolves_custom_user(self) -> None:
        request = RequestFactory().get('/')
        SessionMiddleware(lambda request: HttpResponse()).process_request(request)
        user = User.objects.get(username='user')
        AuthenticationMiddleware(lambda request: HttpResponse()).process_request(request)
        with patch('accounts.middleware.auser', new=AsyncMock(return_value=user)):
            self.assertIs(async_to_sync(request.auser)(), user)

    def test_async_user_reuses_resolved_custom_account(self) -> None:
        self.client.login(username='user', password='demo')
        request = RequestFactory().get('/')
        request.session = self.client.session
        AuthenticationMiddleware(lambda request: HttpResponse()).process_request(request)

        async def fetch_user_twice() -> None:
            first = await request.auser()
            second = await request.auser()
            self.assertIsInstance(first, User)
            self.assertIs(first, second)

        async_to_sync(fetch_user_twice)()

    def test_base_user_without_child_remains_distinct(self) -> None:
        basic_user = BasicUser.objects.get(username='user')
        with patch('accounts.authentication.User.objects.get', side_effect=User.DoesNotExist):
            self.assertIs(resolve_user(basic_user), basic_user)
        self.assertNotIsInstance(basic_user, User)

    def test_unexpected_user_lookup_errors_are_not_swallowed(self) -> None:
        basic_user = BasicUser.objects.get(username='user')
        with patch('accounts.authentication.User.objects.get', side_effect=RuntimeError('lookup failed')):
            with self.assertRaisesRegex(RuntimeError, 'lookup failed'):
                resolve_user(basic_user)

    def test_required_application_user_is_checked(self) -> None:
        request = RequestFactory().get('/')
        user = User.objects.get(username='user')
        request.user = user
        self.assertIs(require_user(request), user)
        request.user = AnonymousUser()
        with self.assertRaises(PermissionDenied):
            require_user(request)
        request.user = BasicUser.objects.get(pk=user.pk)
        self.assertEqual(require_user(request), user)
        with patch('accounts.authentication.User.objects.get', side_effect=User.DoesNotExist):
            with self.assertRaises(PermissionDenied):
                require_user(request)

    def test_inactive_authenticated_user_is_logged_out(self) -> None:
        request = RequestFactory().get('/')
        SessionMiddleware(lambda request: HttpResponse()).process_request(request)
        user = User.objects.get(username='user')
        user.is_active = False
        request.user = user
        response = LogoutInactiveUserMiddleware(lambda request: HttpResponse()).process_request(request)
        assert response is not None
        self.assertEqual(response.url, reverse('registration_deactivated'))
        self.assertIsInstance(request.user, AnonymousUser)

    def test_disclaimer_redirect_and_exempt_paths(self) -> None:
        request = RequestFactory().get('/tasks/')
        request.user = User.objects.get(username='user')
        middleware = DisclaimerAcceptanceMiddleware(lambda request: HttpResponse())
        with patch('accounts.middleware.get_settings', return_value=SimpleNamespace(
            requires_disclaimer_acceptance=True
        )):
            response = middleware.process_request(request)
            assert response is not None
            self.assertEqual(response.url, reverse('accept_disclaimer'))
            for path in (reverse('accept_disclaimer'), reverse('logout')):
                request.path = path
                self.assertIsNone(middleware.process_request(request))
            request.path = '/tasks/'
            request.user.accepted_disclaimer = True
            self.assertIsNone(middleware.process_request(request))

    def test_disclaimer_does_not_treat_base_user_as_custom_user(self) -> None:
        request = RequestFactory().get('/tasks/')
        request.user = BasicUser.objects.get(username='user')
        middleware = DisclaimerAcceptanceMiddleware(lambda request: HttpResponse())
        with patch('accounts.middleware.get_settings', return_value=SimpleNamespace(
            requires_disclaimer_acceptance=True
        )):
            with patch('accounts.authentication.User.objects.get', side_effect=User.DoesNotExist):
                with self.assertRaises(PermissionDenied):
                    middleware.process_request(request)
        request.user = AnonymousUser()
        self.assertIsNone(middleware.process_request(request))

    def test_anonymous_authentication_decorators_redirect(self) -> None:
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse('allowed')
        request = RequestFactory().get('/protected/')
        request.user = AnonymousUser()
        for decorated in (local_user_required(view), shibboleth_user_required()(view)):
            response = decorated(request)
            self.assertEqual(response.status_code, 302)

    def test_local_and_shibboleth_access_are_distinguished(self) -> None:
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse('allowed')
        request = RequestFactory().get('/')
        user = User.objects.get(username='user')
        request.user = user
        self.assertEqual(local_user_required(view)(request).status_code, 200)
        self.assertEqual(shibboleth_user_required()(view)(request).status_code, 302)
        user.set_unusable_password()
        self.assertEqual(local_user_required(view)(request).status_code, 302)
        self.assertEqual(shibboleth_user_required()(view)(request).status_code, 200)
        user.password = 'LDAP_AUTH'
        self.assertEqual(local_user_required(view)(request).status_code, 200)
        self.assertEqual(shibboleth_user_required()(view)(request).status_code, 302)

    @override_settings(SHIB_ENABLED=False)
    def test_disabled_shibboleth_feature_returns_not_found(self) -> None:
        @shibboleth_support_required
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse('allowed')
        with self.assertRaises(Http404):
            view(RequestFactory().get('/'))

    @override_settings(SHIB_ENABLED=True)
    def test_shibboleth_feature_decorator_preserves_view_arguments(self) -> None:
        @shibboleth_support_required
        def view(request: HttpRequest, value: str) -> HttpResponse:
            return HttpResponse(value)
        self.assertEqual(view(RequestFactory().get('/'), 'value').content, b'value')

    @override_settings(
        SHIB_ENABLED=True,
        SHIB_USERNAME='username',
        SHIB_ATTRIBUTE_MAP={
            'HTTP_SHIB_USERNAME': (True, 'username'),
            'HTTP_SHIB_EMAIL': (False, 'email'),
            'HTTP_SHIB_FIRST_NAME': (False, 'first_name'),
            'HTTP_SHIB_LAST_NAME': (False, 'last_name'),
            'HTTP_SHIB_MAT_NUMBER': (False, 'matriculationNumber'),
            'HTTP_SHIB_PROGRAMME': (False, 'programme'),
        },
    )
    def test_shibboleth_login_keeps_custom_user_on_following_request(self) -> None:
        response = self.client.get(
            reverse('shib_login'),
            HTTP_SHIB_USERNAME='user',
            HTTP_SHIB_EMAIL='shib@example.com',
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse('task_list'))
        user = response.wsgi_request.user
        assert isinstance(user, User)
        self.assertEqual(user.username, 'user')
        self.assertEqual(user.email, 'shib@example.com')


class TestModelContracts(TestCase):
    def test_admin_display_metadata_is_preserved(self) -> None:
        for method in (
            User.activation_key_expired, User.is_activated, User.can_activate
        ):
            self.assertIs(getattr(method, 'boolean'), True)
        self.assertEqual(str(getattr(Tutorial.tutors_flat, 'short_description')), 'Tutors')

    def test_user_manager_returns_custom_users(self) -> None:
        user = User.objects.create_user(
            'model-contract-user', 'model-contract@example.com', 'demo'
        )
        self.assertIsInstance(user, User)
        self.assertIsInstance(User.objects.get(pk=user.pk), User)
        self.assertEqual(user.user_ptr.pk, user.pk)
        self.assertEqual(User.objects.model, User)
        self.assertEqual(
            User.objects.deconstruct(),
            (False, 'django.contrib.auth.models.UserManager', None, (), {}),
        )

    def test_base_user_creation_keeps_custom_child(self) -> None:
        basic_user = BasicUser.objects.create_user(
            'base-contract-user', 'base-contract@example.com', 'demo'
        )
        self.assertTrue(User.objects.filter(pk=basic_user.pk).exists())
        user = User.objects.get(pk=basic_user.pk)
        self.assertEqual(user.date_joined, user.user_ptr.date_joined)
        self.assertIsInstance(user.activation_key_expired(), bool)

    def test_tutorial_reverse_relations(self) -> None:
        tutorial = Tutorial.objects.create(name='Model contracts')
        student = User.objects.get(username='user')
        tutor = User.objects.get(username='tutor')
        student.tutorial = tutorial
        student.save()
        tutorial.tutors.add(tutor)
        self.assertEqual(list(tutorial.user_set.all()), [student])
        self.assertIn(tutorial, tutor.tutored_tutorials.all())

    def test_inherited_fields_are_not_replaced(self) -> None:
        for name in ('first_name', 'last_name', 'username'):
            self.assertIs(
                User._meta.get_field(name), BasicUser._meta.get_field(name)
            )
        self.assertEqual(User._meta.ordering, ['first_name', 'last_name'])
        self.assertEqual(User._meta.pk.name, 'user_ptr')

    @override_settings(DUMMY_MAT_NUMBERS=True)
    def test_dummy_mat_number_validator_returns_none(self) -> None:
        self.assertIsNone(validate_mat_number(None))

    @override_settings(DUMMY_MAT_NUMBERS=False)
    def test_mat_number_validator_rejects_invalid_values(self) -> None:
        with patch(
            'accounts.models.get_settings',
            return_value=SimpleNamespace(mat_number_validation_regex=r'\d{5}'),
        ):
            self.assertIsNone(validate_mat_number(12345))
            with self.assertRaises(ValidationError):
                validate_mat_number(123)


class TestLogin(TestCase):
    def test_login(self) -> None:
        response = self.client.get('/accounts/login/')
        self.assertTrue('username' in response.context['form'].fields)
        self.assertTrue('password' in response.context['form'].fields)
        response2 = self.client.post('/accounts/login/',
                           {'username':'user', 'password':'demo'},
                           follow=True)
        self.assertTrue(b'Welcome, user' in response2.content)


class TestUserImport(TestCase):
    def export_source(self) -> str:
        source = User.objects.create_user(
            'import-source', 'import-source@example.com', 'demo'
        )
        source.tutorial = Tutorial.objects.first()
        source.final_grade = 'A'
        source.save()
        return User.export_user(User.objects.filter(pk=source.pk))

    def test_import_xml_string_remaps_parent_and_clears_course_state(self) -> None:
        xml = self.export_source().replace('import-source', 'import-copy')
        imported = User.import_user(xml)
        user = imported.get()
        self.assertEqual(user.username, 'import-copy')
        self.assertEqual(user.email, 'import-copy@example.com')
        self.assertTrue(user.check_password('demo'))
        self.assertIsNone(user.tutorial)
        self.assertIsNone(user.final_grade)
        self.assertEqual(user.user_ptr.pk, user.pk)
        self.assertNotEqual(user.pk, User.objects.get(username='import-source').pk)

    def test_import_uploaded_xml(self) -> None:
        xml = self.export_source().replace('import-source', 'import-upload')
        uploaded = SimpleUploadedFile('users.xml', xml.encode('utf-8'))
        self.client.login(username='trainer', password='demo')
        response = self.client.post(
            reverse('admin:user_import'), {'file': uploaded}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='import-upload').exists())

    def test_import_skips_existing_users_without_breaking_transaction(self) -> None:
        xml = self.export_source()
        self.assertEqual(User.import_user(xml).count(), 0)
        self.assertEqual(User.objects.filter(username='import-source').count(), 1)

    def test_import_rejects_other_models_and_rolls_back(self) -> None:
        xml = self.export_source().replace('import-source', 'import-rollback')
        tutorial_xml = serializers.serialize('xml', Tutorial.objects.all())
        combined = xml.replace(
            '</django-objects>',
            tutorial_xml.split('>', 2)[2],
        )
        with self.assertRaises(ValidationError):
            User.import_user(combined)
        self.assertFalse(User.objects.filter(username='import-rollback').exists())


class TestViews(TestCase):
    def setUp(self) -> None:
        self.client.login(username='trainer', password='demo')
        self.testgroup: Group = Group(name = 'test')
        self.testgroup.save()

    def test_get_testgroup(self) -> None:
        response = self.client.get(reverse('admin:auth_group_change', args=[self.testgroup.pk]))
        self.assertEqual(response.status_code, 200)

    def test_testgroup_empty(self) -> None:
        self.assertFalse(User.objects.filter(groups=self.testgroup).exists())

    def test_testgroup_add_user(self) -> None:
        # mostly to test the testing
        user = User.objects.get(username = 'user')
        user.groups.add(self.testgroup)
        user.save()
        self.assertEqual(set( u.mat_number for u in User.objects.filter(groups = self.testgroup)),
                             set( u.mat_number for u in [user]))

    def test_testgroup_add_to_group(self) -> None:
        user = User.objects.get(username = 'user')

        user2 = User.objects.create_user('user2', 'user@praktomat.com', 'demo')
        user2.mat_number = 22222
        user2.groups.add(self.testgroup)
        user2.save()

        f = StringIO("11111\n33333")
        f.name="foo.txt"
        response = self.client.post(
            reverse('admin:import_matriculation_list', args=[self.testgroup.pk]),
            { 'mat_number_file': f,
              'remove_others' : False,
              'create_users': False},
            follow=True)
        self.assertContains(response, "1 users added to group test, 0 removed, 0 already in group. 0 new users created.")
        self.assertEqual(set( u.mat_number for u in User.objects.filter(groups = self.testgroup)),
                             set( u.mat_number for u in [user, user2]))

    def test_testgroup_set_group_without_creating_users(self) -> None:
        user = User.objects.get(username = 'user')

        user2 = User.objects.create_user('user2', 'user@praktomat.com', 'demo')
        user2.mat_number = 22222
        user2.groups.add(self.testgroup)
        user2.save()

        f = StringIO("11111\n33333")
        f.name="foo.txt"
        response = self.client.post(
            reverse('admin:import_matriculation_list', args=[self.testgroup.pk]),
            { 'mat_number_file': f,
              'remove_others' : True,
              'create_users': False},
            follow=True)
        self.assertContains(response, "1 users added to group test, 1 removed, 0 already in group. 0 new users created.")
        self.assertEqual(set( u.mat_number for u in User.objects.filter(groups = self.testgroup)),
                             set( u.mat_number for u in [user]))

    def test_testgroup_set_group_with_new_users(self) -> None:
        # mostly to test the testing
        user = User.objects.get(username = 'user')

        user2 = User.objects.create_user('user2', 'user@praktomat.com', 'demo')
        user2.mat_number = 22222
        user2.groups.add(self.testgroup)
        user2.save()

        f = StringIO("11111\n33333")
        f.name="foo.txt"
        response = self.client.post(
            reverse('admin:import_matriculation_list', args=[self.testgroup.pk]),
            { 'mat_number_file': f,
              'remove_others' : True,
              'create_users': True},
            follow=True)
        self.assertContains(response, "2 users added to group test, 1 removed, 0 already in group. 1 new users created.")

        user3 = User.objects.get(mat_number = 33333)

        self.assertEqual(set( u.mat_number for u in User.objects.filter(groups = self.testgroup)),
                             set( u.mat_number for u in [user, user3]))
