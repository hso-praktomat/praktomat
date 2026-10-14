# CLAUDE.md

Guidance for coding agents (and humans) working on this repository: what the project is, the
quality requirements code must meet, and the Definition of Done for every change.

## What this is

Praktomat is a Django 5.2 web app for running programming courses. It is the HS Offenburg fork of
KIT Praktomat. Students upload solutions, automated *checkers* compile and test them in a sandbox,
and tutors grade them (*attestations*). The code is Python ≥ 3.10; CI tests 3.10–3.14. There are
about 12.5k LOC of Python in `src/` (excluding migrations), about 100 migrations, Django
templates in `src/templates/`, and static JS/CSS in `media/`.

## Repository layout

| Path | Contents |
|---|---|
| `src/` | **Import root.** `manage-*.py` live here, so imports are top-level: `from checker.basemodels import Checker`, `from accounts.models import User`. Never write `from src.… import`. |
| `src/settings/` | `defaults.py` plus the per-mode files `devel.py`, `local.py` and `test.py` (see *Settings* below). |
| `src/accounts/` | `User` (a multi-table subclass of `auth.User`, with the role helpers `is_trainer`/`is_tutor`/`is_coordinator`), `Tutorial`, LDAP and Shibboleth login, user import, the `access_denied` view (`views.py`), Shibboleth/local-user decorators. |
| `src/tasks/` | `Task`, checker orchestration (`Task.get_checkers`, `check_all_*`), XML/zip task import/export, JPlag. |
| `src/solutions/` | `Solution` and `SolutionFile` (zip upload is unpacked in `SolutionFile.save`), the upload view and form (zip-bomb checks), downloads. |
| `src/checker/` | The checker framework: `basemodels.py` (`Checker`, `CheckerEnvironment`, `CheckerResult` with a GenericFK, `check_solution`, `run_checks`), `checker/*.py` (one module per checker type, each ending with its admin `…Inline`), `compiler/*.py` (C/C++/Java/Haskell/… builders), `scripts/` (bash wrappers and Java policies). |
| `src/attestation/` | Grading: `Attestation`, `RatingScale`, `Rating`, and a large `views.py`. |
| `src/taskstatistics/` | An unmanaged model on a raw-SQL DB view (window functions, so SQLite ≥ 3.38 is needed), plus pandas/matplotlib boxplots. |
| `src/configuration/` | Singleton `Settings` model (`get_settings()` hits the DB every call) and `Chunk` text snippets. |
| `src/utilities/` | `safeexec.py` (**all execution of student code**), `file_operations.py`, `encoding.py`, `TestSuite.py` (test runner plus shared test data), protected file serving in `views.py`, management commands. Tests in `tests.py`. |
| `src/hbrs_tests/` | Extra tests (CUnit/CppUnit, admin list views, wsgi, locale). Not an installed app. |
| `src/sessionprofile/` | phpBB integration. **Disabled** (commented out in `INSTALLED_APPS`), and its tests are not run. |
| `ADR/` | Architecture decision records named `yyyy-mm-dd-title.md`, with the sections Context and Problem Statement, Options, Decision, Rationale. Write one for significant design decisions. |
| `docker-image/` | The `safe-docker` image that student code runs in. |
| `wsgi/praktomat.wsgi` | mod_wsgi entrypoint. |

### Key mechanics you must know before changing code

- **Checker registration is implicit.**
  - `checker/models.py` star-imports `checker/checker/__init__.py` and `compiler/__init__.py`, whose `__all__` lists the modules.
  - `Task.get_checkers()` finds checkers via `apps.get_app_config('checker').get_models()` plus `issubclass(Checker)`.
  - `tasks/admin.py` builds the inlines from `CheckerInline.__subclasses__()`.
  - A new checker therefore needs all of the following: a module in `checker/checker/`, an entry in `__all__`, a `…Inline` class, a migration, and templates if needed.
