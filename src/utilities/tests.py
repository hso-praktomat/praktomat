import os
import subprocess
import tempfile
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from django.core.files.base import ContentFile
from django.http import Http404, HttpResponse
from django.test import RequestFactory

from settings.defaults import load_defaults
from utilities.safeexec import ExecutionResult, execute_arglist, safe_docker, safe_docker_cleanup
from utilities.file_operations import (
    InvalidZipFile, create_tempfolder, require_file_name, unpack_zipfile_to,
)
from utilities.views import sendfile, forbidden


class TestHTTPFileResponses(SimpleTestCase):
    def test_xsendfile_headers_preserve_mime_length_and_unicode_paths(self) -> None:
        with TemporaryDirectory() as root, override_settings(UPLOAD_ROOT=root):
            path = Path(root) / 'Grüße file.txt'
            path.write_bytes(b'hello')
            for version_one in (True, False):
                with self.subTest(version_one=version_one), override_settings(MOD_XSENDFILE_V1_0=version_one):
                    with patch('utilities.views.sys.argv', ['apache']):
                        response = sendfile(RequestFactory().get('/'), path.name)
                    self.assertEqual(response['Content-Type'], 'text/plain')
                    self.assertEqual(response['Content-Length'], '5')
                    if version_one:
                        self.assertIn('Gr%C3%BC%C3%9Fe%20file.txt', response['X-Sendfile'])
                    else:
                        self.assertEqual(response['X-Sendfile'], str(path))

    def test_development_server_delegates_streaming_response(self) -> None:
        with TemporaryDirectory() as root, override_settings(UPLOAD_ROOT=root):
            path = Path(root) / 'file.bin'
            path.write_bytes(b'data')
            request = RequestFactory().get('/')
            response = HttpResponse('development response')
            with patch('utilities.views.sys.argv', ['runserver']):
                with patch('utilities.views.serve', return_value=response) as serve:
                    self.assertIs(sendfile(request, path.name), response)
                    serve.assert_called_once_with(request, path.name, document_root=root)

    def test_missing_file_is_not_found_in_both_response_paths(self) -> None:
        with TemporaryDirectory() as root, override_settings(UPLOAD_ROOT=root):
            request = RequestFactory().get('/')
            for view in (sendfile, forbidden):
                with self.subTest(view=view), self.assertRaises(Http404):
                    view(request, 'missing.txt')


class TestFileOperations(SimpleTestCase):
    def test_file_name_contract(self) -> None:
        self.assertEqual(require_file_name(ContentFile(b'data', name='file.txt')), 'file.txt')
        with self.assertRaisesRegex(ValueError, 'name'):
            require_file_name(ContentFile(b'data'))

    def test_temporary_folder_does_not_change_process_default(self) -> None:
        with TemporaryDirectory() as root:
            original = tempfile.tempdir
            folder = create_tempfolder(root)
            self.assertEqual(Path(folder).parent, Path(root))
            self.assertEqual(Path(folder).stat().st_mode & 0o777, 0o770)
            self.assertEqual(tempfile.tempdir, original)

    def test_zip_callbacks_and_relative_destinations(self) -> None:
        with TemporaryDirectory() as root:
            archive = Path(root) / 'input.zip'
            destination = Path(root) / 'output'
            destination.mkdir()
            (destination / 'existing.txt').write_bytes(b'old')
            with zipfile.ZipFile(archive, 'w') as zip:
                zip.writestr('existing.txt', b'new')
                zip.writestr('nested/', b'')
                zip.writestr('nested/file.bin', b'\x00\x01')
            overwritten: list[str] = []
            extracted: list[str] = []
            unpack_zipfile_to(
                str(archive), os.path.relpath(destination),
                overwritten.append, extracted.append,
            )
            self.assertEqual(overwritten, ['existing.txt'])
            self.assertEqual(extracted, ['existing.txt', 'nested/file.bin'])
            self.assertEqual((destination / 'nested/file.bin').read_bytes(), b'\x00\x01')
            self.assertEqual((destination / 'existing.txt').read_bytes(), b'new')

    def test_zip_paths_must_remain_inside_the_destination(self) -> None:
        with TemporaryDirectory() as root:
            archive = Path(root) / 'input.zip'
            destination = Path(root) / 'output'
            for name in ('../output-sibling/file.txt', '/absolute/file.txt', '../../outside.txt'):
                with self.subTest(name=name):
                    with zipfile.ZipFile(archive, 'w') as zip:
                        zip.writestr(name, b'data')
                    with self.assertRaisesRegex(InvalidZipFile, 'illegal path'):
                        unpack_zipfile_to(str(archive), str(destination))
            self.assertFalse((Path(root) / 'output-sibling').exists())

    def test_non_zip_is_explicitly_rejected(self) -> None:
        with TemporaryDirectory() as root:
            source = Path(root) / 'not.zip'
            source.write_text('not a zip')
            with self.assertRaisesRegex(InvalidZipFile, 'not a zipfile'):
                unpack_zipfile_to(str(source), str(Path(root) / 'output'))


