from os.path import dirname, join
from datetime import datetime, timedelta
from collections.abc import Callable
import difflib
import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile
from unittest.mock import Mock, patch
from email import policy
from email.parser import BytesParser

from utilities.TestSuite import TestCase
from django.core.mail import get_connection
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.test import SimpleTestCase, RequestFactory, override_settings
from django.contrib.admin import AdminSite
from django.urls import reverse
from django.utils.translation import gettext_lazy
from django.utils.functional import Promise

from checker.checker.TextChecker import TextChecker
from checker.checker.CreateFileChecker import CreateFileChecker
from checker.checker.CheckStyleChecker import CheckStyleChecker
from checker.checker.ScriptChecker import ScriptChecker
from checker.basemodels import CheckerResult, CheckerResultArtefact
from accounts.models import User
from django.contrib.auth.models import Group
from solutions.forms import SolutionFileForm, SolutionFormSet, ModelSolutionFormSet
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict
from solutions.models import (
    ConfirmationMessage, Solution, SolutionFile, get_solutions_zip,
    id_for_path, path_for_task, path_for_user, until_critical,
)
from solutions.templatetags.highlight import colorize, colorize_table, colorize_diff_table
from pygments.util import ClassNotFound
from tasks.models import Task
from solutions.admin import SolutionAdmin, IsLatestOfOnlyFailedFilter


