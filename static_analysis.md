# Static analysis, typing and tests: plan and status

This is the single source of truth for making Praktomat safe to develop with coding agents:
a strong, tool-enforced Definition of Done with tests, coverage, linting and static typing.
[CLAUDE.md](CLAUDE.md) describes the project, its quality requirements and the Definition of Done as
they are *now*; this file holds the plan, the decisions, the progress and the analysis findings.
When a gate changes, update the quality requirements and the Definition of Done in CLAUDE.md.

---

## 0. Status at a glance (handoff, 2026-10-13)

| Phase | Topic                                                                                                        | Status                                                                                            |
| ----- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| 0     | Reproducible environment, `scripts/check`, CI on the same script                                             | ✅ **done, uncommitted** (§0.1)                                                                   |
| 1     | One-shot reformat with `ruff format` + format gate, then fix the confirmed latent bugs with regression tests | ⏭️ **next** (§5, Phase 1)                                                                         |
| 2     | Lint gate (ruff)                                                                                             | ☐ open, report-only for now                                                                       |
| 3     | Type-checking infrastructure, mypy gate at zero                                                              | ☐ open, report-only for now                                                                       |
| 4     | Typing ratchet, module by module                                                                             | ☐ open                                                                                            |
| 5     | Tests and coverage ratchet                                                                                   | 🟡 partly: ratchet active (57 %), diff coverage 80 % active, new tests still to write             |
| 6     | CI, hooks, agent integration                                                                                 | 🟡 partly: CI runs `scripts/check --full`; no separate static job, pre-commit or Claude hooks yet |

### 0.1 Where the work stands

- **Nothing is committed yet.** All Phase 0 work is in the working tree of `master`, on top of `b2ad432d`.
- **Changed files:**
  - New: `CLAUDE.md`, `static_analysis.md`, `pyproject.toml`, `requirements-dev.txt`, `scripts/check`, `scripts/install-system-deps.sh`.
  - Modified: `.github/workflows/test.yml`, `.gitignore`, `src/settings/test.py`, `src/utilities/TestSuite.py`, `src/tasks/tests.py`, `src/checker/tests.py`, `src/hbrs_tests/test_CUnitCppUnit_Checker.py`, `src/hbrs_tests/test_wsgi.py`.
  - The untracked `.claude/`, `.devcontainer/`, `.mcp.json` and `.vscode/` are personal editor/agent settings. They are **not** part of this work; do not commit them.
- **Verified locally** (Python 3.12, all checker toolchains installed, mod_wsgi missing): `./scripts/check --full` is green, with 113 tests, 6 skipped, coverage 62 % and diff coverage 93 %. The toolchain-free subset that CI runs passes as well (102 tests).
- **Not verified:** the GitHub Actions workflow. It has not run yet because nothing is pushed. The likely trouble spots are:
  - `pip install -r requirements-dev.txt` on Python 3.10 and 3.14 (stub packages and the mypy pin).
  - `scripts/install-system-deps.sh` on the `ubuntu-latest` runner.
  - mod_wsgi plus the `../env` symlink under strict mode: the wsgi tests are not optional, so CI fails if they can't run.

### 0.2 Next actions for whoever picks this up

1. **Land Phase 0.**
   - Create a branch (e.g. `static-analysis-phase0`), commit the files listed above, push, and open a PR.
   - Watch CI and fix what breaks. Verify that the CI coverage is ≥ 57 %, which is `fail_under`.
   - Merge only when CI is green on all Python versions.
2. **Phase 1**, in the order of §5. Start with the one-shot reformat (step 1a); it goes first so that every later diff is already formatted. Then fix the bugs, beginning with `utilities/safeexec.py`.
3. **Settle the open decisions** in §2.2 with the maintainers. None of them blocks Phase 1.
4. After each phase, tick the checklist below, and update §0 and §6. If a gate changed, also update *Quality requirements* and *Definition of Done* in CLAUDE.md.

---

## 1. Goal

Coding agents can only be trusted to change code autonomously when a single, fast, deterministic
command tells them and reviewers whether a change is acceptable:

