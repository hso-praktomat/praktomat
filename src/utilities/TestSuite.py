import functools
import importlib.util
import os
import shutil
import sys
import unittest
from collections.abc import Callable, Iterable
from os.path import dirname, join
from shutil import rmtree
from typing import Any, TypeVar, cast

from django.conf import settings
from django.db.backends.base.base import BaseDatabaseWrapper
from django.test import TestCase as DjangoTestCase
from django.test import tag
from django.test.runner import DiscoverRunner

# a test method or a test class; Any matches the bound of unittest.skip and django.test.tag
T = TypeVar("T", bound=Callable[..., Any])

class TestSuiteRunner(DiscoverRunner):
    testSuiteUploadRoot = join(settings.UPLOAD_ROOT, 'TestSuite')

    def setup_test_environment(self, **kwargs):
        """ Change the upload root to not mess up the production folder """
        super(TestSuiteRunner, self).setup_test_environment(**kwargs)
        settings.UPLOAD_ROOT = self.testSuiteUploadRoot
        # storage object is lazy and is not updated by simply updating the settings
        from django.core.files.storage import default_storage
        default_storage.location = self.testSuiteUploadRoot

    def setup_databases(self, **kwargs: object) -> list[tuple[BaseDatabaseWrapper, str, bool]]:
        """ Prefill database with some testdata. Rollbacks ensure that the database is in the state after create_test_data().
        Rollbacks need to be supported by the database otherwise the db will be flushed after every test.
        This is much quicker than creating everything in setUp() and more flexible than fixtures as you can use files. """
        x = super().setup_databases(**kwargs)
        # Django creates no test database if the selected tests don't need one (only SimpleTestCase)
        if x:
            create_test_data()
        return x

    def teardown_test_environment(self, **kwargs):
        super(TestSuiteRunner, self).teardown_test_environment(**kwargs)
        try:
            rmtree(self.testSuiteUploadRoot)
        except:
            pass

    def suite_result(self, suite: unittest.TestSuite, result: unittest.TextTestResult, **kwargs: object) -> int:
        """ Names the skipped tests at the end of the run; unittest itself only counts them. """
        sys.stderr.write(format_skipped_tests(result.skipped))
        return super().suite_result(suite, result, **kwargs)


def format_skipped_tests(skipped: Iterable[tuple[unittest.TestCase, str]]) -> str:
    """ One line per skipped test with its reason, sorted by test id; empty if nothing was skipped. """
    lines = sorted(f"  {test.id()}: {reason}" for test, reason in skipped)
    if not lines:
        return ""
    return f"Skipped tests ({len(lines)}):\n" + "\n".join(lines) + "\n"


class TestCase(DjangoTestCase):

    def assertRedirectsToView(self, response, view):
        """ Asserts whether the request was redirected to a specific view function. """
        from urllib.parse import urlparse
        from django.urls import resolve
        self.assertTrue(hasattr(response, 'redirect_chain'),
                        msg="Please use client.get(...,follow=True) with assertRedirectsToView")
        self.assertTrue(len(response.redirect_chain) > 0,
                        msg="No redirection found")
        url = response.redirect_chain[-1][0]
        self.assertEqual(resolve(urlparse(url)[2])[0].__name__, view)


REQUIRE_ALL_TOOLS_ENV = "PRAKTOMAT_REQUIRE_ALL_TOOLS"
INCLUDE_DIRS = ("/usr/include", "/usr/local/include")


def missing_requirements(
    executables: Iterable[str] = (),
    headers: Iterable[str] = (),
    modules: Iterable[str] = (),
    paths: Iterable[str] = (),
) -> list[str]:
    """ Returns a description of every requirement that is not available on this system. """
    missing = [f"executable '{e}'" for e in executables if shutil.which(e) is None]
    missing += [f"C header '{h}'" for h in headers
                if not any(os.path.isfile(os.path.join(d, h)) for d in INCLUDE_DIRS)]
    missing += [f"Python module '{m}'" for m in modules if importlib.util.find_spec(m) is None]
    missing += [f"path '{p}'" for p in paths if not os.path.exists(p)]
    return missing


