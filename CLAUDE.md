# CLAUDE.md

Guidance for coding agents and contributors working on Praktomat.

## What this is

Praktomat is a Django 5.2 application for programming courses: students submit solutions,
checkers run automated tests, and tutors grade the results. Python 3.10–3.14 are tested in CI.
`src/` is the import root: use `from accounts.models import User`, not `from src.accounts...`.

## Repository layout

| Path | Contents |
|---|---|
| `src/accounts/` | Users, tutorials, authentication, and access controls. |
| `src/tasks/` | Tasks, checker orchestration, import/export, and JPlag. |
| `src/solutions/` | Solution uploads, files, downloads, and zip validation. |
| `src/checker/` | Checker framework, checker implementations, compilers, and scripts. |
| `src/attestation/` | Grading and ratings. |
| `src/taskstatistics/` | Statistics, including an unmanaged SQL view and plots. |
| `src/configuration/` | Singleton configuration and text snippets. |
| `src/utilities/` | Safe execution, file operations and serving, test runner, and management commands. |
| `src/settings/` | Mode-specific settings and dynamically loaded defaults. |
| `src/hbrs_tests/` | Additional tests; not an installed app. |
| `src/sessionprofile/` | Disabled phpBB integration; its tests are not run. |
| `src/templates/`, `media/` | Django templates and static assets. |
| `docker-image/`, `wsgi/` | Student-code sandbox image and mod_wsgi entrypoint. |
| `ADR/` | Architecture decision records. |

### Key mechanics

- **Checker registration:** `checker/models.py` imports modules listed in the checker and compiler
  packages' `__all__`. `Task.get_checkers()` discovers `Checker` subclasses, and task admin
  discovers `CheckerInline` subclasses. A new checker needs its module, `__all__` entry, inline,
  migration, and any required templates.
- **Checker execution:** `solution.check_solution()` prepares a sandbox directory and runs
  checkers, each returning a `CheckerResult`. Dependencies from `requires()` are class-based.
  Exceptions are emailed to admins except in debug mode or test runs.
- **External programs:** use `utilities.safeexec.execute_arglist` with an argument list, never
  `shell=True`. It returns an `ExecutionResult` and applies resource limits and, when configured,
  the tester account or safe Docker.
- **Settings:** mode files call `defaults.load_defaults(globals())`; add defaults inside that
  function as `d.NAME = ...`. These dynamically injected settings are not always visible to static
  tools, and module-level constants outside `load_defaults` are not exported.
- **Access:** middleware replaces `request.user` with `accounts.models.User`. Follow the existing
  role helpers and access checks, and test denied paths.
- **Migrations:** generate a new migration for model changes; do not edit existing migrations.
  Keep new migrations linear.
- **Checker support:** ScriptChecker is actively used and must remain tested. Language-toolchain
  checkers are legacy; preserve them when changing shared code.

## Running things

Install system dependencies listed in `.github/workflows/test.yml` and the `en_US.UTF-8` locale,
then install Python dependencies in a virtualenv:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
source .venv/bin/activate
./scripts/check         # static checks, Django checks, and tests
./scripts/check --full  # same tests under branch coverage, plus coverage gates
.venv/bin/python -m ruff check src/path/to/file.py
.venv/bin/python -m pyright --project . --warnings
./src/manage-devel.py migrate && ./src/manage-devel.py runserver
```

Run commands from the repository root. `scripts/check` uses `.venv/bin/python` if available,
otherwise `python3`; set `PYTHON` to override it. It defaults `LANGUAGE` to `en_US:en` and `CI`
to `true`, and adds `src/` to `PYTHONPATH`. The `--full` diff-coverage comparison defaults to
`origin/master`; use `COMPARE_BRANCH` to override it. CI compares with the PR target branch.

Test settings use `../test-data/` relative to the repository root; the directory must be writable.
`utilities.TestSuite.TestSuiteRunner` initializes shared users, a task, a solution, and an
attestation once per run; tests rely on transaction rollback and this shared data. CI installs
the legacy toolchains and runs the same test selection as the script. Existing guards skip the
safe-Docker memory-limit test when disabled and two C upload tests when `CI` is set. Do not remove,
weaken, or skip tests merely to make a run pass; add CI dependencies or an appropriate explicit
guard for new external-tool tests.

## Quality requirements

### Automated gates

| Gate | Requirement |
|---|---|
| Tests | `scripts/check --full` passes on Python 3.10–3.14. |
| Coverage | At least 80% total coverage with branch measurement, and 80% diff coverage. |
| Django | System checks, migration drift, and template validation pass. |
| Lint and formatting | Ruff checks pass; migrations are excluded from formatting. |
| Types | Strict Pyright passes with `--warnings`, targeting Python 3.10. |
| Dependencies | CI runs `pip-audit` as report-only; findings or audit failures do not block CI. |

The blocking checks run through `scripts/check`; only `--full` enforces coverage gates.
Tool configuration is in `pyproject.toml`.

### Code standards

- Fully annotate added or changed functions and methods. Explain any `Any`, scoped type ignore,
  or lint suppression.
- Do not silently swallow exceptions. Avoid star imports, mutable defaults, `%` formatting, and
  `print()` outside management commands; use f-strings.
- Prefer focused tests, including permission and failure paths for security-sensitive code:
  safe execution, uploads and zip handling, protected file serving, and access controls.
- Record significant design decisions in an ADR. Keep changes and formatting scoped to the task.
- Change `README.md` only when absolutely necessary, and keep such changes as compact as possible.

## Definition of Done

1. Run relevant checks and keep the blocking CI gates green; report actual skipped tests.
2. Cover new behavior with tests and fixes with regression tests.
3. Keep total and diff coverage at or above 80%; include migrations for model changes.
4. Follow the code standards above. Make commits only when requested, using short imperative messages.