```
./scripts/check          # inner loop: lint + types (report-only for now), Django checks, tests without external tools (~40 s)
./scripts/check --full   # before merge and in CI: all tests under coverage, coverage threshold, diff coverage (~60 s)
```

Target gates, and where each stands:

| Gate          | Tool                                                    | Target                                                                 | Today                                                          |
| ------------- | ------------------------------------------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------- |
| Lint          | ruff (curated rule set in `pyproject.toml`)             | zero findings                                                          | report-only, 1005 findings (Phase 2)                           |
| Format        | `ruff format`                                           | zero diffs                                                             | not checked yet; one-shot reformat + gate in Phase 1 (D1)      |
| Types         | mypy + django-stubs                                     | zero errors; strict modules never regress; changed functions annotated | report-only, 433 errors (Phases 3 and 4)                       |
| Django        | `check`, `makemigrations --check`, `validate_templates` | zero issues                                                            | ✅ enforced                                                    |
| Tests         | Django test runner                                      | all pass; required tools missing in CI → fail                          | ✅ enforced                                                    |
| Coverage      | coverage.py                                             | total ≥ ratchet                                                        | ✅ enforced, `fail_under = 57`                                 |
| Diff coverage | diff-cover vs `origin/master`                           | ≥ 80 % of changed lines                                                | ✅ enforced locally (skipped in CI: shallow checkout, Phase 6) |
| Dependencies  | pip-audit                                               | informational, later blocking                                          | report-only, currently clean                                   |

**Guiding principle: ratchet, don't big-bang.** The code base has about 12.5k LOC with almost no
annotations. Every gate starts at the current baseline, blocks regressions right away, and gets
stricter module by module.

---

## 2. Decisions

### 2.1 Decided

| #   | Date                           | Decision                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| --- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | 2026-09-29, revised 2026-10-13 | **Formatting:** at first (2026-09-29) no format check, so as not to require reformatting the code. **Revised 2026-10-13: the one-shot reformat with `ruff format` is the first step of Phase 1**, followed directly by a blocking `ruff format --check`. Until that commit lands, agents must not reformat code they don't change.                                                                                                                                                                                                                                                                                                                                   |
| D2  | 2026-10-13                     | **The checker toolchains R, DejaGnu/Java, C and CUnit/CppUnit are not actively maintained.** Their tests are `@requires(..., optional=True)`: they are skipped when the tool is missing, even in CI, and are tagged `optional_toolchain`. CI does not install the toolchains; locally, `scripts/install-system-deps.sh --checker-toolchains` does. **ScriptChecker stays fully supported**, and its tests are required in CI. The import → upload → check flow is covered by `tasks.tests.TestTaskImportAndUploadWithScriptChecker` instead of the C++ tests. Consequence: making `cTestrunner` work (fakechroot, bindfs, a hard-coded chroot path) is out of scope. |
| D3  | 2026-10-13                     | **The coverage ratchet is measured the way CI measures it**, without the optional toolchains: `fail_under = 57`. It was 61 % while the toolchain tests ran; that was not a real loss of tests.                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| D4  | 2026-09-28                     | **mypy + django-stubs is the type gate, not pyright.** pyright has no Django plugin: 161 of its 270 errors were ORM noise. Pylance remains fine as an editor aid.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| D5  | 2026-09-28                     | **Keep Django's test runner.** `TestSuiteRunner` provides shared test data. pytest-django is optional and not planned.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| —   | upstream                       | The Pygments pin (`~=2.7.0`) was lifted on `master` (`99c648fb`, now `~=2.19`). The former open question about it is gone.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |

### 2.2 Open (need a maintainer)

1. **Settings typing (Phase 3).**
   - Recommended: the typed shim `settings/typecheck.py`, see §4.1.
   - Alternative: restructure the settings conventionally. That touches `local.py` in praktomat-docker and needs an ADR.
2. **`sessionprofile` app.** It is disabled in `INSTALLED_APPS` and its tests never run. Delete it, or revive it and add it to the test app list?
3. **Public task statistics.** `taskstatistics/views.py:192,210` (`/tasks/statistic`) have no login requirement and handle anonymous users explicitly. Confirm this is intended; Phase 5's permission matrix will encode the answer.
4. **Coverage target and pace.** Proposed: 80 % total within 6 months; 80 % of changed lines already applies.