def requires(
    executables: Iterable[str] = (),
    headers: Iterable[str] = (),
    modules: Iterable[str] = (),
    paths: Iterable[str] = (),
    optional: bool = False,
) -> Callable[[T], T]:
    """ Decorator for tests (methods or classes) that depend on external tools.

    Tags the test as 'external' (run `manage-test.py test --exclude-tag external` for the fast subset).
    If a requirement is missing, the test is skipped, unless the environment variable
    PRAKTOMAT_REQUIRE_ALL_TOOLS=1 is set (as in CI): then it fails, so a CI run can never
    turn green just because tools were not installed.

    optional=True is for tests of language toolchains that are not maintained actively
    (e.g. the R, DejaGnu and CUnit/CppUnit checkers): they are additionally tagged
    'optional_toolchain' and are always skipped if a requirement is missing, even in CI. """
    missing = missing_requirements(executables, headers, modules, paths)

    def decorator(test_item: T) -> T:
        test_item = tag("external")(test_item)
        if optional:
            test_item = tag("optional_toolchain")(test_item)
        if not missing:
            return test_item
        reason = "missing " + ", ".join(missing)
        if optional or os.environ.get(REQUIRE_ALL_TOOLS_ENV) != "1":
            return unittest.skip(reason)(test_item)
        if isinstance(test_item, type):
            # let the tests of the class run and fail with their own error messages
            return test_item

        @functools.wraps(test_item)
        def failing_test(self: unittest.TestCase, *args: object, **kwargs: object) -> None:
            self.fail(f"{reason} ({REQUIRE_ALL_TOOLS_ENV}=1)")
        return cast(T, failing_test)

    return decorator



from accounts.models import User, Tutorial
from django.contrib.auth.models import Group
from tasks.models import Task
from solutions.models import Solution, SolutionFile
from attestation.models import Attestation

from datetime import datetime, timedelta

from django.core.files import File

def create_test_data():
    """ Fills the test db with objects needed in the unit tests. """

    # Users & Tutorials
    trainer = User.objects.create_user('trainer', 'trainer@praktomat.com', 'demo')
    trainer.groups.add(Group.objects.get(name='Trainer'))
    trainer.is_staff = True
    trainer.is_superuser = True
    trainer.save()

    tutor = User.objects.create_user('tutor', 'trainer@praktomat.com', 'demo')
    tutor.groups.add(Group.objects.get(name='Tutor'))

    tutorial = Tutorial.objects.create(name='Tutorial 1')
    tutorial.tutors.add(tutor)

    user = User.objects.create_user('user', 'user@praktomat.com', 'demo')
    user.groups.add(Group.objects.get(name='User'))
    user.tutorial = tutorial
    user.mat_number = 11111
    user.save()

    # Tasks
    task = Task.objects.create(
            title = 'Test task',
            description = 'Test description.',
            publication_date = datetime.now() - timedelta(hours=5),
            submission_date =  datetime.now() + timedelta(hours=5)
            #model_solution
            #all_checker_finished = False
            #final_grade_rating_scale =
        )

    # Solutions
    solution = Solution.objects.create(    task = task, author = user )

    solution_file = SolutionFile(solution = solution)
    with open(join(dirname(dirname(dirname(__file__))), 'examples', 'Tasks', 'GGT', 'solutions', 'GgT.java')) as fd:
        solution_file.file.save('GgT.java', File(fd))

    # Attestation
    attestation = Attestation.objects.create(solution = solution, author=tutor) # final, published

def dump(obj):
    """ Kinda like obj.__meta__ but shows more, very usefull for testcase debugging. """
    for attr in dir(obj):
        print("obj.%s = %s" % (attr, getattr(obj, attr)))