- **Checker flow.** `solution.check_solution()` → `basemodels.check_solution` creates a tmpdir in `SANDBOX_DIR` → copies the files → `run_checks` → each `checker.run(env)` returns a `CheckerResult`.
  - Dependencies between checkers are class-based: `requires()` returns classes.
  - Exceptions in checkers are swallowed and mailed to the admins, **except** when `DEBUG` is on or `test` is in `sys.argv`.
- **`utilities/safeexec.execute_arglist`** is the only sanctioned way to run external or student programs. It returns an untyped 5-element list `[output, error, exitcode, timed_out, oom_ed]`.
  - It applies `prlimit`, and optionally `sudo -u tester` (`USEPRAKTOMATTESTER`) or `docker run` (`USESAFEDOCKER`).
  - Always pass argument lists; never use `shell=True`.
- **Settings are injected dynamically.**
  - Each mode file sets the required values (`SITE_NAME`, `PRAKTOMAT_ID`, `BASE_HOST`, `BASE_PATH`, `UPLOAD_ROOT`, `PRIVATE_KEY`, `CERTIFICATE`), then calls `defaults.load_defaults(globals())`. That call fills in every other setting through a `__setattr__` trick.
  - Consequences: static tools cannot see most settings; module-level constants at the bottom of `defaults.py` are **not** exported; some settings exist only in `local.py` and are probed with `hasattr`.
  - When you add a setting, put it inside `load_defaults` as `d.NAME = …`.
  - `settings/local.py` is tracked, but production deployments ([praktomat-docker](https://github.com/hso-praktomat/praktomat-docker)) bring their own `local.py`. A new setting therefore needs a default in `load_defaults`; never rely on it being set in `local.py`.
- **Access control in views.** `request.user` is replaced by `accounts.middleware` with the `accounts.models.User` subclass. There are **no role decorators**. The idiom is:
  - `@login_required` (or `@staff_member_required` for staff-only pages) on the view, then
  - an inline role check with the helpers, e.g. `if not (request.user.is_trainer or request.user.is_tutor or request.user.is_superuser): return access_denied(request)` (`access_denied` is in `accounts/views.py`).
  - Follow this idiom in new views, and test the denied path.
- **Migrations.** After changing a model, run `makemigrations`. **Never edit an existing migration**; it may already have run in production. Add a new one instead. The history contains many merge migrations; keep it linear from now on.
- **Databases.** Production runs on PostgreSQL; development and tests use SQLite. Raw SQL (the DB view in the `taskstatistics` migrations) must work on both, but only SQLite is tested, so keep it portable.
- **Supported vs. legacy checkers.** **ScriptChecker** is actively used and must stay fully tested. The language-toolchain checkers (R, DejaGnu/Java, C/C++ builders, CUnit/CppUnit, Haskell, Isabelle, …) are not actively maintained. Keep them working when you touch shared code, but don't invest in them otherwise.

## Running things

Setup (once):
- **System packages:** `./scripts/install-system-deps.sh` (Debian/Ubuntu; CI uses the same script). It installs the build dependencies for `python-ldap`, `psycopg2` and `mod_wsgi`, the tools that `safeexec` and the ScriptChecker tests use, and the locale `en_US.UTF-8`. `settings/test.py` calls `setlocale` with that locale at import time and aborts without it. Add `--checker-toolchains` to also install R, DejaGnu, JDK 8 and CUnit/CppUnit for the optional checker tests.
- **Python packages:** in the virtualenv `.venv/` in the repo root (git-ignored), which `scripts/check` uses automatically:
  `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`.
  Run the other commands below with `.venv/bin/python` or with the virtualenv activated. If `scripts/check` stops with "lacks the project requirements", this step is missing.
- **Test data directory:** tests write to `$PRAKTOMAT_TEST_DATA`, which defaults to `../test-data/`, a **sibling of the repo root**. It is created automatically. In sandboxes or worktrees, set `PRAKTOMAT_TEST_DATA` to a directory you may write to. For development, use `../debug-data/`.

```bash
# THE check: lint, types, Django checks, tests without external tools (about 20 s)
./scripts/check
# before finishing: all tests under coverage, coverage threshold, diff coverage vs origin/master (about 60 s)
./scripts/check --full
# single app, class or test (add --exclude-tag external to skip tests needing compilers etc.)
./src/manage-test.py test checker
./src/manage-test.py test checker.tests.TestChecker.test_script_timeout
# individual tools (configured in pyproject.toml)
ruff check src/path/to/file.py
mypy src
# dev server (SQLite database and uploads in ../debug-data/); create a login once with createsuperuser
./src/manage-devel.py migrate && ./src/manage-devel.py createsuperuser && ./src/manage-devel.py runserver
```

`scripts/check` uses `$PYTHON` (default `.venv/bin/python` if it exists, else `python3`) and compares
against `$COMPARE_BRANCH` (default `origin/master`). For ruff and mypy it prints the total count plus
all findings in the files you changed, including findings that were already there. If a report-only
tool cannot run at all (not installed, crash, config error), the check fails; pip-audit, which needs
the network, only warns.

The test runner is `utilities.TestSuite.TestSuiteRunner`. It relocates `UPLOAD_ROOT` to
`…/TestSuite`, and creates the users `trainer`, `tutor` and `user` (all with password `demo`) plus one
task, one solution and one attestation **once per run**. Tests rely on per-test transaction rollback.
Even tests that subclass plain `django.test.TestCase` depend on this data. Tests that need no database
should subclass `django.test.SimpleTestCase`. At the end of a run, the runner prints a
`Skipped tests (N):` list with the reason for each skip.

**Environment-dependent tests.** Tests that need external tools are marked with
`@requires(executables=…, headers=…, modules=…, paths=…, optional=…)` from `utilities/TestSuite.py`,
which also tags them `external`.
- When a requirement is missing, the test is **skipped**, and the reason names the missing tool.
- With `PRAKTOMAT_REQUIRE_ALL_TOOLS=1`, which CI sets, the test **fails** instead.
- **Exception:** tests marked `optional=True`, which are additionally tagged `optional_toolchain`, are always skipped when their tool is missing. They cover the legacy checker toolchains, and CI does not install those.

Use `@requires` for every new test that runs an external program. Use `optional=True` only for tests of
legacy checker toolchains.

| Tests | Need | In CI |
|---|---|---|
| `checker.tests.test_script_checker`, `test_script_timeout`, `test_script_filesizelimit` | `bash`, `perl`, `seq`, `prlimit`, `pkill` | required |
| `tasks.tests.TestTaskImportAndUploadWithScriptChecker` (import → upload → ScriptChecker) | `bash`, `grep`, `prlimit` | required |
| `hbrs_tests.test_wsgi` | `mod_wsgi` (pip; needs `apache2-dev`) plus a `../env` symlink to the virtualenv | required |
| `hbrs_tests.test_systemlocale` (not marked) | `LANG` containing UTF-8, and `LANGUAGE` set | required |
| `checker.tests.test_script_memorylimit` | `USESAFEDOCKER=True` | always skipped in test settings |
| `checker.tests.test_dejagnu_checker` | `javac`, `/usr/bin/runtest` | optional |
| `checker.tests.test_c_checker` | `gcc` | optional |
| `checker.tests.test_r_checker*` | `Rscript` | optional |
| `hbrs_tests.test_CUnitCppUnit_Checker`, C upload tests | `gcc`, CUnit headers, `fakechroot`, `bindfs`; also skipped whenever `CI` is set (`cTestrunner` hard-codes a chroot path) | optional |
| `hbrs_tests.test_CUnitCppUnit_Checker`, C++ upload tests | `c++`, CppUnit headers | optional |

The fast subset without any external tool is `./src/manage-test.py test --exclude-tag external <apps…>`.
To reproduce exactly what CI tests, use `--exclude-tag optional_toolchain`.

Never make a failing test pass by deleting it, weakening it, or adding `@requires`/skips for a
tool that is actually installed.

## Quality requirements

### Automated gates

All gates run through `scripts/check`; their configuration lives in `pyproject.toml`. The roadmap for
tightening them is in [static_analysis.md](static_analysis.md).

| Gate | Rule | Enforcement |
| --- | --- | --- |
| Tests | The whole suite passes. Tests skipped for a missing tool are named in your summary. | blocking |
| Coverage | Total branch coverage ≥ `fail_under` in `pyproject.toml`, measured as in CI, i.e. without the optional toolchain tests. | blocking (`--full`) |
| Diff coverage | ≥ 80 % of the lines you changed are covered (diff-cover against `$COMPARE_BRANCH`). | blocking (`--full`) |
| Django | `check`, `makemigrations --check --dry-run` and `validate_templates` report no issues. | blocking |
| Lint | ruff with the rule set in `pyproject.toml`. **No new findings** in the files you change; fix existing findings on the lines you touch. | report-only: `scripts/check` lists the findings in changed files |
| Types | mypy + django-stubs with the config in `pyproject.toml`. **No new errors** in the files you change; fix existing errors in code you touch. | report-only: `scripts/check` lists the errors in changed files |
| Formatting | Not enforced. **Do not reformat code you don't change**; reformatting bloats diffs. | — |
| Dependencies | pip-audit reports no known vulnerabilities. | report-only (`--full`) |

### Code standards

- **Typing.**
  - Every function or method you add or change gets complete annotations (parameters and return type), using modern syntax (`list[str]`, `X | None`).
  - No `Any` or `# type: ignore` without a comment explaining why. Scope ignores to an error code, e.g. `# type: ignore[attr-defined]`.
- **Error handling.** No bare `except:` or blind `except Exception:` that swallows errors silently.
- **Style.**
  - No star imports, mutable default arguments, `%`-formatting, or `print()` outside management commands.
  - Use f-strings.
  - Suppress a lint finding only with `# noqa: CODE  <reason>`.
- **External programs** run only through `utilities/safeexec.execute_arglist`, with argument lists, never `shell=True`.
- **Settings.** New settings go inside `load_defaults` in `settings/defaults.py` as `d.NAME = …`.
- **Tests.**
  - Prefer focused tests, e.g. checker logic with a mocked `execute_arglist`, over full compiler runs.
  - Tests that run an external program use `@requires`.
  - Never delete, skip or weaken an existing assertion to make a change pass.
- **Security-sensitive code** needs explicit tests for its permission and failure paths. This covers `utilities/safeexec.py`, upload/zip handling in `solutions/` and `utilities/file_operations.py`, file serving in `utilities/views.py`, and the access checks of views (anonymous, `user`, `tutor`, `trainer`).

## Definition of Done

A change is done only when **all** of the following hold:

1. **`./scripts/check --full` exits 0.** In your summary, name every test that was skipped for a missing tool (copy them from the `Skipped tests` list in the test output).
2. **No regressions in the report-only gates:** no new ruff findings and no new mypy errors in the files you changed.
3. **Tests.**
   - New behaviour comes with new tests.
   - Every bug fix comes with a regression test that fails without the fix.
4. **Coverage.** If total coverage rises by 2 points or more above `fail_under`, raise `fail_under` in `pyproject.toml`; never lower it.
5. **The code standards above are met** for all added or changed code.
6. **Models.** If you changed a model, the migration is included.
7. **Scope.**
   - No mass reformatting or unrelated cleanups mixed into a functional change.
   - Diffs stay reviewable.
   - Significant design decisions get an ADR in `ADR/`.
8. **Git: agents do not commit.** The maintainer reviews and commits every change.
   - Leave your changes uncommitted in the working tree. Don't run `git commit`, `git push`, or anything that rewrites history or discards work (`rebase`, `reset --hard`, `stash drop`, `checkout -- <file>`), unless the maintainer explicitly asks for it in the current task.
   - Don't stage unrelated files. The untracked `.claude/`, `.devcontainer/`, `.mcp.json` and `.vscode/` are personal settings.
   - End your summary with a proposed commit message: imperative, capitalised, at most 72 characters in the first line (e.g. `Fix NameError in ScriptChecker.clean_filename`), and a short body if the reason isn't obvious.