---

## 3. Tool choices

- **ruff** for linting. It replaces flake8, isort, pyupgrade and bandit (its `S` rules) in one fast binary. Also **`ruff format`** as the formatter (Black-compatible), from Phase 1 on (D1).
- **mypy + django-stubs** (`django-stubs[compatible-mypy]==5.2.9`, the Django 5.2 line). The plugin understands models, managers, related names and settings (D4).
- **Django test runner + coverage.py + diff-cover.** A total threshold alone lets new untested code slip in under a high average; diff-cover measures the lines a change touched.
- **pip-audit** for dependency CVEs.
- **Not used:** separate bandit, pylint or flake8 (they overlap with ruff), and pytest (D5).
- Versions are pinned in `requirements-dev.txt`. Config lives in `pyproject.toml`, which holds tool config only; Praktomat is not packaged.

---

## 4. Structural blockers for typing (solve in Phase 3)

These must be solved first, otherwise mypy stays noisy and agents learn to ignore it.

1. **Dynamic settings** (about 140 of the mypy errors).
   - The problem: `defaults.load_defaults(globals())` injects about 140 settings through `globals()` and a `__setattr__` trick, which django-stubs cannot see. The same mechanism silently drops the constants defined at module level in `defaults.py`; that is the `DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_*` bug, fixed in Phase 1.
   - **Recommended:** add `src/settings/typecheck.py`. It does `from .test import *` and then gives *bare annotations* for every setting, e.g. `TEST_TIMEOUT: int`. Set `django_settings_module = "settings.typecheck"` in `pyproject.toml`. At runtime the star import supplies the values; mypy reads the annotations.
   - Add a parity test, so that a setting cannot exist at runtime without an annotation, or the other way round.
2. **`request.user` is the `accounts.models.User` subclass**, swapped in by `accounts/middleware.py`.
   - The problem: django-stubs types `request.user` as `auth.User | AnonymousUser`, so about 90 uses of `is_trainer`, `is_tutor`, `is_coordinator` and `is_user` fail.
   - The fix: add `class AuthenticatedRequest(HttpRequest): user: accounts.models.User` in `accounts/typing.py`, and annotate the views guarded by `@login_required`.
   - Also give `accounts/decorators.py` `functools.wraps` and a `ParamSpec` signature.
3. **`safeexec.execute_arglist` returns an untyped 5-element list**, unpacked positionally at about 20 call sites, with `output: str` but `error: bytes | None`.
   - Return an `ExecResult(NamedTuple)` instead. Tuple unpacking stays compatible. Do this in Phase 1.
4. **The checker plugin architecture.**
   - Type the abstract API on `Checker`: `run(self, env: CheckerEnvironment) -> CheckerResult`, `title() -> str`, `requires() -> list[type[Checker]]`. Then fix the about 46 incompatible overrides.
   - Wrap the GenericForeignKey `CheckerResult.checker` in a typed accessor.
   - Make `Task.get_checkers` narrow to `type[Checker]`.
5. **Star imports** (22). 13 checker modules get `os` or `settings` only via `from utilities.file_operations import *`. Replace them with explicit imports. This is a prerequisite for meaningful F405/F403 and mypy results.

---

## 5. Phases (checklists)

Effort estimates assume one developer working with an agent.

### Phase 0: Reproducible environment and single entry point — ✅ done (uncommitted)