class TestSettingsDefaults(SimpleTestCase):
    def settings_for(self, root: str) -> dict[str, object]:
        return {
            'SITE_NAME': 'Test defaults',
            'PRAKTOMAT_ID': 'defaults-test',
            'BASE_HOST': 'http://localhost',
            'BASE_PATH': '/defaults/',
            'UPLOAD_ROOT': root,
            'PRIVATE_KEY': None,
            'CERTIFICATE': None,
            'SECRET_KEY': 'test-key',
            'DEBUG': False,
        }

    def test_required_values_are_not_invented(self) -> None:
        with self.assertRaisesRegex(RuntimeError, 'SITE_NAME'):
            load_defaults({})

    def test_repeated_loads_are_isolated_and_preserve_overrides(self) -> None:
        with TemporaryDirectory() as root:
            first = self.settings_for(root)
            first['AUTH_BACKEND'] = 'custom.backend'
            load_defaults(first)
            second = self.settings_for(root)
            second['BASE_PATH'] = '/second/'
            load_defaults(second)
        self.assertEqual(first['STATIC_URL'], '/defaults/static/')
        self.assertEqual(second['STATIC_URL'], '/second/static/')
        self.assertEqual(first['AUTHENTICATION_BACKENDS'], (
            'accounts.ldap_auth.LDAPBackend', 'custom.backend',
        ))
        self.assertEqual(second['USE_TZ'], False)
        self.assertIsNone(second['DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_1'])

    def test_debug_and_shibboleth_overrides_control_dependent_defaults(self) -> None:
        with TemporaryDirectory() as root:
            values = self.settings_for(root)
            values.update({
                'DEBUG': True, 'SHIB_ENABLED': True,
                'INSTALLED_APPS': ('custom.app',),
                'MIDDLEWARE': ['custom.Middleware'],
            })
            load_defaults(values)
        self.assertEqual(values['LOGIN_URL'], 'shib_hello')
        self.assertEqual(values['INSTALLED_APPS'], ('debug_toolbar', 'custom.app'))
        self.assertEqual(values['MIDDLEWARE'], [
            'debug_toolbar.middleware.DebugToolbarMiddleware', 'custom.Middleware',
        ])

    def test_secret_key_is_created_with_private_permissions_and_reused(self) -> None:
        with TemporaryDirectory() as root:
            values = self.settings_for(root)
            del values['SECRET_KEY']
            load_defaults(values)
            path = Path(root) / 'SECRET_KEY'
            self.assertEqual(path.read_text(), values['SECRET_KEY'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            again = self.settings_for(root)
            del again['SECRET_KEY']
            load_defaults(again)
            self.assertEqual(again['SECRET_KEY'], values['SECRET_KEY'])

    def test_empty_secret_key_file_is_rejected(self) -> None:
        with TemporaryDirectory() as root:
            (Path(root) / 'SECRET_KEY').touch()
            values = self.settings_for(root)
            del values['SECRET_KEY']
            with self.assertRaisesRegex(RuntimeError, 'empty'):
                load_defaults(values)

    def test_invalid_derived_setting_inputs_are_rejected(self) -> None:
        for name, value in (
            ('BASE_PATH', None), ('DEBUG', 'yes'), ('AUTH_BACKEND', 1),
            ('INSTALLED_APPS', 'app'), ('MIDDLEWARE', [1]),
        ):
            with self.subTest(setting=name), TemporaryDirectory() as root:
                values = self.settings_for(root)
                values['DEBUG'] = True
                values[name] = value
                with self.assertRaisesRegex(TypeError, name):
                    load_defaults(values)

    def test_derived_defaults_use_this_calls_path_overrides(self) -> None:
        with TemporaryDirectory() as root:
            values = self.settings_for(root)
            values.update({
                'PRAKTOMAT_ROOT': '/custom/root', 'STATIC_URL': '/assets/',
                'ADMINS': [('Admin', 'admin@example.com')],
                'DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_1': '/custom:/extra:ro',
            })
            load_defaults(values)
        self.assertEqual(values['STATIC_ROOT'], '/custom/static')
        self.assertEqual(values['ADMIN_MEDIA_PREFIX'], '/assets/admin/')
        self.assertEqual(values['MANAGERS'], values['ADMINS'])
        self.assertEqual(values['DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_1'], '/custom:/extra:ro')

    @patch('settings.defaults.load_defaults')
    def test_deployment_overrides_preserve_course_and_mirror_behavior(self, loader: Mock) -> None:
        path = Path(__file__).parents[1] / 'settings' / 'local.py'
        code = compile(path.read_text(), str(path), 'exec')
        for course, title, timeout, parallel in (
            ('', 'Programmieren', 600, 6),
            ('algo1_', 'Algorithmen I', 180, 6),
            ('cram_', 'CRAM', 600, 6),
            ('birap_', 'BIRAP', 600, 6),
            ('tba_', 'Theorembeweiser', 600, 1),
            ('mlfds_', 'MLFDS', 180, 6),
            ('pp_', 'Programmierparadigmen', 180, 6),
            ('iimb_', 'Informatik im Maschinenbau', 180, 6),
        ):
            for mirror in (False, True):
                deployment = f'{course}2024_WS_Abschluss' + ('_Mirror' if mirror else '')
                with self.subTest(deployment=deployment):
                    values: dict[str, object] = {
                        '__file__': f'/srv/{deployment}/praktomat/src/settings/local.py',
                        '__package__': 'settings',
                        '__name__': 'settings.local',
                    }
                    exec(code, values)
                    self.assertEqual(values['SITE_NAME'], (
                        f'{title} Abschlussaufgaben Wintersemester 2024/2025'
                        + (' (Mirror)' if mirror else '')
                    ))
                    self.assertEqual(values['MIRROR'], mirror)
                    self.assertEqual(values['DEBUG'], mirror)
                    self.assertEqual(values['TEST_TIMEOUT'], timeout)
                    self.assertEqual(values['NUMBER_OF_TASKS_TO_BE_CHECKED_IN_PARALLEL'], parallel)
                    self.assertEqual(values['EMAIL_BACKEND'], (
                        'django.core.mail.backends.filebased.EmailBackend' if mirror
                        else 'django.core.mail.backends.smtp.EmailBackend'
                    ))
                    if course == 'cram_':
                        self.assertEqual(values['TEST_MAXMEM'], 200)
                    loader.assert_called_with(values)


@override_settings(USEPRAKTOMATTESTER=False, USESAFEDOCKER=False)
class TestExecutionOptions(SimpleTestCase):
    @patch('utilities.safeexec.subprocess.Popen')
    def test_plain_execution_preserves_output_and_limits(self, popen: Mock) -> None:
        process = popen.return_value
        process.communicate.return_value = (b'output', b'error')
        process.returncode = 3
        result = execute_arglist(
            ['program', 'argument'], '/work', fileseeklimit=12,
            error_to_output=False,
        )
        self.assertIsInstance(result, ExecutionResult)
        self.assertEqual(result, ('output', b'error', 3, False, False))
        self.assertEqual(result.output, 'output')
        self.assertEqual(popen.call_args.args[0], [
            'prlimit', '--nofile=128', '--fsize=12288', 'program', 'argument',
        ])

    @patch('utilities.safeexec.subprocess.Popen')
    def test_environment_changes_do_not_leak_to_host(self, popen: Mock) -> None:
        popen.return_value.communicate.return_value = (b'', None)
        popen.return_value.returncode = 0
        with patch.dict(os.environ, {'PRAKTOMAT_EXEC_TEST': 'host'}):
            execute_arglist(['program'], '/work', {'PRAKTOMAT_EXEC_TEST': 'child'})
            self.assertEqual(os.environ['PRAKTOMAT_EXEC_TEST'], 'host')
            self.assertEqual(popen.call_args.kwargs['env']['PRAKTOMAT_EXEC_TEST'], 'child')

    @override_settings(USEPRAKTOMATTESTER=True, USESAFEDOCKER=True)
    @patch('utilities.safeexec.safe_docker_cleanup')
    @patch('utilities.safeexec.safe_docker')
    @patch('utilities.safeexec.subprocess.Popen')
    def test_tester_backend_does_not_use_docker_state(
        self, popen: Mock, docker: Mock, cleanup: Mock
    ) -> None:
        popen.return_value.communicate.return_value = (b'', None)
        popen.return_value.returncode = 137
        result = execute_arglist(['program'], '/work')
        docker.assert_not_called()
        cleanup.assert_not_called()
        self.assertFalse(result[4])
        self.assertIn('tester', popen.call_args.args[0])

    @override_settings(USESAFEDOCKER=True)
    @patch('utilities.safeexec.safe_docker_cleanup')
    @patch('utilities.safeexec.safe_docker')
    @patch('utilities.safeexec.subprocess.Popen')
    def test_docker_exit_status_and_cleanup(
        self, popen: Mock, docker: Mock, cleanup: Mock
    ) -> None:
        volumes = [{'container': 'helper', 'volume': 'volume', 'dir': '/work/'}]
        docker.return_value = (['docker-command'], 'container', volumes)
        popen.return_value.communicate.return_value = (b'', None)
        popen.return_value.returncode = 137
        self.assertTrue(execute_arglist(['program'], '/work')[4])
        cleanup.assert_called_once_with(volumes)

    @override_settings(USESAFEDOCKER=True)
    @patch('utilities.safeexec.safe_docker_cleanup')
    @patch('utilities.safeexec.safe_docker')
    @patch('utilities.safeexec.subprocess.Popen', side_effect=OSError('launch failed'))
    def test_docker_resources_are_cleaned_if_process_launch_fails(
        self, popen: Mock, docker: Mock, cleanup: Mock
    ) -> None:
        docker.return_value = (['docker-command'], 'container', [])
        with self.assertRaisesRegex(OSError, 'launch failed'):
            execute_arglist(['program'], '/work')
        cleanup.assert_called_once_with([])

    @override_settings(USESAFEDOCKER=True)
    @patch('utilities.safeexec.safe_docker_cleanup')
    @patch('utilities.safeexec.safe_docker', return_value=(['docker-command'], 'container', []))
    @patch('utilities.safeexec.subprocess.Popen')
    def test_docker_resources_are_cleaned_if_communication_fails(
        self, popen: Mock, docker: Mock, cleanup: Mock
    ) -> None:
        popen.return_value.communicate.side_effect = OSError('communication failed')
        with self.assertRaisesRegex(OSError, 'communication failed'):
            execute_arglist(['program'], '/work')
        cleanup.assert_called_once_with([])

    @override_settings(USEPRAKTOMATTESTER=True, USESAFEDOCKER=True)
    @patch('utilities.safeexec.safe_docker')
    @patch('utilities.safeexec.subprocess.Popen')
    def test_unsafe_execution_bypasses_both_backends(self, popen: Mock, docker: Mock) -> None:
        popen.return_value.communicate.return_value = (b'', None)
        popen.return_value.returncode = 137
        result = execute_arglist(['program'], '/work', unsafe=True)
        self.assertFalse(result.oom_ed)
        self.assertEqual(popen.call_args.args[0], ['prlimit', '--nofile=128', 'program'])
        docker.assert_not_called()

    @patch('utilities.safeexec.kill_proc_tree')
    @patch('utilities.safeexec.time.sleep')
    @patch('utilities.safeexec.subprocess.call')
    @patch('utilities.safeexec.subprocess.Popen')
    def test_timeout_uses_the_selected_backend(
        self, popen: Mock, call: Mock, sleep: Mock, kill_tree: Mock
    ) -> None:
        for tester, unsafe in ((False, False), (True, False), (True, True)):
            with self.subTest(tester=tester, unsafe=unsafe), override_settings(
                USEPRAKTOMATTESTER=tester, USESAFEDOCKER=tester,
            ):
                call.reset_mock()
                process = popen.return_value
                process.pid = 42
                process.poll.return_value = None
                process.communicate.side_effect = [
                    subprocess.TimeoutExpired('program', 1), (b'timeout output', None),
                ]
                process.returncode = -9
                result = execute_arglist(['program'], '/work', timeout=1, unsafe=unsafe)
                self.assertTrue(result.timed_out)
                self.assertFalse(result.oom_ed)
                prefix = ['sudo', '-E', '-u', 'tester'] if tester and not unsafe else []
                self.assertEqual(
                    call.call_args_list[0].args[0], prefix + ['pkill', '-TERM', '-s', '42']
                )
                self.assertEqual(call.call_count, 4)
                kill_tree.assert_called_with(pid=42)
                process.kill.assert_called()

    @override_settings(USESAFEDOCKER=True)
    @patch('utilities.safeexec.subprocess.call')
    @patch('utilities.safeexec.safe_docker_cleanup')
    @patch('utilities.safeexec.safe_docker', return_value=(['docker-command'], 'container', []))
    @patch('utilities.safeexec.subprocess.Popen')
    def test_timeout_kills_selected_container_and_collects_output(
        self, popen: Mock, docker: Mock, cleanup: Mock, call: Mock
    ) -> None:
        process = popen.return_value
        process.communicate.side_effect = [
            subprocess.TimeoutExpired('program', 1), (b'timed out', None),
        ]
        process.poll.return_value = -9
        process.returncode = -9
        result = execute_arglist(['program'], '/work', timeout=1)
        self.assertEqual(result, ('timed out', None, -9, True, False))
        call.assert_called_once_with(['sudo', 'docker', 'kill', 'container'])
        cleanup.assert_called_once_with([])


@override_settings(
    DOCKER_CONTAINER_HOST_NET=False, DOCKER_CONTAINER_WRITABLE=False,
    DOCKER_UID_MOD=False, DOCKER_IMAGE_NAME='test-image',
    DOCKER_CONTAINER_EXTERNAL_DIR=None,
    DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_1=None,
    DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_2=None,
    DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_3=None,
    DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_4=None,
    DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_5=None,
)
class TestDockerOptions(SimpleTestCase):
    @patch('utilities.safeexec.exists', return_value=False)
    def test_task_id_templates_and_missing_ids(self, exists: Mock) -> None:
        with override_settings(
            DOCKER_CONTAINER_EXTERNAL_DIR='/courses/${TASK_ID_CUSTOM}',
            DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_1='/extras/$TASK_ID_CUSTOM:/extras:ro',
        ):
            command, _, volumes = safe_docker(
                {'TASK_ID_CUSTOM': 'task-42'}, [], 128, ['nofile=64'], '/work', True
            )
            self.assertIn('--volume=/courses/task-42:/external:ro', command)
            self.assertIn('--volume=/extras/task-42:/extras:ro', command)
            self.assertIn('--memory=128m', command)
            self.assertEqual(volumes, [])
            missing, _, _ = safe_docker({}, [], None, [], '/work', True)
            self.assertFalse(any('/courses/' in arg or '/extras/' in arg for arg in missing))

    @patch('utilities.safeexec.exists', return_value=False)
    def test_literal_paths_and_escaped_template_variables(self, exists: Mock) -> None:
        with override_settings(DOCKER_CONTAINER_EXTERNAL_DIR='/courses/$$TASK_ID_CUSTOM'):
            command, _, _ = safe_docker({}, ['/scripts'], None, [], '/work')
        self.assertIn('--volume=/courses/$$TASK_ID_CUSTOM:/external:ro', command)
        self.assertIn('--volume=/scripts:/scripts:ro', command)
        self.assertIn('--volume=/work:/work', command)
        self.assertIn('--memory=1024m', command)

    def test_invalid_mount_paths_are_rejected_before_launch(self) -> None:
        with self.assertRaisesRegex(Exception, 'working directory'):
            safe_docker({}, [], None, [], '/invalid:path')
        with self.assertRaisesRegex(Exception, 'extra directory'):
            safe_docker({}, ['/invalid:path'], None, [], '/work')

    @patch('utilities.safeexec.exists', return_value=False)
    def test_empty_task_ids_are_not_mounted(self, exists: Mock) -> None:
        with override_settings(DOCKER_CONTAINER_EXTERNAL_DIR='/tasks/$TASK_ID_CUSTOM'):
            command, _, _ = safe_docker({'TASK_ID_CUSTOM': ''}, [], None, [], '/work')
        self.assertFalse(any('/tasks/' in arg for arg in command))

    @patch('utilities.safeexec.subprocess.run')
    @patch('utilities.safeexec.exists', return_value=True)
    def test_containerized_mounts_transfer_cleanup_ownership(self, exists: Mock, run: Mock) -> None:
        command, _, volumes = safe_docker({}, [], None, [], '/work')
        self.assertEqual(len(volumes), 1)
        self.assertIn(f"--volume={volumes[0]['volume']}:/work/", command)
        self.assertEqual(volumes[0]['dir'], '/work/')
        self.assertEqual(run.call_count, 5)
        for invocation in run.call_args_list:
            self.assertTrue(invocation.kwargs['check'])
            self.assertNotIn('stderr', invocation.kwargs)
        with override_settings(DOCKER_DISCARD_ARTEFACTS=False):
            safe_docker_cleanup(volumes)
        self.assertEqual(run.call_count, 8)
        self.assertEqual(run.call_args_list[5].args[0][2:3], ['cp'])
        self.assertEqual(run.call_args_list[6].args[0][2:4], ['container', 'rm'])
        self.assertEqual(run.call_args_list[7].args[0][2:4], ['volume', 'rm'])

    @patch('utilities.safeexec.subprocess.run')
    @patch('utilities.safeexec.exists', return_value=True)
    def test_failed_mount_setup_releases_allocated_resources(self, exists: Mock, run: Mock) -> None:
        for stage in range(5):
            with self.subTest(stage=stage):
                run.reset_mock()
                failure = subprocess.CalledProcessError(1, ['mocked-docker'])
                cleanup_count = 0 if stage == 0 else 1 if stage == 1 else 2
                run.side_effect = [None] * stage + [failure] + [None] * cleanup_count
                with self.assertRaises(subprocess.CalledProcessError):
                    safe_docker({}, [], None, [], '/work')
                cleanup_calls = run.call_args_list[stage + 1:]
                self.assertEqual(len(cleanup_calls), cleanup_count)
                if cleanup_count:
                    self.assertEqual(cleanup_calls[-1].args[0][2:4], ['volume', 'rm'])
                if cleanup_count == 2:
                    self.assertEqual(cleanup_calls[0].args[0][2:5], ['container', 'rm', '-f'])

    @patch('utilities.safeexec.subprocess.run')
    @patch('utilities.safeexec.exists', return_value=True)
    def test_invalid_template_releases_prior_mounts(self, exists: Mock, run: Mock) -> None:
        with override_settings(DOCKER_CONTAINER_EXTERNAL_DIR='/$TASK_ID_CUSTOM/$UNKNOWN'):
            with self.assertRaises(KeyError):
                safe_docker({'TASK_ID_CUSTOM': 'task'}, ['/scripts'], None, [], '/work')
        self.assertEqual(run.call_count, 7)
        self.assertEqual(run.call_args_list[5].args[0][2:5], ['container', 'rm', '-f'])
        self.assertEqual(run.call_args_list[6].args[0][2:4], ['volume', 'rm'])

    @override_settings(DOCKER_DISCARD_ARTEFACTS=False)
    @patch('utilities.safeexec.subprocess.run')
    def test_failed_copyback_still_releases_all_resources(self, run: Mock) -> None:
        run.side_effect = [subprocess.CalledProcessError(1, ['mocked-docker'])] + [None] * 4
        with self.assertRaises(subprocess.CalledProcessError):
            safe_docker_cleanup([
                {'container': 'helper1', 'volume': 'volume1', 'dir': '/first/'},
                {'container': 'helper2', 'volume': 'volume2', 'dir': '/second/'},
            ])
        self.assertEqual(run.call_count, 5)
        for invocation in run.call_args_list:
            self.assertTrue(invocation.kwargs['check'])

    @override_settings(DOCKER_DISCARD_ARTEFACTS=True)
    @patch('utilities.safeexec.subprocess.run')
    def test_discarded_artefacts_are_not_copied_back(self, run: Mock) -> None:
        safe_docker_cleanup([{'container': 'helper', 'volume': 'volume', 'dir': '/work/'}])
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0], ['sudo', 'docker', 'container', 'rm', 'helper'])
        self.assertEqual(run.call_args_list[1].args[0], ['sudo', 'docker', 'volume', 'rm', 'volume'])