class TestSolutionHTTPContracts(TestCase):
    def test_checker_table_keeps_model_rows_and_missing_result_cells(self) -> None:
        task = Task.objects.get(pk=1)
        first_solution = Solution.objects.get(task=task)
        first_solution.final = True
        first_solution.save()
        other = User.objects.create_user('http-table-user', password='demo')
        other.mat_number = 22222
        other.save()
        other.groups.add(Group.objects.get(name='User'))
        second_solution = Solution.objects.create(task=task, author=other, final=True)
        early = TextChecker.objects.create(task=task, order=1)
        late = TextChecker.objects.create(task=task, order=2)
        first_result = CheckerResult.objects.create(solution=first_solution, checker=late, passed=True)
        second_result = CheckerResult.objects.create(solution=second_solution, checker=early, passed=False)
        self.client.force_login(User.objects.get(username='trainer'))
        response = self.client.get(reverse('checker_result_list', args=[task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['checkers_seen'], [early, late])
        rows = response.context['users_with_checkerresults']
        self.assertEqual(rows[0], (first_solution.author, [None, first_result], first_solution))
        self.assertEqual(rows[1], (other, [second_result, None], second_solution))
        self.assertContains(response, reverse('solution_detail_full', args=[second_solution.pk]))

    def test_checker_table_denies_students(self) -> None:
        self.client.force_login(User.objects.get(username='user'))
        response = self.client.get(reverse('checker_result_list', args=[1]))
        self.assertEqual(response.status_code, 403)


class TestSolutionAdminContracts(TestCase):
    def setUp(self) -> None:
        self.model_admin = SolutionAdmin(Solution, AdminSite())
        self.request = RequestFactory().get('/')

    def test_annotated_columns_accept_only_database_booleans(self) -> None:
        solution = Solution.objects.all()[0]
        for name, display in (
            ('_tests_failed_computed_for_sorting', self.model_admin.tests_failed),
            ('_latest_of_only_failed_computed_for_sorting', self.model_admin.latest_of_only_failed),
        ):
            with self.subTest(name=name):
                with self.assertRaises(AttributeError):
                    display(solution)
                for value in (False, True, 0, 1):
                    setattr(solution, name, value)
                    self.assertIs(display(solution), bool(value))
                for invalid in (None, 2, '0', 0.5):
                    setattr(solution, name, invalid)
                    with self.assertRaises(TypeError):
                        display(solution)

    def test_queryset_annotations_and_filter_partition(self) -> None:
        queryset = self.model_admin.get_queryset(self.request)
        expected: dict[bool, set[int]] = {False: set(), True: set()}
        for solution in queryset:
            self.assertIsInstance(self.model_admin.tests_failed(solution), bool)
            expected[self.model_admin.latest_of_only_failed(solution)].add(solution.pk)
        for value in ('Yes', 'No'):
            filter_instance = IsLatestOfOnlyFailedFilter(
                self.request, {'latest_of_only_failed': [value]}, Solution, self.model_admin,
            )
            self.assertEqual(
                set(filter_instance.queryset(self.request, queryset).values_list('pk', flat=True)),
                expected[value == 'Yes'],
            )
        unset_filter = IsLatestOfOnlyFailedFilter(self.request, {}, Solution, self.model_admin)
        self.assertIs(unset_filter.queryset(self.request, queryset), queryset)
        self.assertEqual(
            getattr(SolutionAdmin.tests_failed, 'admin_order_field'), '_tests_failed_computed_for_sorting',
        )
        self.assertTrue(getattr(SolutionAdmin.tests_failed, 'boolean'))

    def test_checker_actions_preserve_execution_modes_and_messages(self) -> None:
        queryset = Solution.objects.filter(pk=1)
        for action, mode in ((self.model_admin.run_checkers, False), (self.model_admin.run_checkers_all, True)):
            with self.subTest(mode=mode), patch('solutions.admin.check_multiple') as check, patch.object(self.model_admin, 'message_user') as message:
                action(self.request, queryset)
                check.assert_called_once_with(queryset, mode)
                message.assert_called_once()

    def test_plagiarism_actions_update_and_count_only_changes(self) -> None:
        queryset = Solution.objects.filter(pk=1)
        queryset.update(plagiarism=False)
        with patch.object(self.model_admin, 'message_user') as message:
            self.model_admin.mark_plagiarism(self.request, queryset)
            self.assertTrue(queryset.get().plagiarism)
            self.assertEqual(message.call_args.args[1], '1 solutions marked as plagiated')
            self.model_admin.mark_plagiarism(self.request, queryset)
            self.assertEqual(message.call_args.args[1], '0 solutions marked as plagiated')
            self.model_admin.mark_no_plagiarism(self.request, queryset)
            self.assertFalse(queryset.get().plagiarism)
            self.assertEqual(message.call_args.args[1], '1 solutions marked as not plagiated')


class TestSolutionFormSetContracts(TestCase):
    def test_empty_and_unchanged_formsets_require_a_file(self) -> None:
        solution = Solution.objects.all()[0]
        for factory in (SolutionFormSet, ModelSolutionFormSet):
            with self.subTest(factory=factory):
                formset = factory({
                    'solutionfile_set-TOTAL_FORMS': '1',
                    'solutionfile_set-INITIAL_FORMS': '0',
                }, instance=solution)
                self.assertFalse(formset.is_valid())
                self.assertIn('You must choose at least one file.', formset.non_form_errors())

    def test_changed_upload_is_valid_and_keeps_typed_solution(self) -> None:
        solution = Solution.objects.all()[0]
        for factory in (SolutionFormSet, ModelSolutionFormSet):
            with self.subTest(factory=factory):
                formset = factory({
                    'solutionfile_set-TOTAL_FORMS': '1',
                    'solutionfile_set-INITIAL_FORMS': '0',
                }, MultiValueDict({'solutionfile_set-0-file': [SimpleUploadedFile('valid.txt', b'content')]}), instance=solution)
                self.assertTrue(formset.is_valid(), formset.errors)
                self.assertEqual(formset.forms[0].cleaned_data['solution'], solution)

    def test_invalid_changed_upload_keeps_field_error(self) -> None:
        solution = Solution.objects.all()[0]
        formset = SolutionFormSet({
            'solutionfile_set-TOTAL_FORMS': '1',
            'solutionfile_set-INITIAL_FORMS': '0',
        }, MultiValueDict({'solutionfile_set-0-file': [SimpleUploadedFile('invalid.txt', b'contains\x00nul')]}), instance=solution)
        self.assertFalse(formset.is_valid())
        self.assertIn('file', formset.forms[0].errors)
        self.assertFalse(formset.non_form_errors())


class TestSolutionModelContracts(TestCase):
    def test_copy_remaps_primary_keys_and_keeps_related_records(self) -> None:
        solution = Solution.objects.get(task_id=1)
        original_id = solution.pk
        original_number = solution.number
        original_file = solution.solutionfile_set.get()
        checker = TextChecker.objects.create(task=solution.task, order=1, text='test')
        result = solution.checkerresult_set.create(checker=checker, passed=True)
        solution.copy()
        self.assertNotEqual(solution.pk, original_id)
        assert original_number is not None
        self.assertEqual(solution.number, original_number + 1)
        self.assertTrue(solution.final)
        copied_file = solution.solutionfile_set.get()
        self.assertNotEqual(copied_file.pk, original_file.pk)
        self.assertEqual(copied_file.solution_id, solution.pk)
        self.assertEqual(copied_file.file.name, original_file.file.name)
        copied_result = solution.checkerresult_set.get()
        self.assertNotEqual(copied_result.pk, result.pk)
        self.assertEqual(copied_result.solution_id, solution.pk)
        self.assertEqual(copied_result.checker, checker)
        self.assertTrue(Solution.objects.filter(pk=original_id, final=False).exists())
        self.assertEqual(solution.task.solution_set.count(), 2)
        self.assertIn(solution, solution.author.solution_set.all())

    def test_critical_results_include_failure_and_stop_after_it(self) -> None:
        solution = Solution.objects.get(task_id=1)
        checker = TextChecker.objects.create(task=solution.task, order=1, text='test')
        critical = TextChecker.objects.create(
            task=solution.task, order=2, text='critical', critical=True
        )
        first = solution.checkerresult_set.create(checker=checker, passed=True)
        stop = solution.checkerresult_set.create(checker=critical, passed=False)
        last = solution.checkerresult_set.create(checker=checker, passed=True)
        self.assertEqual(until_critical([]), [])
        self.assertEqual(until_critical([first, stop, last]), [first, stop])
        self.assertEqual(until_critical([first, last]), [first, last])

    def test_missing_and_malformed_solution_file_names_raise_explicit_errors(self) -> None:
        file = SolutionFile(solution=Solution.objects.get(task_id=1))
        with self.assertRaisesRegex(ValueError, 'name'):
            file.save()
        with self.assertRaisesRegex(ValueError, 'name'):
            file.path()
        file.file.name = 'unrelated/file.txt'
        with self.assertRaisesRegex(ValueError, 'SolutionArchive'):
            file.path()

    def test_solution_path_survives_copy_and_accepts_spaces_in_username(self) -> None:
        file = SolutionFile(solution=Solution.objects.get(task_id=1))
        file.file.name = 'SolutionArchive/Task_1/User_Test User/Solution_123/folder/test.txt'
        self.assertEqual(file.path(), 'folder/test.txt')
        self.assertEqual(str(file), 'test.txt')

    def test_zip_upload_preserves_nested_bytes_and_filters_ignored_entries(self) -> None:
        solution = Solution.objects.get(task_id=1)
        original_ids = list(solution.solutionfile_set.values_list('pk', flat=True))
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as zip:
            zip.writestr('nested/main.txt', b'hello\n')
            zip.writestr('image.bin', b'\x00\x01')
            zip.writestr('.hidden', b'ignored')
            zip.writestr('__MACOSX/file', b'ignored')
            zip.writestr('../escape', b'ignored')
        with TemporaryDirectory() as root, patch.object(storages['default'], 'location', root):
            upload = SolutionFile(solution=solution)
            upload.file = ContentFile(archive.getvalue(), name='upload.zip')
            upload.save()
            files = solution.solutionfile_set.exclude(pk__in=original_ids)
            uploaded = {file.path(): file.file.read() for file in files}
            self.assertEqual(uploaded, {'nested/main.txt': b'hello\n', 'image.bin': b'\x00\x01'})
            self.assertFalse(SolutionFile.objects.filter(solution=solution, file__endswith='upload.zip').exists())

    def test_solution_download_has_exact_names_contents_and_rewound_stream(self) -> None:
        solution = Solution.objects.get(task_id=1)
        base = f'{path_for_task(solution.task)}/{path_for_user(solution.author)}/'
        with get_solutions_zip([solution]) as stream:
            self.assertEqual(stream.tell(), 0)
            with zipfile.ZipFile(stream) as archive:
                file = solution.solutionfile_set.get()
                self.assertIn(base + '.project', archive.namelist())
                self.assertEqual(archive.read(base + 'solution/' + file.path()), file.file.read())

    def test_anonymous_download_uses_stable_numbered_projects(self) -> None:
        solution = Solution.objects.get(task_id=1)
        solution.author.first_name = 'Hidden'
        solution.author.last_name = 'Author'
        with patch('solutions.models.get_settings') as configuration:
            configuration.return_value.anonymous_attestation = True
            with get_solutions_zip([solution]) as stream, zipfile.ZipFile(stream) as archive:
                project = archive.read(f'{solution.task.title}/User1/.project')
                self.assertIn(b'User 1', project)
                self.assertNotIn(solution.author.get_full_name().encode(), project)

    def test_invalid_user_archive_path_is_rejected(self) -> None:
        self.assertEqual(id_for_path('Test-123-42'), '42')
        with self.assertRaisesRegex(ValueError, 'path'):
            id_for_path('invalid')

    def test_full_download_includes_stored_generated_and_artefact_files(self) -> None:
        solution = Solution.objects.get(task_id=1)
        base = f'{solution.task.title}/{path_for_user(solution.author)}/'
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, 'w') as archive:
            archive.writestr('nested/generated.txt', b'generated checker')
        with TemporaryDirectory() as root, patch.object(storages['default'], 'location', root), override_settings(SANDBOX_DIR=root):
            solution.solutionfile_set.all().delete()
            source = SolutionFile(solution=solution)
            source.file.save('main.txt', ContentFile(b'student source'))
            plain = CreateFileChecker(task=solution.task, order=1, path='support', filename='helper.txt')
            plain.file.save('helper.txt', ContentFile(b'checker helper'))
            packed = CreateFileChecker(task=solution.task, order=2, path='generated', unpack_zipfile=True)
            packed.file.save('support.zip', ContentFile(archive_bytes.getvalue()))
            style = CheckStyleChecker(task=solution.task, order=3)
            style.configuration.save('style.xml', ContentFile(b'<module/>'))
            script = ScriptChecker(task=solution.task, order=4)
            script.shell_script.save('script.sh', ContentFile(b'#!/bin/sh\n'))
            result = solution.checkerresult_set.create(checker=plain, passed=True)
            artefact = result.artefacts.create(filename='result.txt')
            artefact.file.save('result.txt', ContentFile(b'checker output'))
            with get_solutions_zip([solution], True, True) as stream, zipfile.ZipFile(stream) as archive:
                self.assertEqual(archive.read(base + 'solution/main.txt'), b'student source')
                self.assertEqual(archive.read(base + 'praktomat-files/other/support/helper.txt'), b'checker helper')
                self.assertEqual(archive.read(base + 'praktomat-files/other/generated/nested/generated.txt'), b'generated checker')
                self.assertEqual(archive.read(base + 'praktomat-files/checkstyle/style.xml'), b'<module/>')
                self.assertEqual(archive.read(base + 'praktomat-files/other/script.sh'), b'#!/bin/sh\n')
                self.assertEqual(archive.read(base + 'praktomat-files/artefacts/result.txt'), b'checker output')
            self.assertFalse(any(path.name.startswith('tmp') for path in Path(root).iterdir()))

    def test_failed_download_closes_stream_and_removes_temporary_files(self) -> None:
        solution = Solution.objects.get(task_id=1)
        with TemporaryDirectory() as root, override_settings(SANDBOX_DIR=root), TemporaryFile() as stream:
            with patch('solutions.models.tempfile.TemporaryFile', return_value=stream) as create:
                with patch('solutions.models.render_to_string', side_effect=RuntimeError('render failed')):
                    with self.assertRaisesRegex(RuntimeError, 'render failed'):
                        get_solutions_zip([solution], True)
                self.assertEqual(create.call_count, 1)
                self.assertTrue(stream.closed)
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_deleting_records_without_stored_files_is_safe(self) -> None:
        solution = Solution.objects.get(task_id=1)
        file = SolutionFile(solution=solution, mime_type='text/plain')
        SolutionFile.objects.bulk_create([file])
        file.delete()
        checker = TextChecker.objects.create(task=solution.task, order=1, text='test')
        result = solution.checkerresult_set.create(checker=checker, passed=True)
        artefact = CheckerResultArtefact.objects.create(result=result, filename='missing.txt')
        artefact.delete()
        self.assertFalse(result.artefacts.exists())


class TestSolutionFileValidation(TestCase):
    def test_upload_validation_preserves_stream_and_rejects_invalid_content(self) -> None:
        solution = Solution.objects.get(task_id=1)
        for name, content, message in (
            ('text.txt', b'bad\x00text', 'NUL'),
            ('archive.zip', b'not a zip', 'could not be read'),
            ('archive.tar', b'not a tar', 'Tar files'),
            ('big.txt', b'x' * (solution.task.max_file_size * 1024 + 1), 'bigger'),
        ):
            with self.subTest(name=name):
                form = SolutionFileForm()
                upload = ContentFile(content, name=name)
                form.cleaned_data = {'solution': solution, 'file': upload}
                with self.assertRaisesRegex(ValidationError, message):
                    form.clean_file()
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, 'w') as archive:
            archive.writestr('main.txt', b'valid text\n')
        upload = ContentFile(archive_bytes.getvalue(), name='upload.zip')
        form = SolutionFileForm()
        form.cleaned_data = {'solution': solution, 'file': upload}
        self.assertIs(form.clean_file(), upload)
        self.assertEqual(upload.tell(), 0)

    def test_missing_name_and_invalid_file_are_rejected(self) -> None:
        solution = Solution.objects.get(task_id=1)
        for upload, error in ((ContentFile(b'data'), 'name'), (object(), 'Invalid uploaded')):
            with self.subTest(upload=upload):
                form = SolutionFileForm()
                form.cleaned_data = {'solution': solution, 'file': upload}
                with self.assertRaisesRegex(ValidationError, error):
                    form.clean_file()

    def test_zip_member_validation_rewinds_even_when_rejected(self) -> None:
        solution = Solution.objects.get(task_id=1)
        for content, error in (
            (b'bad\x00text', 'NUL'),
            (b'x' * (solution.task.max_file_size * 1024 + 1), 'too big'),
        ):
            with self.subTest(error=error):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('member.txt', content)
                upload = ContentFile(buffer.getvalue(), name='upload.zip')
                form = SolutionFileForm()
                form.cleaned_data = {'solution': solution, 'file': upload}
                with self.assertRaisesRegex(ValidationError, error):
                    form.clean_file()
                self.assertEqual(upload.tell(), 0)