- [x] `requirements-dev.txt` with pinned tools: ruff, django-stubs + mypy, stub packages, coverage, diff-cover, pip-audit.
- [x] `pyproject.toml`: ruff lint rules (the Phase 2 target set), mypy config, coverage config with `fail_under`.
- [x] `PRAKTOMAT_TEST_DATA` overrides the test `UPLOAD_ROOT`; the directory is created automatically.
- [x] `@requires(executables=…, headers=…, modules=…, paths=…, optional=…)` in `utilities/TestSuite.py`. It tags tests `external` (and `optional_toolchain`). A missing tool → skip; with `PRAKTOMAT_REQUIRE_ALL_TOOLS=1` → fail, except for `optional=True`.
- [x] Applied to: the ScriptChecker tests (required); the wsgi tests (required); the R, DejaGnu, C and CUnit/CppUnit tests (optional, D2).
- [x] New end-to-end test `tasks.tests.TestTaskImportAndUploadWithScriptChecker`: export → admin import → student upload → required ScriptChecker passes or fails.
- [x] `scripts/check [--full]` and `scripts/install-system-deps.sh [--checker-toolchains]`.
- [x] CI uses both scripts, runs the tests once under coverage, and sets `PRAKTOMAT_REQUIRE_ALL_TOOLS=1`.
- [ ] **Commit, push, and get CI green** (§0.2).

Deviations from the original plan:
- No format step yet (D1); it is added in Phase 1, step 1a.
- No `--parallel`: `TestSuiteRunner` creates the shared test data after Django clones the test DBs.
- mypy has no `python_version` setting, because the numpy stubs need ≥ 3.12 syntax.
- The personal devcontainer config is not changed; run `scripts/install-system-deps.sh` inside it.

### Phase 1: One-shot reformat, then fix the confirmed latent bugs (≈ 2–3 days) — ⏭️ next

#### Step 1a: One-shot reformat with `ruff format` (≈ ½ day). Do this first.

It comes first so that the bug-fix diffs, and everything agents write afterwards, are already in
the final format, and no functional change ever mixes with reformatting. Today 103 of 123 files
would change.

- [ ] **Coordinate open branches.** On 2026-10-13 only two remote branches were unmerged into `master`, each 1 commit ahead: `origin/deadline-extensions` (2023-01-10, Hannes Braun) and `origin/djangoUpdate` (2026-03-12, Simon Roesch). Merge or close them first if possible; otherwise tell their owners about the rebase recipe below. Re-check with `git branch -r --no-merged master`.
- [ ] **Formatter config** in `pyproject.toml`:
  ```toml
  [tool.ruff.format]
  line-ending = "lf"   # also converts the 3 CRLF files in src/sessionprofile/
  ```
  `line-length = 120` and the migrations exclusion are inherited from `[tool.ruff]`. Keep ruff's defaults otherwise: double quotes, spaces, which also removes the 38 tab-indented lines.
- [ ] **One dedicated commit** containing only `ruff format src` plus the config. No other changes; the formatter is AST-preserving.
  - [ ] Before and after the commit, `./scripts/check --full` must be green, with the same test count.
  - [ ] Check that `ruff format --check src` exits 0.
  - **Diff coverage does not apply to this commit.** A reformat touches almost every line, including uncovered ones, so the 80 % gate fails by design. To verify the reformat commit, run `COMPARE_BRANCH=HEAD ./scripts/check --full` (an empty diff); all other gates still apply. Land the reformat **before** diff coverage is enabled in CI (Phase 6).
  - A trial run on 2026-10-13 (scratch copy of `b2ad432d` + Phase 0) changed 104 files (+6712/−4360 lines) and converted the CRLF files. The same 113 tests passed, at the same 62 % coverage, and `ruff format --check` was clean afterwards. Only the diff-coverage gate failed, as expected.
- [ ] **`.git-blame-ignore-revs`** with the hash of the reformat commit, and a comment line describing it.
  - GitHub's blame view honours it automatically.
  - Locally: `git config blame.ignoreRevsFile .git-blame-ignore-revs`. Mention this in CLAUDE.md.
- [ ] **Format gate:** add a blocking `run "ruff format" "$PYTHON" -m ruff format --check src` step to `scripts/check`, before ruff check. CI then enforces it automatically via `scripts/check --full`.
- [ ] **Update CLAUDE.md:** in the *Automated gates* table, change the Formatting row to "`ruff format`; run it on the files you change. Blocking."
- [ ] **Rebase recipe for branches** started before the reformat. Let `<fmt>` be the reformat commit:
  ```bash
  git checkout my-branch
  git merge <fmt>~1                        # bring the branch up to just before the reformat
  ruff format src && git commit -am "Apply ruff format"
  git merge -X ours <fmt>                  # take the branch's (already formatted) side on conflicts
  ruff format --check src                  # must be clean; then run ./scripts/check --full
  ```

