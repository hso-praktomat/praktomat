import io
import unittest
from unittest import mock

from django.test import SimpleTestCase

from utilities.TestSuite import TestSuiteRunner, format_skipped_tests


def _sample_tests() -> type[unittest.TestCase]:
    """ A test class to run inside the tests; defined locally so that test discovery does not find it. """
    class SampleTests(unittest.TestCase):
        def test_runs(self) -> None:
            pass

        @unittest.skip("missing executable 'frobnicate'")
        def test_skipped(self) -> None:
            pass

    return SampleTests


class FormatSkippedTestsTest(SimpleTestCase):

    def test_nothing_skipped(self) -> None:
        self.assertEqual(format_skipped_tests([]), "")

    def test_lists_tests_sorted_with_reasons(self) -> None:
        sample_tests = _sample_tests()
        runs, skipped = sample_tests("test_runs"), sample_tests("test_skipped")
        text = format_skipped_tests([(skipped, "reason b"), (runs, "reason a")])
        self.assertEqual(text, "Skipped tests (2):\n"
                               f"  {runs.id()}: reason a\n"
                               f"  {skipped.id()}: reason b\n")


class TestSuiteRunnerSkipSummaryTest(SimpleTestCase):

    def test_suite_result_names_skipped_tests(self) -> None:
        suite = unittest.TestLoader().loadTestsFromTestCase(_sample_tests())
        result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            failures = TestSuiteRunner(verbosity=0).suite_result(suite, result)
        self.assertEqual(failures, 0)
        self.assertIn("Skipped tests (1):", stderr.getvalue())
        self.assertIn("SampleTests.test_skipped: missing executable 'frobnicate'", stderr.getvalue())