class TestConfirmationMessage(SimpleTestCase):
    signed_body = (
        'MIME-Version: 1.0\n'
        'Content-Type: multipart/signed; boundary="signed-boundary"\n'
        '\n'
        '--signed-boundary\n'
        'Content-Type: text/plain\n\n'
        'Signed content\n'
        '--signed-boundary\n'
        'Content-Type: application/pkcs7-signature\n\n'
        'signature-data\n'
        '--signed-boundary--\n'
    )

    def test_constructor_preserves_mail_options(self) -> None:
        connection = get_connection('django.core.mail.backends.locmem.EmailBackend')
        message = ConfirmationMessage(
            'Subject', 'Body', 'sender@example.com', ['to@example.com'],
            ['bcc@example.com'], connection, [('result.txt', 'Result', 'text/plain')],
            {'X-Praktomat': 'confirmation'}, ['cc@example.com'], ['reply@example.com'],
        )
        self.assertEqual(message.subject, 'Subject')
        self.assertEqual(message.body, 'Body')
        self.assertEqual(message.from_email, 'sender@example.com')
        self.assertEqual(message.to, ['to@example.com'])
        self.assertEqual(message.bcc, ['bcc@example.com'])
        self.assertIs(message.connection, connection)
        self.assertEqual(message.attachments, [('result.txt', 'Result', 'text/plain')])
        self.assertEqual(message.extra_headers, {'X-Praktomat': 'confirmation'})
        self.assertEqual(message.cc, ['cc@example.com'])
        self.assertEqual(message.reply_to, ['reply@example.com'])

    def test_signed_serialization_preserves_mime_body_and_envelope_headers(self) -> None:
        for separator in ('\n', '\r\n'):
            with self.subTest(separator=repr(separator)):
                message = ConfirmationMessage(
                    'Submission', self.signed_body, 'sender@example.com', ['to@example.com'],
                    headers={'X-Praktomat': 'confirmation'},
                )
                wire = message.message().as_bytes(linesep=separator)
                parsed = BytesParser(policy=policy.default).parsebytes(wire)
                self.assertEqual(parsed['Subject'], 'Submission')
                self.assertEqual(parsed['To'], 'to@example.com')
                self.assertEqual(parsed['X-Praktomat'], 'confirmation')
                self.assertEqual(parsed.get_content_type(), 'multipart/signed')
                self.assertEqual(len(list(parsed.iter_parts())), 2)
                self.assertIn(b'signature-data', wire)
                self.assertNotIn(b'Content-Type: text/plain; charset="utf-8"', wire)
                self.assertEqual(message.message().get_content_type(), 'multipart/signed')

    def test_unexpected_mime_structure_is_explicitly_rejected(self) -> None:
        message = ConfirmationMessage('Submission', 'not a signed MIME message')
        with self.assertRaisesRegex(ValueError, 'MIME'):
            message.message().as_bytes()

    def test_lazy_strings_remain_lazy_until_serialization(self) -> None:
        message = ConfirmationMessage(gettext_lazy('Submission'), gettext_lazy(self.signed_body))
        self.assertIsInstance(message.subject, Promise)
        self.assertIsInstance(message.body, Promise)
        self.assertIn(b'Subject: Submission', message.message().as_bytes())

    def test_signed_wire_bytes_match_django_52_serialization(self) -> None:
        headers = {'Date': 'Fri, 23 Oct 2026 00:00:00 +0000', 'Message-ID': '<test@example.com>'}
        for subject in ('Subject', 'Gr\u00fc\u00dfe ' * 30):
            plain = EmailMessage(subject, self.signed_body, 'from@example.com', ['to@example.com'], headers=headers)
            signed = ConfirmationMessage(subject, self.signed_body, 'from@example.com', ['to@example.com'], headers=headers)
            for separator in ('\n', '\r\n'):
                with self.subTest(subject=subject, separator=repr(separator)):
                    raw = plain.message()
                    buffer = io.BytesIO()
                    from email.generator import BytesGenerator
                    BytesGenerator(buffer, mangle_from_=False).flatten(raw, linesep=separator)
                    lines = buffer.getvalue().split(separator.encode())
                    first = lines.index(b'')
                    second = lines.index(b'', first + 1)
                    expected = separator.encode().join(lines[first + 1:second] + lines[3:first] + lines[second + 1:])
                    self.assertEqual(signed.message().as_bytes(linesep=separator), expected)
        message = ConfirmationMessage('Subject', self.signed_body)
        self.assertIn(b'signature-data', message.message(policy=policy.SMTP).as_bytes())
        self.assertTrue(message.message().as_bytes(unixfrom=True).startswith(b'From '))

    def test_smtp_backend_sends_signed_mime_without_network_access(self) -> None:
        backend = SMTPBackend()
        smtp = Mock()
        backend.connection = smtp
        message = ConfirmationMessage('Subject', self.signed_body, 'from@example.com', ['to@example.com'])
        self.assertEqual(backend.send_messages([message]), 1)
        wire = smtp.sendmail.call_args.args[2]
        self.assertIn(b'\r\n', wire)
        self.assertEqual(BytesParser(policy=policy.default).parsebytes(wire).get_content_type(), 'multipart/signed')