#### Step 1b: Fix the confirmed latent bugs (≈ 1–2 days)

Every fix comes with a regression test that fails before the fix. Details and line numbers are in
§7.4; they were re-verified against `b2ad432d`.

- [ ] **`utilities/safeexec.py`**, the highest priority:
  - [ ] Stop mutating `os.environ` (line 48): build a copied environment instead. Add a test that runs a command with an extra variable and asserts `os.environ` is unchanged.
  - [ ] Remove the mutable defaults `environment_variables={}` and `extradirs=[]` (line 40).
  - [ ] Return an `ExecResult` NamedTuple instead of a list (§4.3).
  - [ ] Decode program output tolerantly (`errors="replace"`, line 142); test with non-UTF-8 output.
  - [ ] Fix the possibly unbound `container_name`/`volumes` and the `'f{d}'` f-string typo.
  - [ ] Bring `safeexec.py` coverage from 28 % to at least 70 %. Test timeouts and file-size limits with tiny real commands, and the docker argument list with `subprocess` mocked.
- [ ] **`DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_1..5`** (`settings/defaults.py:455`): move them into `load_defaults` (`d.… = None`). Add a test that `mount_extra_directories` works without them being set in the site settings.
- [ ] **Crash bugs:**
  - [ ] `checker/checker/ScriptChecker.py:162`: `shell_script` → `file`. ScriptChecker is supported, so this one matters.
  - [ ] `attestation/views.py:250`: undefined `published`.
  - [ ] `solutions/models.py:272`: undefined `index` (JPlag export with anonymous attestation).
  - [ ] `utilities/encoding.py:26`: wrong `UnicodeDecodeError` constructor.
  - [ ] `checker/checker/RChecker.py:113` (`%` without a placeholder) and `checker/checker/IsabelleChecker.py:41` (`setting.` typo). These are cheap one-liners, even though the checkers are unmaintained (D2).
- [ ] **Dead code:** `Builder.main_check` (`checker/compiler/Builder.py:39`); the management commands `install_demo_db` and `update_model_graph` (they use `handle_noargs`, which was removed in Django 1.10). Port them or delete them.
- [ ] **Broken tests:**
  - [ ] `accounts/tests.py:81` redefines `test_testgroup_set_group` from line 61. Rename one of them.
  - [ ] `hbrs_tests/test_CUnitCppUnit_Checker.py:36` defines `teatDown`; it should be `tearDown`.
  - [ ] `checker/tests.py` `test_anonymity_checker` and `test_checkstyle_checker` have no assertions.
  - [ ] Decide on `sessionprofile` (§2.2).
- [ ] After the phase: raise `fail_under` if coverage went up by ≥ 2 points.

### Phase 2: Lint gate (≈ 2–3 days, mostly mechanical) — ☐ open

The rule set is already in `pyproject.toml`; `scripts/check` reports it but does not block.

- [ ] Bring each rule group to zero, one commit per group:
  - [ ] `F`: undefined names, unused imports and variables.
  - [ ] `E722`/`BLE`: bare and blind excepts.
  - [ ] `B`: bugbear.
  - [ ] The `S` security subset.
  - [ ] `DJ`.
  - [ ] `PLE`.
  - [ ] `T20`.
  - [ ] `UP` and `I`. These are auto-fixable, but they touch many lines. Give them a dedicated commit, add it to `.git-blame-ignore-revs` like the Phase 1 reformat, and coordinate it with open branches the same way.
- [ ] **No blanket baseline file.** Fix each finding, or suppress it with `# noqa: CODE  <reason>`. `RUF100` flags stale suppressions.
- [ ] Make ruff blocking in `scripts/check`: change `report_only "ruff check"` to `run "ruff check"`.
- [ ] Later additions: `SIM`, `PTH` (new code only), and tuned `PL` rules.

### Phase 3: Type-checking infrastructure (≈ 3–5 days) — ☐ open

