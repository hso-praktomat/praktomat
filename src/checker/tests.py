import os
from os.path import dirname, join
from django.conf import settings
from utilities.TestSuite import TestCase
from utilities.file_operations import copy_file, InvalidZipFile
import unittest
import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from django.test import RequestFactory, override_settings
from django.contrib import admin
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import User
from checker.basemodels import (
    CheckerEnvironment, CheckerFileField, CheckerResult, check_solution,
    check_with_own_connection, check_multiple, run_checks,
)
from checker.compiler.Builder import program_output_flags
from checker.checker.ScriptChecker import CopyForm, ScriptCheckerInline, WarningScriptCheckerFormSet
from utilities.safeexec import ExecutionResult

from solutions.models import Solution, SolutionFile
from django.core.files import File
from tasks.models import Task
from .compiler import *
from .checker import *


class TestCheckerContracts(TestCase):
    def setUp(self) -> None:
        self.solution: Solution = Solution.objects.all()[0]
        self.env = CheckerEnvironment(self.solution)
        self.addCleanup(shutil.rmtree, self.env.tmpdir())

    def test_environment_source_and_program_contracts(self) -> None:
        self.env.add_source('text.txt', 'text')
        self.env.add_source('binary.dat', b'\x00')
        self.env.add_source('generated.o', None)
        self.assertIn(('text.txt', 'text'), self.env.string_sources())
        self.assertNotIn(('binary.dat', b'\x00'), self.env.string_sources())
        self.assertIn(('generated.o', None), self.env.sources())
        self.assertIsNone(self.env.program())
        self.env.set_program('a program')
        self.assertEqual(self.env.program(), 'a program')
        self.env.set_program(None)
        self.assertIsNone(self.env.program())
        self.assertEqual(self.env.solution(), self.solution)
        self.assertEqual(self.env.user(), self.solution.author)
        self.assertEqual(self.env.task(), self.solution.task)

    def test_generic_results_and_artefacts_cascade_without_changing_fields(self) -> None:
        checker = LineCounter.LineCounter.objects.create(task=self.solution.task, order=1)
        result = checker.create_result(self.env)
        self.assertEqual(result.require_checker(), checker)
        self.assertEqual(result.title(), checker.title())
        self.assertEqual(result.required(), checker.required)
        self.assertEqual(list(checker.results.all()), [result])
        self.assertIsInstance(checker._meta.get_field('results'), GenericRelation)
        result.artefacts.create(filename='empty', file='')
        checker.delete()
        self.assertFalse(CheckerResult.objects.filter(pk=result.pk).exists())
        self.assertFalse(self.solution.checkerresult_set.filter(pk=result.pk).exists())

    def test_missing_or_wrong_generic_checker_is_rejected(self) -> None:
        for result in (CheckerResult(), CheckerResult(checker=self.solution.task)):
            with self.subTest(result=result):
                with self.assertRaisesRegex(ValueError, 'no valid checker'):
                    result.require_checker()

    def test_results_sort_by_checked_checker_and_stop_at_critical_failure(self) -> None:
        self.solution.checkerresult_set.all().delete()
        last = LineCounter.LineCounter.objects.create(task=self.solution.task, order=3)
        critical = LineCounter.LineCounter.objects.create(task=self.solution.task, order=2, critical=True)
        first = LineCounter.LineCounter.objects.create(task=self.solution.task, order=1)
        for checker in (last, critical, first):
            result = checker.create_result(self.env)
            result.set_passed(checker != critical)
            result.save()
        self.assertEqual([result.require_checker().order for result in self.solution.allCheckerResults()], [1, 2])
        self.assertEqual([result.require_checker().order for result in self.solution.publicCheckerResults()], [1, 2])

    def test_checker_file_field_retains_storage_and_migration_contract(self) -> None:
        field = CheckerFileField('File')
        _, path, _, kwargs = field.deconstruct()
        self.assertEqual(path, 'checker.basemodels.CheckerFileField')
        self.assertEqual(kwargs['max_length'], 500)
        self.assertEqual(CheckerFileField(max_length=800).max_length, 800)

    @patch.object(SolutionFile, 'content', side_effect=OSError('unreadable upload'))
    def test_source_loading_failure_does_not_allocate_a_sandbox(self, content: Mock) -> None:
        with tempfile.TemporaryDirectory() as root:
            with override_settings(SANDBOX_DIR=root):
                with self.assertRaisesRegex(OSError, 'unreadable upload'):
                    CheckerEnvironment(self.solution)
            self.assertEqual(os.listdir(root), [])
        content.assert_called()

    @patch('checker.compiler.Builder.execute_arglist')
    def test_compilers_fail_on_exit_timeout_or_oom_without_warning_text(self, execute: Mock) -> None:
        for builder_class in (CBuilder.CBuilder, JavaBuilder.JavaBuilder):
            for exitcode, timed_out, oom_ed in ((1, False, False), (0, True, False), (0, False, True)):
                with self.subTest(builder=builder_class.__name__, result=(exitcode, timed_out, oom_ed)):
                    options: dict[str, object] = {'_output_flags': ''}
                    if builder_class is JavaBuilder.JavaBuilder:
                        options['_main_required'] = False
                    checker = builder_class.objects.create(task=self.solution.task, order=1, **options)
                    execute.return_value = ExecutionResult('', None, exitcode, timed_out, oom_ed)
                    result = checker.run(self.env)
                    self.assertFalse(result.passed)
                    self.assertEqual('Timeout occurred!' in result.log, timed_out)
                    self.assertEqual('Memory limit exceeded' in result.log, oom_ed)

    @patch('checker.compiler.Builder.execute_arglist')
    def test_compilers_pass_clean_success_and_preserve_shared_environment(self, execute: Mock) -> None:
        for builder_class in (CBuilder.CBuilder, JavaBuilder.JavaBuilder):
            with self.subTest(builder=builder_class.__name__):
                options: dict[str, object] = {'_output_flags': ''}
                if builder_class is JavaBuilder.JavaBuilder:
                    options['_main_required'] = False
                checker = builder_class.objects.create(task=self.solution.task, order=1, **options)
                original = checker.environment()
                execute.return_value = ExecutionResult('', None, 0, False, False)
                self.assertTrue(checker.run(self.env).passed)
                self.assertEqual(checker.environment(), original)
                environment = checker.environment()
                environment['TASK_ID_CUSTOM'] = 'changed'
                self.assertEqual(checker.environment(), original)

    @patch('checker.compiler.Builder.execute_arglist')
    def test_compiler_warning_skips_successful_postprocessing(self, execute: Mock) -> None:
        checker = CBuilder.CBuilder.objects.create(task=self.solution.task, order=1)
        execute.return_value = ExecutionResult('source.c:1: warning: example', None, 0, False, False)
        with patch.object(checker, 'post_run') as post:
            result = checker.run(self.env)
        self.assertFalse(result.passed)
        post.assert_not_called()

    def test_output_flags_preserve_quoted_program_and_constant_flags(self) -> None:
        self.assertEqual(program_output_flags('-o %s', 'a program "quoted"'), ['-o', 'a program "quoted"'])
        self.assertEqual(program_output_flags('-o "%s"', 'a program'), ['-o', 'a program'])
        self.assertEqual(program_output_flags('-Dpercent=100% -o=%s', 'a program'), ['-Dpercent=100%', '-o=a program'])
        self.assertEqual(program_output_flags('-o %s', None), ['-o', '%s'])
        self.assertEqual(program_output_flags('-cp "library dir"', 'Main'), ['-cp', 'library dir'])
        self.assertEqual(program_output_flags('-c', None), ['-c'])
        self.assertEqual(program_output_flags('', None), [])
        with self.assertRaises(ValueError):
            program_output_flags('"unclosed', 'Main')

    def test_main_required_helper_calls_instance_method(self) -> None:
        checker = CLinker.CLinker(_main_required=True)
        with patch.object(checker, 'main_search', return_value='main'):
            self.assertTrue(checker.main_check(self.env))
        with patch.object(checker, 'main_search', return_value=''):
            self.assertFalse(checker.main_check(self.env))
        checker = CLinker.CLinker(_main_required=False)
        with patch.object(checker, 'main_search') as search:
            self.assertTrue(checker.main_check(self.env))
        search.assert_not_called()

    def test_linker_object_sources_are_unique_and_discovery_is_idempotent(self) -> None:
        self.env.add_source('first.c', 'source')
        self.env.add_source('second.c', 'source')
        checker = CLinker.CLinker(_file_pattern=r'.*\.o$')
        first = checker.get_file_names(self.env)
        second = checker.get_file_names(self.env)
        self.assertEqual(first, second)
        self.assertEqual(first.count('first.o'), 1)
        self.assertEqual(first.count('second.o'), 1)

    @patch('checker.compiler.CLinker.execute_arglist')
    def test_linker_rechecks_main_for_each_environment(self, execute: Mock) -> None:
        self.env.add_source('first.c', 'source')
        Path(self.env.tmpdir(), 'first.o').touch()
        checker = CLinker.CLinker()
        execute.return_value = ExecutionResult('first.o:0000000d T main', None, 0, False, False)
        self.assertEqual(checker.main_module(self.env), 'first')
        execute.return_value = ExecutionResult('first.o:0000000d T other', None, 0, False, False)
        with self.assertRaises(checker.NotFoundError):
            checker.main_module(self.env)

    @patch('checker.compiler.JavaBuilder.execute_arglist')
    def test_java_main_search_reads_declaration_from_start_and_varargs(self, execute: Mock) -> None:
        Path(self.env.tmpdir(), 'Main.class').touch()
        checker = JavaBuilder.JavaBuilder()
        for signature in ('java.lang.String[]', 'java.lang.String...'):
            execute.return_value = ExecutionResult(
                f'public class Main {{\n  public static void main({signature});\n}}',
                None, 0, False, False,
            )
            self.assertEqual(checker.main_module(self.env), 'Main')
        execute.return_value = ExecutionResult('public static void main(java.lang.String[])', None, 0, False, False)
        with self.assertRaisesRegex(checker.NotFoundError, 'identify the main class'):
            checker.main_module(self.env)

    def test_script_filename_inference_and_invalid_file_values(self) -> None:
        class ScriptForm(CopyForm):
            class Meta:
                model = ScriptChecker.ScriptChecker
                fields = ['filename', 'shell_script']

        form = ScriptForm()
        form.cleaned_data = {
            'filename': '', 'shell_script': SimpleUploadedFile('script.sh', b'echo ok'),
        }
        self.assertEqual(form.clean_filename(), 'script.sh')
        form.cleaned_data['filename'] = 'renamed.sh'
        self.assertEqual(form.clean_filename(), 'renamed.sh')
        form.cleaned_data = {'filename': '', 'shell_script': None}
        self.assertEqual(form.clean_filename(), '')
        form.cleaned_data['shell_script'] = object()
        with self.assertRaises(ValidationError):
            form.clean_filename()

    def test_script_inline_formset_preserves_request_injection(self) -> None:
        request = RequestFactory().get('/admin/')
        request.user = User.objects.get(username='trainer')
        inline = ScriptCheckerInline(Task, admin.site)
        formset_class = inline.get_formset(request, self.solution.task)
        formset = formset_class(instance=self.solution.task)
        assert isinstance(formset, WarningScriptCheckerFormSet)
        self.assertIs(formset.request, request)
        self.assertEqual(formset.model, ScriptChecker.ScriptChecker)

    @patch('checker.checker.ScriptChecker.os.chmod')
    @patch('checker.checker.ScriptChecker.copy_file')
    @patch('checker.checker.ScriptChecker.execute_arglist')
    def test_script_execution_contract_retains_warning_exitcode_and_escaping(
        self, execute: Mock, copy: Mock, chmod: Mock,
    ) -> None:
        checker = ScriptChecker.ScriptChecker.objects.create(
            task=self.solution.task, order=1, shell_script='script.sh',
            arguments='--title "two words"', mount_extra_directories=True,
        )
        for exitcode, timed_out, oom_ed, passed, warning in (
            (0, False, False, True, False),
            (121, False, False, True, True),
            (1, False, False, False, False),
            (121, True, False, False, False),
            (121, False, True, False, False),
        ):
            with self.subTest(exitcode=exitcode, timeout=timed_out, oom=oom_ed):
                execute.return_value = ExecutionResult('<unsafe>', None, exitcode, timed_out, oom_ed)
                result = checker.run(self.env)
                self.assertEqual(result.passed, passed)
                self.assertEqual(result.passed_with_warning, warning)
                self.assertIn('&lt;unsafe&gt;', result.log)
                self.assertEqual(execute.call_args.args[0][1:3], ['--title', 'two words'])
                self.assertTrue(execute.call_args.kwargs['mount_extra_directories'])
        copy.assert_called()
        chmod.assert_called()

    def test_dependency_failure_skips_checker_and_rejects_required_solution(self) -> None:
        prerequisite = CBuilder.CBuilder.objects.create(task=self.solution.task, order=1)
        dependent = LineCounter.LineCounter.objects.create(task=self.solution.task, order=2, required=True)
        result = prerequisite.create_result(self.env)
        result.set_passed(False)
        with patch.object(Task, 'get_checkers', return_value=[prerequisite, dependent]):
            with patch.object(prerequisite, 'run', return_value=result):
                with patch.object(dependent, 'requires', return_value=[CBuilder.CBuilder]):
                    with patch.object(dependent, 'run') as run:
                        run_checks(self.solution, self.env, True)
        run.assert_not_called()
        self.assertFalse(dependent.results.get().passed)
        self.assertIn('required checkers failed', dependent.results.get().log)
        self.assertFalse(self.solution.accepted)

    def test_dependency_success_and_warning_flags_survive_result_saving(self) -> None:
        prerequisite = CBuilder.CBuilder.objects.create(task=self.solution.task, order=1)
        dependent = LineCounter.LineCounter.objects.create(task=self.solution.task, order=2)
        first = prerequisite.create_result(self.env)
        second = dependent.create_result(self.env)
        second.set_passed_with_warning(True)
        second.set_log('a\x00b')
        with patch.object(Task, 'get_checkers', return_value=[prerequisite, dependent]):
            with patch.object(prerequisite, 'run', return_value=first):
                with patch.object(dependent, 'requires', return_value=[CBuilder.CBuilder]):
                    with patch.object(dependent, 'run', return_value=second) as run:
                        run_checks(self.solution, self.env, True)
        run.assert_called_once()
        second.refresh_from_db()
        self.assertEqual(second.log, 'ab')
        self.assertTrue(self.solution.accepted)
        self.assertTrue(self.solution.warnings)

    def test_secondary_run_preserves_existing_result_without_rerunning(self) -> None:
        checker = LineCounter.LineCounter.objects.create(task=self.solution.task, order=1)
        existing = checker.create_result(self.env)
        with patch.object(Task, 'get_checkers', return_value=[checker]):
            with patch.object(checker, 'run') as run:
                run_checks(self.solution, self.env, True, secondary_check=True)
        run.assert_not_called()
        self.assertEqual(list(checker.results.all()), [existing])

    @override_settings(DEBUG=False)
    @patch('checker.basemodels.run_checks', side_effect=RuntimeError('checker failed'))
    def test_checker_failure_cleans_sandbox_and_preserves_exception(self, run: Mock) -> None:
        with tempfile.TemporaryDirectory() as root:
            with override_settings(SANDBOX_DIR=root):
                with self.assertRaisesRegex(RuntimeError, 'checker failed'):
                    check_solution(self.solution, debug_keep_tmp=False)
            self.assertEqual(os.listdir(root), [])
        run.assert_called_once()

    @override_settings(DEBUG=False)
    @patch.object(Solution, 'copySolutionFiles', side_effect=RuntimeError('copy failed'))
    def test_source_copy_failure_cleans_sandbox(self, copy: Mock) -> None:
        with tempfile.TemporaryDirectory() as root:
            with override_settings(SANDBOX_DIR=root):
                with self.assertRaisesRegex(RuntimeError, 'copy failed'):
                    check_solution(self.solution, debug_keep_tmp=False)
            self.assertEqual(os.listdir(root), [])
        copy.assert_called_once()

    @override_settings(DEBUG=True)
    @patch('checker.basemodels.run_checks')
    def test_debug_keep_and_all_finished_behavior(self, run: Mock) -> None:
        with tempfile.TemporaryDirectory() as root:
            with override_settings(SANDBOX_DIR=root):
                check_solution(self.solution, run_all=True, debug_keep_tmp=True)
            self.assertEqual(len(os.listdir(root)), 1)
        self.solution.refresh_from_db()
        self.assertTrue(self.solution.all_checker_finished)
        run.assert_called_once()

    @patch('checker.basemodels.connection.close')
    @patch('checker.basemodels.check_solution', side_effect=RuntimeError('checker failed'))
    def test_worker_connection_closes_after_failure(self, check: Mock, close: Mock) -> None:
        with self.assertRaisesRegex(RuntimeError, 'checker failed'):
            check_with_own_connection(self.solution)
        self.assertEqual(close.call_count, 2)
        check.assert_called_once()

    @override_settings(NUMBER_OF_TASKS_TO_BE_CHECKED_IN_PARALLEL=2)
    @patch('checker.basemodels.connection.close')
    @patch('checker.basemodels.Pool')
    def test_parallel_pool_and_connection_close_after_failure(self, pool: Mock, close: Mock) -> None:
        pool.return_value.__enter__.return_value.map.side_effect = RuntimeError('worker failed')
        with self.assertRaisesRegex(RuntimeError, 'worker failed'):
            check_multiple([self.solution])
        pool.return_value.__exit__.assert_called_once()
        close.assert_called_once()

    @override_settings(DEBUG=False)
    @patch('checker.basemodels.sys.argv', ['worker'])
    @patch('checker.basemodels.mail_admins')
    def test_production_failure_reports_error_and_rejects_required_solution(self, mail: Mock) -> None:
        checker = LineCounter.LineCounter.objects.create(task=self.solution.task, order=1, required=True)
        with patch.object(Task, 'get_checkers', return_value=[checker]):
            with patch.object(checker, 'run', side_effect=RuntimeError('intentional error')):
                run_checks(self.solution, self.env, True)
        result = checker.results.get()
        self.assertFalse(result.passed)
        self.assertIn('unexpected internal error', result.log)
        self.assertFalse(self.solution.accepted)
        mail.assert_called_once()
        self.assertIn('RuntimeError', mail.call_args.args[1])