class TestHighlightDiffTable(TestCase):
    """Tests for the rendering of annotated solution diffs."""

    def render(self, original: str, anotated: str, filename: str) -> str:
        differ = difflib.Differ()
        diff = "\n".join(l.strip("\n") for l in differ.compare(original.splitlines(), anotated.splitlines()))
        return colorize_diff_table(diff, filename)

    def test_empty_diff(self) -> None:
        self.assertEqual(colorize_diff_table("", "Hello.java"), "")

    def test_line_numbers_match_the_number_of_code_lines(self) -> None:
        html = self.render("a = 1\nb = 2\n", "a = 1\nb = 3\nc = 4\n", "t.py")
        linenos = html.split('<td class="code">')[0]
        # one number per code line, the "? " hint lines of difflib do not count
        self.assertEqual(linenos.count('<span class="normal">'), 4)
        self.assertIn('<span class="normal">4</span>', linenos)
        self.assertNotIn('<span class="normal">5</span>', linenos)

    def test_syntax_highlighting_is_not_confused_by_the_diff_markers(self) -> None:
        html = self.render("// comment\n", "int x = 0;\n", "Hello.java")
        # the leading +/- must neither end up inside a token nor be highlighted
        self.assertIn('<span class="c1">// comment</span>', html)
        self.assertIn('<span class="kt">int</span>', html)
        self.assertNotIn('<span class="o">-</span>', html)
        self.assertNotIn('<span class="o">+</span>', html)

    def test_changed_lines_get_a_css_class(self) -> None:
        html = self.render("a = 1\n", "a = 1\nb = 2\n", "t.py")
        self.assertIn('<div class="changed added">', html)

    def test_changed_characters_get_a_css_class(self) -> None:
        html = self.render('s = "Hello"\n', 's = "Hello World"\n', "t.py")
        self.assertIn('<span class="addedChar"> World</span>', html)

    def test_html_entities_count_as_one_character(self) -> None:
        html = self.render("a = b & c;\n", "a = b && c;\n", "T.java")
        self.assertIn('<span class="addedChar">&amp;</span>', html)

    def test_unknown_file_type_is_escaped(self) -> None:
        html = self.render("a < b\n", "a > b\n", "unknown.filetype")
        self.assertIn("&lt;", html)
        self.assertNotIn("a < b", html)

    def test_plain_highlighting_fallback_is_escaped(self) -> None:
        for render in (colorize, colorize_table):
            with self.subTest(render=render.__name__):
                with patch('solutions.templatetags.highlight.get_lexer', side_effect=ClassNotFound('unknown')):
                    html = render('<script>alert("x")</script>', 'unknown')
                self.assertIn('&lt;script&gt;', html)
                self.assertNotIn('<script>', html)

    def test_lexer_failures_other_than_missing_lexer_propagate(self) -> None:
        with patch('solutions.templatetags.highlight.get_lexer', side_effect=RuntimeError('lexer failed')):
            with self.assertRaisesRegex(RuntimeError, 'lexer failed'):
                colorize('source', 'file.txt')

    def test_isabelle_symbols_and_diff_alignment(self) -> None:
        html = colorize(r'theory Test imports Main begin lemma "\<forall>x. x = x" by simp end', 'Test.thy')
        self.assertIn('\u2200', html)
        diff = colorize_diff_table('  text \\<open>content\\<close>\n+ lemma "x = x"', 'Test.thy')
        self.assertEqual(diff.count('<span class="normal">'), 2)
        self.assertIn('changed added', diff)