- [ ] Solve the blockers of §4 in this order: settings (4.1, needs decision §2.2.1), star imports (4.5), `ExecResult` (4.3, if not done in Phase 1), `AuthenticatedRequest` (4.2), checker API (4.4).
- [ ] Bring `mypy src` to **zero errors** with the committed config (`check_untyped_defs = true`). Fix errors where it is cheap; otherwise use `# type: ignore[code]  # reason`. Track the number of ignores.
- [ ] Optionally tighten `enable_error_code` with `redundant-expr`, `truthy-bool` and `possibly-undefined`.
- [ ] Make mypy blocking in `scripts/check`.

### Phase 4: Typing ratchet, from islands outward (continuous, 1–2 modules/week) — ☐ open

Mechanism:
- A strict mypy override (`strict = true`) in `pyproject.toml`. The list of modules only ever grows.
- A **diff annotation gate** in `scripts/check`: run ruff `ANN001,ANN201,ANN202,ANN204` on the changed files, keeping only findings on changed lines (parsed from `git diff -U0 $COMPARE_BRANCH`). Then every function an agent adds or modifies must be annotated, without forcing whole files.

| Wave | Modules                                                                                     | Why                                           | Done |
| ---- | ------------------------------------------------------------------------------------------- | --------------------------------------------- | ---- |
| 1    | `utilities/{nub,encoding,exceptionlogger,mimetypes,log_filter}.py`                          | Plain Python and tiny; proves the setup       | ☐    |
| 2    | `utilities/safeexec.py`, `utilities/file_operations.py`                                     | Security core: sandbox and zip extraction     | ☐    |
| 3    | `accounts/decorators.py`, `accounts/typing.py`, `utilities/views.py`, `context_processors/` | Permission checks and protected file serving  | ☐    |
| 4    | `checker/basemodels.py`, `checker/compiler/Builder.py`, `checker/checker/ScriptChecker.py`  | The plugin API and the supported checker      | ☐    |
| 5    | `solutions/`, `tasks/`, `configuration/` models and forms                                   | ORM-heavy; django-stubs does most of the work | ☐    |
| 6    | Views and admin (`attestation/views.py` last)                                               | Largest and least reused                      | ☐    |
| —    | The other checkers and compilers                                                            | Only when touched (D2)                        | —    |

### Phase 5: Tests and coverage ratchet (continuous) — 🟡 partly done

- [x] Coverage config with `fail_under` (57, measured as CI measures it; D3).
- [x] Diff coverage ≥ 80 % in `scripts/check --full`.
- [x] CI runs the tests once, under coverage, instead of twice.
- [ ] **Permission matrix:** one table-driven test requesting every URL in `urls.py` and `accounts/urls.py` as anonymous, `user`, `tutor` and `trainer`, asserting allowed vs. redirect/403. It encodes the answer to §2.2.3.
- [ ] **`safeexec`** tests (see Phase 1).
- [ ] **Upload handling:**
  - Zip traversal: `../`, absolute paths, and sibling-prefix dirs (the guard at `utilities/file_operations.py:91` is a bare prefix check).
  - Zip bombs, NUL bytes, and non-UTF-8 file names.
- [ ] **ScriptChecker unit tests** with a mocked `execute_arglist`: pass, warning (exit 121), fail, timeout, OOM.
- [ ] **Account flows:** registration/activation, CSV/XML user import, and LDAP/Shibboleth (with `ldap` and the request headers mocked).
- [ ] **Hygiene:**
  - Use `timezone.now()` instead of naive `datetime.now()` in fixtures.
  - Replace the `'test' in sys.argv` special case in `checker/basemodels.run_checks` with a setting.
- [ ] Raise `fail_under` step by step; the target is in §2.2.4.

### Phase 6: CI, hooks and agent integration (≈ 1 day) — 🟡 partly done