class TestChecker(TestCase):
    def setUp(self) -> None:
        self.solution: Solution = Solution.objects.all()[0]
        self.task: Task = self.solution.task

    def tearDown(self) -> None:
        pass

    def test_anonymity_checker(self) -> None:
        AnonymityChecker.AnonymityChecker.objects.create(
                task = self.task,
                order = 0
                )
        self.solution.check_solution()

    def test_checkstyle_checker(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'check style', 'check_ws.xml')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit', 'check style', 'check_ws.xml')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        CheckStyleChecker.CheckStyleChecker.objects.create(
                    task = self.task,
                    order = 0,
                    configuration = dest
                    )
        self.solution.check_solution()

    def test_createfile_checker(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'check style', 'check_ws.xml')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit', 'check style', 'createfile.xml')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        CreateFileChecker.CreateFileChecker.objects.create(
                    task = self.task,
                    order = 0,
                    file = dest
                    )
        self.solution.check_solution()
        for checkerresult in self.solution.checkerresult_set.all():
            self.assertTrue(checkerresult.passed, checkerresult.log)

    def test_createfile_override_checker(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'check style', 'check_ws.xml')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit', 'check style', 'createfile.xml')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        CreateFileChecker.CreateFileChecker.objects.create(
                    task = self.task,
                    order = 0,
                    file = dest
                    )
        CreateFileChecker.CreateFileChecker.objects.create(
                    task = self.task,
                    order = 1,
                    file = dest
                    )
        self.solution.check_solution()
        for checkerresult in self.solution.checkerresult_set.all():
            if checkerresult.require_checker().order == 1:
                self.assertFalse(checkerresult.passed, checkerresult.log)

    def test_createfile_zip_checker(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'simple_zip_file.zip')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit', 'simple_zip_file.zip')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        CreateFileChecker.CreateFileChecker.objects.create(
                    task = self.task,
                    order = 0,
                    unpack_zipfile = True,
                    file = dest
                    )
        self.solution.check_solution()
        for checkerresult in self.solution.checkerresult_set.all():
            self.assertTrue(checkerresult.passed, checkerresult.log)

    def test_createfile_illegal_zip_checker(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'badzipfile.zip')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit', 'badzipfile.zip')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        CreateFileChecker.CreateFileChecker.objects.create(
                    task = self.task,
                    order = 0,
                    unpack_zipfile = True,
                    file = dest
                    )
        self.assertRaises(InvalidZipFile, self.solution.check_solution)

    def test_createfile_zip_override_checker(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'simple_zip_file.zip')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit', 'simple_zip_file.zip')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        CreateFileChecker.CreateFileChecker.objects.create(
                    task = self.task,
                    order = 0,
                    unpack_zipfile = True,
                    file = dest
                    )
        CreateFileChecker.CreateFileChecker.objects.create(
                    task = self.task,
                    order = 1,
                    unpack_zipfile = True,
                    file = dest
                    )
        self.solution.check_solution()
        for checkerresult in self.solution.checkerresult_set.all():
            if checkerresult.require_checker().order == 1:
                self.assertFalse(checkerresult.passed, checkerresult.log)



    def test_interface_checker(self) -> None:
        InterfaceChecker.InterfaceChecker.objects.create(
                    task = self.task,
                    order = 0,
                    interface1 = 'Test'
                    )
        self.solution.check_solution()
        # This fails (no good test data)
        for checkerresult in self.solution.checkerresult_set.all():
            self.assertFalse(checkerresult.passed, checkerresult.log)

    def test_linecounter_checker(self) -> None:
        LineCounter.LineCounter.objects.create(
                    task = self.task,
                    order = 0,
                    )
        self.solution.check_solution()
        for checkerresult in self.solution.checkerresult_set.all():
            self.assertTrue(checkerresult.passed, checkerresult.log)

    def test_linewidth_checker(self) -> None:
        LineWidthChecker.LineWidthChecker.objects.create(
                    task = self.task,
                    order = 0,
                    )
        self.solution.check_solution()
        for checkerresult in self.solution.checkerresult_set.all():
            self.assertTrue(checkerresult.passed, checkerresult.log)

    def test_script_checker(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'Power.sh')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit', 'Power.sh')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        ScriptChecker.ScriptChecker.objects.create(
                    task = self.task,
                    order = 0,
                    shell_script = dest
                    )
        self.solution.check_solution()
        for checkerresult in self.solution.checkerresult_set.all():
            self.assertTrue(checkerresult.passed, checkerresult.log)

    def test_script_timeout(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'loop.sh')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit', 'loop.sh')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        with self.settings(TEST_TIMEOUT=1):
            ScriptChecker.ScriptChecker.objects.create(
                task = self.task,
                order = 0,
                shell_script = dest
            )
            self.solution.check_solution()
            for checkerresult in self.solution.checkerresult_set.all():
                self.assertIn('1', checkerresult.log, "Test did not even start?")
                self.assertIn('Timeout occurred!', checkerresult.log, "Test result does not mention timeout")
                # (string 'Timeout occurred!' defined in checker/basemodels.py : CheckerResult.set_log)
                self.assertFalse(checkerresult.passed, "Test succeed (no timeout?)")
                self.assertNotIn('done', checkerresult.log, "Test did finish (no timeout?)")


    @unittest.skipIf('TRAVIS' in os.environ, "ulimit doesn’t seem to work on travis")
    @unittest.skipIf(settings.USESAFEDOCKER, "not yet supported with safe-docker")
    def test_script_filesizelimit(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'largefile.pl')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit', 'largefile.pl')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        with self.settings(TEST_MAXFILESIZE=5):
            ScriptChecker.ScriptChecker.objects.create(
                task = self.task,
                order = 0,
                shell_script = dest
                )
            self.solution.check_solution()
            for checkerresult in self.solution.checkerresult_set.all():
                self.assertIn('Begin', checkerresult.log, "Test did not even start? (%s)" % checkerresult.log)
                self.assertNotIn('End', checkerresult.log, "Test did finish (no timeout?) (%s)" % checkerresult.log)
                #self.assertIn('Timeout occurred!', checkerresult.log, "Test result does not mention timeout")
                # (string 'Timeout occurred!' defined in checker/basemodels.py : CheckerResult.set_log)
                self.assertFalse(checkerresult.passed, "Test succeed (no timeout?)")


    @unittest.skipIf(not settings.USESAFEDOCKER, "only supported with safe-docker")
    def test_script_memorylimit(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'allocate.pl')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit', 'allocate.pl')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        with self.settings(TEST_MAXMEM=1):
            ScriptChecker.ScriptChecker.objects.create(
                task = self.task,
                order = 0,
                shell_script = dest
                )
            self.solution.check_solution()
            for checkerresult in self.solution.checkerresult_set.all():
                self.assertIn('Begin', checkerresult.log, "Test did not even start?")
                self.assertNotIn('End', checkerresult.log, "Test did finish (no timeout?)")
                self.assertIn('Timeout occurred!', checkerresult.log, "Test result does not mention timeout")
                # (string 'Timeout occurred!' defined in checker/basemodels.py : CheckerResult.set_log)
                self.assertFalse(checkerresult.passed, "Test succeed (no timeout?)")

    def test_text_checker(self) -> None:
        TextChecker.TextChecker.objects.create(
                    task = self.task,
                    order = 0,
                    text = 'System.out'
                    )
        self.solution.check_solution()
        for checkerresult in self.solution.checkerresult_set.all():
            self.assertTrue(checkerresult.passed, checkerresult.log)

    def test_dejagnu_checker(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'Tasks', 'GGT', 'solutions', 'javagently', 'Stream.java')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit',  'javagently', 'Stream.java')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        CreateFileChecker.CreateFileChecker.objects.create(
                    task = self.task,
                    order = 0,
                    file = dest,
                    path = "javagently"
                    )
        JavaBuilder.JavaBuilder.objects.create(
                    task = self.task,
                    order = 1,
                    _flags = "",
                    _output_flags = "",
                    _file_pattern = r"^[a-zA-Z0-9_/\\]*\.[jJ][aA][vV][aA]$"
                    )
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'Tasks', 'GGT', 'DejaGnuTestCases', 'default.exp')
        test_defs = join(settings.UPLOAD_ROOT, 'directdeposit', 'DejaGnuTestCases', 'default.exp')
        # circumvent SuspiciousOperation exception
        copy_file(src, test_defs)
        DejaGnu.DejaGnuSetup.objects.create(
                    task = self.task,
                    order = 2,
                    test_defs = test_defs
                    )
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'Tasks', 'GGT', 'DejaGnuTestCases', 'public.exp')
        test_case = join(settings.UPLOAD_ROOT, 'directdeposit', 'DejaGnuTestCases', 'public.exp')
        # circumvent SuspiciousOperation exception
        copy_file(src, test_case)
        DejaGnu.DejaGnuTester.objects.create(
                    task = self.task,
                    order = 3,
                    test_case = test_case
                    )

        self.solution.check_solution()

        # Check if they are all finished, or if one of the dependencies failed.
        for checkerresult in self.solution.checkerresult_set.all():
            self.assertTrue(checkerresult.passed, checkerresult.log)

    def test_c_checker(self) -> None:
        src = join(dirname(dirname(dirname(__file__))), 'examples', 'Hello World.c')
        dest = join(settings.UPLOAD_ROOT, 'directdeposit', 'Hello World.c')
        # circumvent SuspiciousOperation exception
        copy_file(src, dest)
        CreateFileChecker.CreateFileChecker.objects.create(
                    task = self.task,
                    order = 0,
                    file = dest,
                    )
        CBuilder.CBuilder.objects.create(
                    task = self.task,
                    order = 1,
                    _file_pattern = r"^[a-zA-Z0-9_ ]*\.[cC]$"
                    )
        self.solution.check_solution()

        # Check if they are all finished, or if one of the dependencies failed.
        for checkerresult in self.solution.checkerresult_set.all():
            self.assertTrue(checkerresult.passed, checkerresult.log)

    def test_r_checker(self) -> None:
        import mimetypes
        mimetypes.init()
        self.assertTrue(mimetypes.inited)
        # TODO: This is duplicated from solutions/forms.py. Where should this go?
        for (mimetype, extension) in settings.MIMETYPE_ADDITIONAL_EXTENSIONS:
            mimetypes.add_type(mimetype, extension, strict=True)
        solution_file = SolutionFile(solution = self.solution)
        mime_type = mimetypes.guess_type('example.R')[0]
        assert mime_type is not None, "Mimetype for example.R shouldn't be None"
        solution_file.mime_type = mime_type
        # Bughunting for Python 3.9.12 and above
        # at time of bughunting ... uses pysqlite 2.6.0 with SQLite 3.38.3
        # see https://github.com/KITPraktomatTeam/Praktomat/issues/336
        #
        # Unit Tests for R Checker fail : missing mimetype for example.R
        # django.db.utils.IntegrityError: NOT NULL constraint failed: solutions_solutionfile.mime_type
        self.assertEqual(str(mimetypes.types_map['.R']),solution_file.mime_type, "Mimetype for extension R should be guessed right")
        self.assertIsNotNone(solution_file.mime_type, "Mimetype for example.R shouldn't be None")
        with open(join(dirname(dirname(dirname(__file__))), 'examples', 'example.R',)) as fd:
            solution_file.file.save('example.R', File(fd))

        RChecker.RChecker.objects.create(
            task = self.task,
            order = 0,
            )

        self.solution.check_solution()

        try:
            for checkerresult in self.solution.checkerresult_set.all():
                self.assertIn('2', checkerresult.log, "Test did not calculate 1 + 2 (%s)" % checkerresult.log)
                self.assertTrue(checkerresult.passed, checkerresult.log)
                self.assertTrue(checkerresult.artefacts.exists())
                self.assertEqual(checkerresult.artefacts.get().path(), "Rplots.pdf")
        finally:
            solution_file.delete()

    def test_r_checker_2(self) -> None:
        import mimetypes
        mimetypes.init()
        # TODO: This is duplicated from solutions/forms.py. Where should this go?
        for (mimetype, extension) in settings.MIMETYPE_ADDITIONAL_EXTENSIONS:
            mimetypes.add_type(mimetype, extension, strict=True)
        solution_file = SolutionFile(solution = self.solution)
        mime_type = mimetypes.guess_type('example.R')[0]
        assert mime_type is not None, "Mimetype for example.R shouldn't be None"
        solution_file.mime_type = mime_type
        # Bughunting for Python 3.9.12 and above
        # at time of bughunting ... uses pysqlite 2.6.0 with SQLite 3.38.3
        # see https://github.com/KITPraktomatTeam/Praktomat/issues/336
        #
        # Unit Tests for R Checker fail : missing mimetype for example.R
        # django.db.utils.IntegrityError: NOT NULL constraint failed: solutions_solutionfile.mime_type
        self.assertIsNotNone(solution_file.mime_type, "Mimetype for example.R shouldn't be None")
        with open(join(dirname(dirname(dirname(__file__))), 'examples', 'example.R',)) as fd:
            solution_file.file.save('example.R', File(fd))

        RChecker.RChecker.objects.create(
            task = self.task,
            order = 0,
            r_script = 'example.R',
            )

        self.solution.check_solution()

        try:
            for checkerresult in self.solution.checkerresult_set.all():
                self.assertIn('2', checkerresult.log, "Test did not calculate 1 + 2 (%s)" % checkerresult.log)
                self.assertTrue(checkerresult.passed, checkerresult.log)
                self.assertTrue(checkerresult.artefacts.exists())
                self.assertEqual(checkerresult.artefacts.get().path(), "Rplots.pdf")
        finally:
                solution_file.delete()

    def test_r_checker_3(self) -> None:
        import mimetypes
        mimetypes.init()
        # TODO: This is duplicated from solutions/forms.py. Where should this go?
        for (mimetype, extension) in settings.MIMETYPE_ADDITIONAL_EXTENSIONS:
            mimetypes.add_type(mimetype, extension, strict=True)
        solution_file = SolutionFile(solution = self.solution)
        mime_type = mimetypes.guess_type('example.R')[0]
        assert mime_type is not None, "Mimetype for example.R shouldn't be None"
        solution_file.mime_type = mime_type
        # Bughunting for Python 3.9.12 and above
        # at time of bughunting ... uses pysqlite 2.6.0 with SQLite 3.38.3
        # see https://github.com/KITPraktomatTeam/Praktomat/issues/336
        #
        # Unit Tests for R Checker fail : missing mimetype for example.R
        # django.db.utils.IntegrityError: NOT NULL constraint failed: solutions_solutionfile.mime_type
        self.assertIsNotNone(solution_file.mime_type, "Mimetype for example.R shouldn't be None")
        with open(join(dirname(dirname(dirname(__file__))), 'examples', 'example.R',)) as fd:
            solution_file.file.save('example.R', File(fd))

        RChecker.RChecker.objects.create(
            task = self.task,
            order = 0,
            r_script = 'not-example.R',
            )

        self.solution.check_solution()

        try:
            for checkerresult in self.solution.checkerresult_set.all():
                self.assertIn('Could not find expected R script', checkerresult.log, "Test did not complain (%s)" % checkerresult.log)
                self.assertFalse(checkerresult.passed, checkerresult.log)
        finally:
            solution_file.delete()

    def test_r_checker_4(self) -> None:
        import mimetypes
        mimetypes.init()
        # TODO: This is duplicated from solutions/forms.py. Where should this go?
        for (mimetype, extension) in settings.MIMETYPE_ADDITIONAL_EXTENSIONS:
            mimetypes.add_type(mimetype, extension, strict=True)
        solution_file = SolutionFile(solution = self.solution)
        mime_type = mimetypes.guess_type('example.R')[0]
        assert mime_type is not None, "Mimetype for example.R shouldn't be None"
        solution_file.mime_type = mime_type
        # Bughunting for Python 3.9.12 and above
        # at time of bughunting ... uses pysqlite 2.6.0 with SQLite 3.38.3
        # see https://github.com/KITPraktomatTeam/Praktomat/issues/336
        #
        # Unit Tests for R Checker fail : missing mimetype for example.R
        # django.db.utils.IntegrityError: NOT NULL constraint failed: solutions_solutionfile.mime_type
        with open(join(dirname(dirname(dirname(__file__))), 'examples', 'example.R',)) as fd:
            solution_file.file.save('example.R', File(fd))

        solution_file2 = SolutionFile(solution = self.solution)
        mime_type2 = mimetypes.guess_type('example2.R')[0]
        assert mime_type2 is not None, "Mimetype for example2.R shouldn't be None"
        solution_file2.mime_type = mime_type2
        with open(join(dirname(dirname(dirname(__file__))), 'examples', 'example.R',)) as fd:
            solution_file2.file.save('example2.R', File(fd))

        RChecker.RChecker.objects.create(
            task = self.task,
            order = 0,
            )

        self.solution.check_solution()

        try:
            for checkerresult in self.solution.checkerresult_set.all():
                self.assertIn('Multiple R scripts found', checkerresult.log, "Test did not complain (%s)" % checkerresult.log)
                self.assertFalse(checkerresult.passed, checkerresult.log)
        finally:
            solution_file.delete()
            solution_file2.delete()

    def test_keep_file_checker(self) -> None:
        KeepFileChecker.KeepFileChecker.objects.create(
            task = self.task,
            order = 0,
            filename = "GgT.java",
            )

        self.solution.check_solution()

        for checkerresult in self.solution.checkerresult_set.all():
            self.assertTrue(checkerresult.passed, checkerresult.log)
            self.assertTrue(checkerresult.artefacts.exists())
            self.assertEqual(checkerresult.artefacts.get().path(), "GgT.java")

    def test_keep_file_checker_2(self) -> None:
        KeepFileChecker.KeepFileChecker.objects.create(
            task = self.task,
            order = 0,
            filename = "does-not-exist",
            )

        self.solution.check_solution()

        for checkerresult in self.solution.checkerresult_set.all():
            self.assertIn('Could not find file', checkerresult.log, "Test did not complain (%s)" % checkerresult.log)
            self.assertFalse(checkerresult.passed, checkerresult.log)