class TestViews(TestCase):
    def setUp(self) -> None:
        self.client.login(username='user', password='demo')
        self.task: Task = Task.objects.all()[0]

    def tearDown(self) -> None:
        pass

    def test_get_solution_list(self) -> None:
        response = self.client.get(reverse('solution_list', args=[self.task.id]))
        self.assertEqual(response.status_code, 200)

    def test_post_solution(self) -> None:
        path = join(dirname(dirname(dirname(__file__))), 'examples', 'Tasks', 'AMI', 'ModelSolution(flat).zip')
        with open(path, 'rb') as f:
            response = self.client.post(reverse('solution_list', args=[self.task.id]), data={
                                'solutionfile_set-INITIAL_FORMS': '0',
                                'solutionfile_set-TOTAL_FORMS': '3',
                                'solutionfile_set-0-file': f
                            }, follow=True)
        self.assertRedirectsToView(response, 'solution_detail')

    def test_post_solution_expired(self) -> None:
        self.task.submission_date = datetime.now() - timedelta(hours=3)
        self.task.save()

        path = join(dirname(dirname(dirname(__file__))), 'examples', 'Tasks', 'AMI', 'ModelSolution(flat).zip')
        with open(path, 'rb') as f:
            response = self.client.post(reverse('solution_list', args=[self.task.id]), data={
                                'solutionfile_set-INITIAL_FORMS': '0',
                                'solutionfile_set-TOTAL_FORMS': '3',
                                'solutionfile_set-0-file': f
                            }, follow=True)
        self.assertEqual(response.status_code, 403)

    def test_get_solution(self) -> None:
        response = self.client.get(reverse('solution_detail', args=[self.task.solution_set.all()[0].id]))
        self.assertEqual(response.status_code, 200)