- [x] CI runs `scripts/check --full` on Python 3.10–3.14 with `PRAKTOMAT_REQUIRE_ALL_TOOLS=1`.
- [ ] A separate fast `static` job on one Python version (ruff, mypy, Django checks, pip-audit), once Phases 2 and 3 make them blocking.
- [ ] Diff coverage in CI: check out with `fetch-depth: 0` so that `origin/master` exists, and set `COMPARE_BRANCH` to the PR base.
- [ ] Make the CI jobs required status checks on `master` (GitHub settings).
- [ ] pre-commit: `ruff format`, `ruff check --fix`, trailing whitespace/EOF, `check-merge-conflict`.
- [ ] Claude Code: a committed `.claude/settings.json` with a `PostToolUse` hook running `ruff format` and `ruff check --fix` on edited `*.py` files, and a reminder or hook to run `./scripts/check` before finishing. `.claude/settings.local.json` stays personal.

---

## 6. Measurements

| Metric                                | 2026-09-28 (`7a657885`, analysis)          | 2026-10-13 (`b2ad432d` + Phase 0)                                      |
| ------------------------------------- | ------------------------------------------ | ---------------------------------------------------------------------- |
| Tests                                 | 104; 10 failed because tools were missing  | 113 (6 skipped locally: wsgi ×3, CUnit C ×2, memory limit), 0 failures |
| Branch coverage                       | 61 % (with the toolchain tests)            | 62 % locally with toolchains; **57.18 % in CI** (no toolchains)        |
| Annotated functions                   | 6 / 701                                    | new test helpers only                                                  |
| ruff (rule set in `pyproject.toml`)   | — (480 with ruff defaults)                 | 1005                                                                   |
| mypy (`pyproject.toml` config)        | 432 (`check_untyped_defs`, tests excluded) | 433 (tests included)                                                   |
| Django check / migrations / templates | clean                                      | clean                                                                  |
| pip-audit                             | —                                          | no known vulnerabilities                                               |

To reproduce: `pip install -r requirements.txt -r requirements-dev.txt`, then `./scripts/check --full`.
For the CI coverage figure, add `--exclude-tag optional_toolchain` to the test command, or run on a
machine without the toolchains.

---

## 7. Findings of the original analysis

The analysis that motivated this plan. Line numbers in §7.4 were re-verified against `b2ad432d`.

### 7.1 State before Phase 0 (2026-09-28, `master` @ `7a657885`)

The numbers below were measured on Python 3.12, in a scratch copy of the repo.

| Check                             | Status                                                                                                                                                                                                            |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit/integration tests            | **104 tests** in 14 modules, run by the Django test runner, about 50 s. Mostly Django test-client and end-to-end checker runs (real compilers); there are very few isolated unit tests. No pytest.                |
| CI (`.github/workflows/test.yml`) | Runs the tests on Python 3.10–3.14 (conda), then runs them a second time under coverage. **Tests are the only gate.**                                                                                             |
| Coverage                          | Measured in CI but **not enforced** (no `--fail-under`, no config file). Baseline 61 % branch coverage.                                                                                                           |
| Type checking                     | **None.** 6 of 701 functions have annotations; no module imports `typing`; no mypy/pyright config.                                                                                                                |
| Linting / formatting              | **None configured.** No ruff/flake8/pylint config and no pre-commit. `.vscode/settings.json` disables linting.                                                                                                    |
| Django `check`                    | Clean. `check --deploy` reports only production-settings warnings (expected for test settings).                                                                                                                   |
| Migration drift                   | Clean (`makemigrations --check`).                                                                                                                                                                                 |
| Template syntax                   | Clean (`validate_templates`).                                                                                                                                                                                     |
| Dependency hygiene                | `requirements.txt` is mostly unpinned (only Django `~=5.2` and Pygments, then held back at `~=2.7.0`; lifted to `~=2.19` upstream in `99c648fb`). No lock file, no dev-requirements file, no vulnerability audit. |

### 7.2 What the static tools reported (no config, `migrations/` excluded)

| Tool                             | Result                                                                                                                                                                                                                 |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ruff check` (default rules)     | 480 findings, mainly: 158 F405/F403 (star imports, mostly settings), 123 unused imports, 42 E402, 22 unused variables, 18 bare `except`, 25 F821 undefined names (mostly settings, but some are real bugs, see below). |
| `ruff format --check`            | 102 of 122 files would be reformatted (mixed tabs and spaces in places).                                                                                                                                               |
| `mypy` + django-stubs (lenient)  | 98 errors in 32 files.                                                                                                                                                                                                 |
| `mypy` with `check_untyped_defs` | 432 errors in 66 files. 138 are `'Settings' object has no attribute …`, caused by the dynamic settings.                                                                                                                |
| `pyright` basic                  | 270 errors, 161 of them attribute-access noise from the ORM (no Django plugin). **mypy + django-stubs is the better gate.**                                                                                            |

### 7.3 Weak spots

- **Coverage below 40 %:**
  - `utilities/safeexec.py` **28 %**, the sandbox, the most security-critical code.
  - `accounts/shib_views.py` 17 %, `accounts/ldap_auth.py` 21 %, `accounts/views.py` 31 %.
  - `attestation/models.py` 33 %, `attestation/views.py` 38 %, `utilities/views.py` 30 % (protected file serving).
  - The checkers DiffChecker, AutoAttestChecker, Haskell, Isabelle and JUnit are between 33 % and 46 %.
- **Untested:** all management commands under `utilities/management/`, most account flows, and password reset.
- **Broken tests:**
  - `accounts/tests.py:81` redefines `test_testgroup_set_group` (line 61), so the first version never runs.
  - `hbrs_tests/test_CUnitCppUnit_Checker.py:36` defines `teatDown`, a typo, so it never runs.
  - `checker/tests.py` `test_anonymity_checker` and `test_checkstyle_checker` have no assertions.
  - `sessionprofile/tests.py` is never executed.

### 7.4 Latent bugs (not yet fixed)

Each needs a regression test when fixed. The fixes are tracked in Phase 1, step 1b (§5).

- `utilities/safeexec.py:48` does `environment = os.environ; environment.update(...)`. This **mutates the server's process environment** on every call, so variables leak between checker runs.
- `utilities/safeexec.py:40` has mutable default arguments (`environment_variables={}`, `extradirs=[]`).
- `utilities/safeexec.py:246-252` reads `settings.DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_1..5`. These are defined at module level in `settings/defaults.py:455`, outside `load_defaults`, so they are never exported. The result is an `AttributeError` when "mount extra directories" is enabled and `local.py` does not set them.
- `checker/checker/RChecker.py:113`: `"...required ----\n" % exitcode` has no placeholder, so it raises `TypeError` whenever `require_plots` is set and no plot was produced.
- `checker/checker/ScriptChecker.py:162`: `clean_filename` uses the undefined name `shell_script`, which raises `NameError`.
- `solutions/models.py:272`: the undefined `index` in the JPlag export raises `NameError` when anonymous attestation is on.
- `attestation/views.py:250`: the undefined `published` raises `NameError` when anonymous attestation is on and the user is neither tutor nor trainer.
- `checker/compiler/Builder.py:39-40`: `main_check` uses the undefined names `_main_required` and `main_search`. It is currently dead code.
- `checker/compiler/Builder.py:87,354`: the class-level mutable `_env = {}` is shared across instances.
- `utilities/management/commands/install_demo_db.py` and `update_model_graph.py` use `handle_noargs`, which was removed in Django 1.10, so both commands are dead.
- `accounts/ldap_auth.py:10`: `from settings import LDAP_GROUP_ADAPTERS` imports from the settings *package*, so it always hits the bare `except`.
- `checker/checker/IsabelleChecker.py:41`: `setting.ISABELLE_BINARY` is a typo for `settings`, so it raises `NameError`.
- `utilities/encoding.py:26`: `UnicodeDecodeError("…")` is constructed with 1 argument instead of 5, so it raises `TypeError` instead.
- `utilities/safeexec.py:142`: strict `output.decode('utf-8')` crashes on non-UTF-8 program output. The returned `error` is `bytes | None`, while `output` is `str`.
- `utilities/file_operations.py:91`: the zip path guard is a bare `startswith(to_path)` with no trailing separator. `zipfile.extract` sanitizes `..` itself, so this is weak defence in depth rather than an exploitable hole.
- `taskstatistics/views.py:192,210` have no auth decorator; they are public by design (anonymous users are handled). Confirm that this is intended.
- `re.match(...).group()` is used without a `None` check in `solutions/models.py:191` and `checker/compiler/CLinker.py:55`.