def test_concurrently(
    times: int,
) -> Callable[[Callable[..., object]], Callable[..., None]]:
    """
    Add this decorator to small pieces of code that you want to test
    concurrently to make sure they don't raise exceptions when run at the
    same time.  E.g., some Django views that do a SELECT and then a subsequent
    INSERT might fail when the INSERT assumes that the data has not changed
    since the SELECT.
    """
    def test_concurrently_decorator(
        test_func: Callable[..., object],
    ) -> Callable[..., None]:
        def wrapper(*args: object, **kwargs: object) -> None:
            exceptions: list[Exception] = []
            import threading
            def call_test_func() -> None:
                try:
                    test_func(*args, **kwargs)
                except Exception as e:
                    exceptions.append(e)
                    raise
            threads: list[threading.Thread] = []
            for _ in range(times):
                threads.append(threading.Thread(target=call_test_func))
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            if exceptions:
                raise Exception('test_concurrently intercepted %s exceptions: %s' % (len(exceptions), exceptions))
        return wrapper
    return test_concurrently_decorator

        # Use like this:
        # Transaction in djangos testcase results in an deadlock so use pythons
        #class MyTest(TestCase):
        #        def testRegistrationThreaded(self):
        #                url = reverse('toggle_registration')
        #                @test_concurrently(15)
        #                def toggle_registration():
        #                        # perform the code you want to test here; it must be thread-safe
        #                        # (e.g., each thread must have its own Django test client)
        #                        c = Client()
        #                        c.login(username='user@example.com', password='abc123')
        #                        response = c.get(url)
        #                toggle_registration()


#from unittest import TestCase as ConcurrentTestCase
#class ConcurentTest(ConcurrentTestCase):
        #""" Will probably result in an error as not all db connections will be closed on table destruction """
        #def setUp(self):
            #self.task = Task.objects.all()[0]

        #def tearDown(self):
            #pass

        #def test_post_solution_concurrently(self):
                #url = reverse('solution_list', args=[self.task.id])
                #@test_concurrently(20)
                #def run():
                        #f = open('/Users/halluzinativ/untitled.c','r')
                        #client = Client()
                        #client.login(username='user', password='demo')
                        #response = client.post(url, follow=True, data={
                                #u'solutionfile_set-INITIAL_FORMS': u'0',
                                #u'solutionfile_set-TOTAL_FORMS': u'3',
                                #u'solutionfile_set-0-file': f
                            #})
                        #self.failUnlessEqual(response.status_code, 200)
                #run()
