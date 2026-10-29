# Python Typing Plan

## Goal

Make Praktomat's Python codebase progressively type-safe and provide a runnable,
strict Pyright check, preferably configured in `pyproject.toml`. Preserve the
project's supported Python range, currently Python 3.10 and newer. Use
`django-stubs` if it materially improves Django typing under Pyright.

## Approach

Treat strict typing as a project-wide target, not just a configuration change.
Establish the current state first, then resolve errors in manageable groups
without hiding them behind broad ignores or weakening strict checking. The
baseline measures the work; it does not set a permanent reduced scope.

The end goal is strict checking of all maintained first-party Praktomat Python
code. Include application code, tests, and migrations unless a specific,
documented technical reason justifies an exclusion. Do not leave difficult paths
permanently excluded merely to obtain a passing check.

## Remaining-work dependency bundles

Planning baseline: **1,364 errors, 0 warnings**, 225 files, Pyright 1.1.414,
django-stubs 6.0.9, Python 3.10 static target, Django 5.2 runtime.
This covers all remaining work, not just the 56 remaining diagnostics introduced
by the stub upgrade.

### Implementation progress

**Current status: B1 through B12 complete.** The full configured strict check now
passes with **zero errors and zero warnings across 227 files**, with no reduced
scope or weakened rules. An independent GitHub Actions job enforces the same
command on pushes and pull requests. Runtime validation retains the known
missing-`fakechroot` failures described below.

B1's exit criteria are verified: the custom-user
manager, inherited fields, primary-key reset/write contracts, domain reverse
relations and relation element types are explicit without changing runtime model
registration or the database schema. B2's checked authentication boundary is
propagated to HTTP consumers, with anonymous and role-based access verified.
B3 now defines isolated settings defaults and typed process results/options,
with execution/backend/resource-lifetime regressions verified.
B4 now checks required stored-file names and archive paths, types archive inputs,
and preserves Django 5.2 signed-mail serialization with regression coverage.
B5 now contains typed LDAP, statistics, highlighting and template-chunk boundaries,
with integration/output regressions verified.
B6 now defines checked generic checker results, compatible compiler/linker
contracts and tested execution/failure/resource-lifetime behavior.
B7 now defines form-instance, cleaned-data and field-choice boundaries, with
admin validation and generated upload/attestation formsets regression-tested.
B8 now defines concrete checker-inline models, compatible admin form/fieldset
factories and supported display/action metadata, with admin regressions verified.
B9 now defines HTTP/template data contracts, typed SSO and upload boundaries,
and compatible response/routing contracts, with HTTP regressions verified.
B10 now types historical migration metadata without changing serialized operations
or graph metadata, with fresh migration and rollback validation.
B11 now types the remaining test consumers and fixtures without weakening their
assertions; a previously shadowed group-import test is restored.
B12 resolves the model residuals and adds strict-check CI enforcement, with
final runtime, startup and migration replay validation.
The entries below record the successive bundle slices and their validation.

**B1, first foundation slice: 1,364 -> 1,291 errors, 0 warnings.**
All 225 files remain included, with the same pinned checker and dependencies.
The diagnostic multiset comparison removes 77 diagnostics and surfaces four
downstream diagnostics, for a net reduction of 73.

- Removed the old plain-string redeclarations of inherited user name fields;
  django-stubs now describes their actual descriptors and instance values.
- Specialized the existing manager constructor as `UserManager["User"]()`.
  Unlike an explicit mutable `ClassVar` override, this resolves manager result
  types without conflicting with the inherited declaration. Runtime checks and
  regression tests confirm the manager model and migration deconstruction are
  unchanged.
- Declared verified generated parent links, primary keys and reverse relation
  descriptors under `TYPE_CHECKING`. These cover tutorial users/tutors,
  attestation files/rating results, solution-file annotations and checker
  artefacts. They do not add database fields or runtime descriptors.
- Corrected the tutorial many-to-many through-model type: Django generates a
  join model, not another `User`.
- Gave the nested user `Meta` its inherited typing base only under
  `TYPE_CHECKING`, retaining its existing runtime options instead of inheriting
  additional migration metadata.
- Made the validator conform to Django's `None`-returning validator contract.
  Its only callers are Django field validation and historical migration
  references; acceptance/rejection behavior remains unchanged.
- Expressed activation as a normal staticmethod declaration and read the
  inherited `date_joined` directly. Tests verify the parent/child date agrees.
- Typed the base-user creation signal's `instance` and `created` arguments.
  `vars()` accesses the same mutable instance dictionaries for the existing
  parent/child copying operation.
- Added six regression tests for manager results/deconstruction, automatic
  parent/child user creation, reverse tutorial relations, inherited field
  identity and matriculation-number validation.

Verification: all 44 accounts/attestation/solutions/tasks tests pass.
The separate model-contract/checker run executes 29 tests, with 28 passing and
one skipped. Django startup/system checks pass; changed-file whitespace checks
pass. `makemigrations --check --dry-run` reports the same pre-existing changes
to DejaGnu `test_defs` and `test_case` as before this slice, and no additional
changes; no migration was written.

The four newly surfaced diagnostics are one partially unknown tutorial ID in
an attestation view (the unresolved request-user boundary), and three artefact
archive diagnostics caused by nullable stored-file names. Keep these visible
for B2/B4 rather than weakening the relation declarations.

B1 is not declared complete: serialization/import model narrowing and remaining
shared contracts still need work. The core manager/generated-relation work now
provides a verified foundation for the B2 request-user boundary.

**B1, import-contract slice: 1,291 -> 1,259 errors, 0 warnings.**
The pinned full-scope check removes 32 diagnostics and introduces none, comparing
diagnostic multisets by file, rule and message. B1's cumulative reduction is now
105 errors from the 1,364-error planning baseline.

- Typed user XML inputs, imported identity maps and the returned custom-user
  queryset. Narrowed deserialized parent/child user models explicitly and passed
  the validated upload from the import form.
- Fixed a reproduced user-import bug: unrelated serialized models were treated
  as base users and saved. They now raise `ValidationError`, with the transaction
  rolling back earlier imported records.
- Typed task archive inputs, identity/scale maps and imported solution lists.
  Narrowed supported task archive models before accessing model-specific fields;
  unrelated models now raise `ValidationError` rather than an accidental
  `AttributeError`. Preserved checker subclasses and legacy HTML-injector records.
- Declared the generated task foreign-key IDs on media files, HTML injectors and
  checkers. Allowed the existing `date.max` template value in the publication
  field's write contract while retaining `datetime` as its database read type.
- Typed queued attestation deserialization records using Django's
  `DeserializedObject` contract.
- Added four user-import regression tests and three task-import tests, covering
  multipart uploads, parent-ID remapping, duplicate users, unsupported-model
  rollback, rating-scale/item reuse and template publication/reset behavior.

Verification: all 51 accounts/attestation/tasks/solutions tests pass, including
the existing real task ZIP upload/export tests. Changed-file whitespace checks
pass. Python 3.10, Django 5.2, dependencies and the 225-file strict scope remain
unchanged. Signature checking still exposes the existing generic
`request.user` argument at the task-import view; this is a B2 dependency, not
evidence that the authenticated runtime user is incorrectly imported.

B1 is still in progress; task export/file handling and other shared contracts
remain visible rather than being suppressed.

**B1, task-export and display-metadata slices: 1,259 -> 1,245 errors,
0 warnings.** The pinned full-scope check removes 14 diagnostics and introduces
none. The cumulative reduction from the planning baseline is now 119 errors.

- Replaced list-summing with typed comprehensions for checker discovery in
  task export and execution ordering. Preserved concrete checker subclasses,
  task filtering, export traversal order and execution-order sorting.
- Typed the exported file collection as Django `FieldFile` instances, including
  fields discovered from concrete checker model metadata.
- Used the ZIP context manager to finalize exported archives while retaining
  the rewound, open temporary-file return contract.
- Replaced four direct function-metadata assignments on user/tutorial models
  with Django's `display` decorator, preserving boolean indicators and the
  translated tutor-column label without dynamic-attribute typing errors.
- Added archive-content tests for empty exports, XML model identity/order,
  exact media/checker/solution file bytes and the returned stream position.
  Added checker subclass/filter/order and admin display-metadata tests.

Verification: 78 accounts/attestation/tasks/solutions/checker tests run;
77 pass and one is skipped. Changed-file whitespace checks pass. The static
Python target, runtime Django version, dependencies and 225-file scope are
unchanged. Remaining optional filename and checker-result contracts are still
visible for their corresponding foundation/file bundles.

**B1 closure: 1,245 -> 1,242 errors, 0 warnings.** The pinned full-scope
check removes three diagnostics and introduces none. B1's total net reduction
is **122 errors** from the 1,364-error planning baseline.

- Replaced plain manager annotations on Task, Solution and RatingScale reverse
  relations with verified `ReverseManyToOneDescriptor` declarations. Added the
  remaining shared user/solution, task/media/deadline and rating reverse
  relations used by domain consumers.
- Declared generated primary keys with `AutoField` write/read contracts,
  including Solution's clone/reset path, rather than inferring a permanently
  nullable ID from its in-method reset annotation. Added generated foreign-key
  IDs for attestation/rating records, task helpers and checker-result records.
- Corrected the nullable `Attestation.final_grade` and `RatingResult.mark`
  declarations to match their actual `null=True` fields and `SET_NULL` behavior.
- Typed the shared critical-result prefix accumulator.
- Added three regression tests for solution cloning with copied file/result
  identities, critical-result truncation, and nullable rating/attestation
  grades with reverse queries and deletion behavior.

Verification: the affected 81-test suite has 80 passes and one skip.
The full 134-test application suite has 131 passes, one skip and the same two
known CUnit upload failures: both rendered checker logs explicitly report
`fakechroot: command not found`. No new runtime test failures were found.
`makemigrations --check --dry-run` still proposes only the pre-existing DejaGnu
`test_defs`/`test_case` alterations; no migration was written. Changed-file
whitespace checks pass. All 225 Python files remain in the strict check.

Completing B1 does not mean that every diagnostic in a model file belongs to
B1 or has been resolved. The remaining boundaries retain their original owners:

| Remaining boundary | Owning bundle |
| --- | --- |
| Generic/anonymous HTTP users and decorators | B2 |
| JPlag/process settings and execution options | B3 |
| Optional stored filenames, archive paths, uploads and mail compatibility | B4 |
| Rendering/diff/statistics consumers | B5 |
| Generic checker targets, result ordering and checker execution | B6 |
| Residual unused imports/locals and final diagnostic cleanup | B12 |

`accounts.models` now has no strict diagnostics. The shared ORM contracts above
are available to subsequent bundles; no rule suppression, dependency change or
runtime-version change was used to close B1.

**B2, authentication/decorator foundation: 1,242 -> 1,197 errors,
0 warnings.** The pinned diagnostic multiset comparison removes 45 diagnostics
and introduces none. The new shared authentication helper is included, bringing
the full source scope to 226 files rather than excluding any existing files.

- Replaced request-class mutation and its broad exception fallback with a
  per-request `SimpleLazyObject`, preserving lazy custom-user resolution and
  repeated-access caching. Aliased Django's authentication middleware base,
  retained its session validation, and wired its async user accessor through
  the same custom-user resolver.
- Resolve actual base Django users to their multi-table Praktomat child.
  Anonymous/custom users remain distinct. Only a missing child is an expected
  fallback to the base account; unexpected lookup errors propagate.
- Added `require_user(request)` as a checked application-user boundary.
  It returns a verified custom User or raises `PermissionDenied`; it does not
  globally narrow `HttpRequest.user`. Account editing now uses this boundary.
- Kept inactive-user logout and disclaimer redirects/exempt paths. Required
  disclaimer enforcement rejects authenticated base-only accounts explicitly
  rather than assuming they have custom fields or bypassing the requirement.
- Typed decorators with parameter-preserving callable contracts and added
  `wraps` to the Shibboleth feature decorator. Fixed the reproduced anonymous
  local/Shibboleth predicate crash by checking the actual custom-user type.
- Added 16 regression tests covering normal and Shibboleth login, lazy lookup,
  request-class isolation, session requirements, async accessor integration,
  base-only accounts, unexpected lookup errors, inactive logout, disclaimer
  handling and local/LDAP/Shibboleth/anonymous access distinctions.

The lazy proxy requires one localized `cast` at the middleware assignment:
Django's runtime proxy delegates to the resolver's user type but is not a
static subclass of it. This is not a custom-user assertion; the declared union
still permits base/anonymous users, and consumers must use the checked helper.

Verification: the broader affected suite ran 96 tests with 95 passes and one
skip. After the final base-only disclaimer guard/test, all 33 accounts tests
pass. The three authentication/middleware/decorator modules have no strict
diagnostics, and changed-file whitespace checks pass. Python 3.10, Django 5.2,
dependencies and strict rules are unchanged. At this stage B2 was not complete:
remaining HTTP consumers still need to adopt the checked boundary where they
require custom-user operations; generic authentication alone is not sufficient.

**B2 closure: 1,197 -> 824 errors, 0 warnings.** Comparing diagnostic
multisets removes 375 messages and surfaces two downstream context diagnostics,
for a net reduction of 373. B2's total net reduction is **418 errors** from its
1,242-error starting point. The pinned check still covers all 226 source files.

- Wired `require_user()` into task, solution, attestation and protected-file
  views, plus the task admin action and authenticated statistics branch that
  consume custom-user operations. Each affected scope assigns only the
  runtime-verified result to `request.user`, which Pyright narrows locally.
  This needs neither a narrower mutable HttpRequest subclass nor new casts,
  global user narrowing, signature changes or altered login/staff decorators.
- Applied the same checked boundary to disclaimer writes. Anonymous GET still
  displays the disclaimer, but a valid anonymous POST is now explicitly denied
  instead of attempting to save an AnonymousUser.
- Replaced the task-list tutorial access's broad exception fallback with an
  explicit nullable relation check. A missing tutorial still has no tutors;
  unexpected database failures are no longer swallowed.
- Checked the optional `tutored_users()` result before testing membership:
  tutors without solution-edit permission are denied rather than raising
  `TypeError`. Existing role checks and login redirects are otherwise retained.
- Cached the async resolver's custom-user result in Django's existing
  `_acached_user` slot; a real session-backed async test verifies repeated
  access returns the same resolved account.
- Added seven closure tests covering HTTP login redirects, authenticated
  base-only rejection, student/tutor/trainer status matrices, disclaimer
  persistence, protected solution-file access, denied tutor uploads and the
  async cache. All 23 authentication-boundary tests pass.

Verification: the full application suite runs **157 tests: 154 pass, one is
skipped and two fail for the same known missing `fakechroot` executable**.
Both failure logs contain `fakechroot: command not found`; there are no new
runtime failures. Signature analysis confirms all 35 `require_user` call sites
are compatible. Changed-file whitespace checks pass. No dependencies, schema,
static Python minimum or runtime Django version changed.

No remaining diagnostic references a generic `_User`/`AnonymousUser` misuse.
The two newly surfaced attestation context diagnostics come from propagation
of the already-reported undefined `published` variable in `show_author`;
the original undefined-variable diagnostic remains visible as well. That
view/rendering logic stays in B9 rather than guessing a new visibility policy
or concealing unknown values to make B2 appear cleaner.

**B3 complete: 824 -> 749 errors, 0 warnings.**
The pinned Pyright 1.1.414 check covers 227 files, including the new utilities
tests. Comparing diagnostic multisets by file, rule and message removes 75
diagnostics and introduces none. No diagnostics remain in settings modules,
`utilities.safeexec`, or the new utilities tests.

- Made defaults invocation-local instead of injecting caller values and defaults
  into module globals. Repeated loads now populate their own mapping and derive
  paths, managers, login URLs and authentication backends from that invocation's
  overrides. Required inputs remain required; invalid dependent-setting types
  raise explicit errors. Secret-key creation/reuse retains private permissions
  and closes its output stream. Extra Docker mount defaults are now actually
  installed in the caller's settings.
- Expressed intentional deployment overrides as single uppercase assignments,
  using a lowercase intermediate for the assembled site title. Removed obsolete
  assignments immediately overwritten by the active JAR paths. Tests preserve
  all eight course variants, mirror behavior, timeout/memory/parallelism choices,
  and mail backend selection.
- Added the immutable, five-element `ExecutionResult` named tuple:
  `(output: str, error: bytes | None, exitcode: int, timed_out: bool, oom_ed: bool)`.
  This intentionally replaces the heterogeneous list; existing positional
  unpacking/indexing remains valid, and named access is available. Typed JPlag's
  environment and consumed its output without unused status bindings.
- Copied the parent environment instead of mutating it. Replaced mutable option
  defaults, defined optional file-size limits explicitly, and tracked the actual
  selected backend. Tester precedence and unsafe bypass remain intact, including
  when both backend flags are enabled.
- Removed unreachable process-debug scaffolding and replaced the Python-3.11-only
  template identifier API with Python-3.10-compatible pattern inspection.
  Preserved missing/empty task-ID mount skipping and literal/escaped paths.
- Ensured Docker helper/volume cleanup runs after launch or communication errors.
  Partial mount setup rolls back allocated resources. Setup/copyback/removal
  subprocess failures now raise with visible stderr instead of silently
  continuing; resource removals are still attempted after copyback failures.

Verification: all **26 new utilities tests pass**, with timeout, backend,
container setup and cleanup activity mocked; no live Docker validation was run.
The full application suite runs **183 tests: 180 pass, one is skipped and two
fail with the known `fakechroot: command not found` environment limitation**.
The full command explicitly sets `LANGUAGE=en_US:en`: the locale test previously
passed only after checker execution leaked that value into the host environment.
Without that prerequisite it correctly reports an undefined host `LANGUAGE`;
subprocess environment isolation is not weakened to hide the dependency.
The README includes both the full command and the isolated no-database utilities
command.

Python 3.10 remains the static compatibility target; runtime Django, dependencies,
database schema and strict-checking scope are unchanged. Checker-specific
consumer issues remain assigned to B6; no broad suppressions were added.

**B4 complete: 749 -> 689 errors, 0 warnings.**
The pinned full-scope check still covers 227 files. Comparing diagnostic
multisets by file, rule and message removes 60 diagnostics and introduces none.
The shared file utilities, deletion-field implementation and new B4 test code
are strictly typed without adding suppressions or changing dependencies.

- Added `require_file_name` for operations that require a nonempty stored-file
  name. Solution saves, display/path parsing, media basenames and archive
  consumers now have explicit missing-name errors instead of nullable path
  operations. Solution paths validate their archive structure and accept spaces
  in usernames; malformed solution/user paths raise descriptive `ValueError`.
  File cleanup signals explicitly handle records with no stored file.
- Replaced archive collections mixing `FieldFile` and dummy path-only objects
  with typed `(archive name, source path)` pairs. Downloads retain solution-file
  priority, generated Eclipse metadata and stored/generated checker files.
  Corrected duplicated checker subdirectories and the reproduced undefined
  anonymous-project index; anonymous projects now use `User1`, `User2`, etc.
- Managed output ZIPs, imported ZIPs, extracted uploads and intermediate streams
  with context managers. Successful exports remain open and rewound for their
  caller; failure closes the output stream, and checker-extraction directories
  are removed on success or failure. Creating a sandbox temporary directory no
  longer changes the process-wide `tempfile.tempdir`.
- Made ZIP extraction validate a real destination boundary rather than a string
  prefix, including relative destinations and sibling-prefix traversal.
  Preserved overwrite/file callbacks and verified extracted binary contents.
- Checked uploaded-file/solution inputs at validation boundaries, preserved
  existing NUL/tar/size/ZIP-member rejection, and rewound ZIP uploads even after
  validation fails. Replaced the broad ZIP exception fallback with explicit
  supported format/decryption errors; unexpected failures propagate.
- Kept Django 5.2 authoritative for signed mail. The runtime's `message(self)`
  API is still called without Django 6 keywords. A standard-message-compatible
  adapter supports serialization policies and Django's `linesep` backend call,
  exposes the signed MIME structure and keeps the existing S/MIME header/body
  transformation. The lazy-string alias is imported only under `TYPE_CHECKING`,
  so development stubs are not a runtime dependency. Translation promises remain
  lazy; the mail connection has the concrete backend interface.

Verification: **24 new regression tests** cover these contracts, including exact
stored/generated archive entries, malformed/missing files, cleanup on failure,
upload rejection and stream position, task/media exports and anonymous naming.
Signed-mail tests compare exact legacy Django 5.2 wire bytes with LF/CRLF and
long Unicode subjects, exercise SMTP policies/Unix envelopes and send through
the actual SMTP backend using a mocked connection (no network access).
The final focused utilities/solutions/tasks run passes all **79 tests**;
the full run includes all **207 tests:
204 pass, one is skipped and two fail with the same missing `fakechroot`
executable**. The final six-test mail run also passes after preserving the
underlying MIME serialization policy explicitly.

`makemigrations --check --dry-run` still proposes only the two pre-existing
DejaGnu `test_defs`/`test_case` changes; no migrations were written. Python 3.10,
Django 5.2 and strict project scope remain unchanged. The three pre-existing
checker-order/unused-query diagnostics in solution models remain B6 work;
formset aggregation and legacy test diagnostics remain assigned to B7/B11.

**B5 complete: 689 -> 542 errors, 0 warnings.**

The pinned full-project check removes **147 diagnostics and introduces none**
(multiset comparison by file, rule and message, ignoring line shifts).
All 227 Python files remain checked. LDAP authentication, template chunks,
statistics views, highlighting and the Isar lexer have no remaining diagnostics;
the added tests introduce no diagnostics. Existing test/view/form/checker errors
remain assigned to later bundles.

- LDAP search entries and normalized users now have separate typed contracts.
  Raw byte attributes are not mutated; referrals/missing/ambiguous results return
  no user. Attribute selection still uses the shortest nonempty raw value before
  UTF-8 decoding. Filters escape supplied usernames, and connections unbind even
  on search/decode/bind failure. Only invalid credentials become authentication
  failure; directory operational failures remain visible.
- Authentication retains local-password precedence, the `LDAP_AUTH` marker,
  disabled-creation behavior, existing-account privileges and the default `User`
  group. Admin imports retain all-or-nothing handling of unknown UIDs.
  Configured group adapters now load from Django's `LDAP_GROUP_ADAPTERS` setting,
  instead of an import from the empty settings package that normally disabled
  them. Missing modules/noncallable adapters fail explicitly at startup.
- Python-ldap 3.4.8 has no installed/published typing package found in this
  investigation. Narrow local `typings/ldap` declarations describe only the
  exercised synchronous search/bind/unbind/filter API, including referral tuples;
  signatures and result structure were checked against the installed runtime.
  LDAP tests mock the connection: no live directory was contacted.
- Development-only `types-Pygments==2.21.0.20260819` supports Python 3.10.
  Formatters/results and diff accumulators use its existing types. Narrow casts
  cover missing registry declarations and incompletely typed keyword/callback
  APIs, without replacing the library's stubs. The unstubbed Isabelle lexer uses
  its verified `RegexLexer` base for static analysis: the runtime subclass only
  adds token rules and no methods. Runtime inheritance and token decoding are
  unchanged; escaping, fallback and character/diff alignment are tested.
- Statistics now pass ordered, validated query rows directly to rendering and
  standard-library CSV, rather than converting through pandas DataFrames and
  untyped named tuples. This avoids a new pandas-stubs/numpy dependency constraint;
  no runtime packages were changed or removed. Field order, SQL NULL-to-zero
  conversion, mixed-number CSV column formatting, quoting/Unicode and selected
  user/category positions have regression coverage.
  Matplotlib's object-oriented Figure/Agg path produces real PNGs without global
  pyplot figure managers. Narrow verified protocol boundaries cover incompletely
  annotated axes/rendering methods; unexpected data/plot errors propagate.
- Chunk tags parse invalid cache timeouts as template syntax errors and reject
  invalid cache objects explicitly. Missing chunks still render empty text;
  database failures do not disappear behind missing-content handling.

Added **24 regressions**. The final focused run passes **157 tests**.
The final full run executes **231 tests: 228 pass, one skipped, two fail with the same missing
`fakechroot` executable**. Python 3.10 grammar parsing and B5-only whitespace
checks pass. Runtime verification used Python 3.12 and Django 5.2; no Python 3.10
runtime run or live LDAP service test was performed. No database models or migrations
changed. Strict rules, Python minimum and runtime dependency requirements remain
unchanged.

**B6 complete: 542 -> 406 errors, 0 warnings.**

The pinned full-project diagnostic multiset removes **136 diagnostics and
introduces none**, ignoring line shifts. All 227 Python files remain included;
strict rules, dependencies, Python 3.10 minimum and Django 5.2 runtime are unchanged.
The checker base/environment/results, concrete checker/compiler modules,
management command and documented checker example have no strict diagnostics.
Existing checker admin, historical migration and legacy test diagnostics remain
assigned to B8/B10/B11; the new tests introduce none.

- The runtime generic relation and its cascade semantics remain intact, while
  static analysis knows its result element type. `CheckerResult.require_checker()`
  checks the generic target before accessing checker-specific attributes and
  raises explicitly for absent/wrong targets. Result titles/public/required/
  critical handling and solution result ordering reuse that boundary.
  The public-result path now uses its already-prefetched queryset.
- The environment explicitly records optional executable state and typed
  text/binary/generated sources. Temporary-directory allocation follows source
  loading, avoiding a leaked directory when an upload cannot be read.
  Checker/source-copy failures clean up the sandbox in `finally`, while the
  existing debug-retention flag remains effective. Cleanup errors are no longer
  silently swallowed. Worker connections close on failure as well as success;
  parallel pools have deterministic context-managed teardown.
- Compiler and linker `Meta` declarations inherit compatible abstract metadata;
  no database schema changes result. Output flag fields are explicitly typed.
  Base/C/C++/linker `post_run()` implementations agree on `tuple[bool, str]`.
  The formerly unbound main-required helper now calls its instance state/method.
- Both compiler families now consume B3's execution result rather than treating
  "no warning text" as proof of success: nonzero exits, timeouts and OOM fail the
  checker, with timeout/memory details in its log. Existing warning rejection and
  postprocessing behavior remain tested. Environment dictionaries are copied
  before per-run locale/task updates, preventing shared class-state contamination.
- Shared output-flag parsing tokenizes configured quoting before substituting
  program placeholders, preserving filenames containing spaces/quotes as single
  arguments. Constant flags and literal percent signs work; malformed shell
  quoting raises rather than taking a broad exception fallback. With no known
  executable, placeholders remain literal as before.
- C-linker generated object sources are added once, without mutating the source
  list while iterating it. Main-object discovery no longer carries a stale
  instance cache into later environments, and it uses the already-checked regex
  match. Java main-class parsing no longer passes `re.MULTILINE` as a search
  offset and checks absent declaration matches explicitly; standard and varargs
  entry points are covered.
- Concrete checker execution dictionaries and file collections are typed;
  DiffChecker reuses B4's required-filename check. Script filename inference
  uses the actual uploaded file rather than an undefined variable and rejects
  invalid cleaned-data values. The dynamically generated script inline formset
  has one localized typed factory boundary and a runtime test proving model and
  request injection are preserved. C-unit filename warnings use supported,
  escaping `format_html` arguments rather than deprecated preformatted HTML.
- Production checker exceptions still generate a failed result and admin mail;
  exception types/messages come from the caught exception directly.
  Process-control exceptions are no longer swallowed as ordinary checker errors.
  The example imports the current base API, uses the static description contract,
  quotes runtime-unsupported generic field annotations, and creates a result
  attached to its solution through `self.create_result(env)`.

Added **26 regressions** for the above contracts, dependency success/failure,
secondary-run skipping, persisted warnings/log normalization, script warning exit
codes, relation cascades and resource failure paths. The final focused
checker/solutions/utilities/tasks run executes **131 tests: 130 pass, one skipped**.
The full run executes **257 tests: 254 pass, one skipped, two fail with the same
missing `fakechroot` executable**. The documented example also imports and runs
against the current API with its result creation mocked.

Python 3.10 grammar parsing passes for all 14 B6-touched Python files; runtime
tests use Python 3.12/Django 5.2, not a Python 3.10 interpreter. New execution,
connection and pool regressions mock external operations; no live Docker or
multiprocessing pool was started by them. The migration dry-run still proposes
only the two pre-existing DejaGnu `test_defs`/`test_case` changes; no migration was
written. B6-touched source whitespace checks pass.

**B7 complete: 406 -> 378 errors, 0 warnings.**

The pinned full-project diagnostic multiset removes **28 diagnostics and
introduces none**, ignoring line shifts. All 227 Python files remain included.
The accounts, attestation and solutions form modules have no strict diagnostics;
the 18 new regression tests introduce none. Strict rules, dependencies, runtime
Django and the Python minimum are unchanged.

- Registration and admin-change `Meta` types inherit their corresponding
  Django auth form metadata only during analysis, preserving the original
  runtime options (including widgets/field classes). Admin creation retains
  runtime `fields = "__all__"`: Django supports this, but the installed
  creation-form stub restricts the inherited attribute to a tuple. Its static
  `Meta` therefore inherits the upstream declaration and specializes only the
  model; the runtime declaration remains unchanged. Regression tests verify the
  actual registration field order, admin creation fields and user-text widget.
- Duplicate matriculation-number registration messages query the typed custom
  user manager through the Trainer group instead of relying on an unrepresented
  dynamically generated `Group.user_set`. Trainer addresses/names and the
  duplicate-registration validation message remain available.
- Admin account cleaning explicitly handles the parent's optional clean return
  and validates selected groups as a Group queryset at the cleaned-data boundary.
  It uses Django's `add_error()` instead of mutating private `_errors`; invalid
  values are removed from cleaned data using Django's normal mechanism.
  Existing group field errors are preserved rather than overwritten or duplicated.
  Users still require matriculation numbers unless dummy numbers are enabled;
  non-User groups retain optional numbers. Unexpected group values raise a
  visible validation error.
- Attestation and rating-result forms read the typed `self.instance` initialized
  by ModelForm instead of assuming an `instance` keyword was supplied. Positional
  instances work too. Model-choice fields are checked before setting choices,
  which come from typed rating-scale items rather than arbitrary row dictionaries.
  Existing grade omission, option labels, aspect help text and model-valued save
  behavior remain covered. Annotation hidden IDs still resolve to SolutionFile
  instances and reject missing IDs.
- Upload formset cleaning uses `any(form.changed_data ...)`, preserving the
  existing "at least one changed file" rule without an untyped list-reduction
  accumulator. Both standard/model-solution factories retain their behavior:
  empty forms fail, valid uploads bind to the solution, and invalid changed
  uploads keep their field error without an extra missing-file error.

Added **18 regressions**. The focused accounts/attestation/solutions/tasks run
passes all **133 tests**. The full run executes **275 tests: 272 pass, one skipped,
two fail with the same missing `fakechroot` executable**. Python 3.10 grammar
parsing passes for all six B7-touched Python files; runtime verification used
Python 3.12/Django 5.2. B7-touched whitespace checks pass. No model fields,
database schema or migrations changed. Admin/view/legacy-test work outside
these form boundaries remains assigned to B8/B9/B11.

**B8 complete: 378 -> 309 errors, 0 warnings.**

The pinned full-project diagnostic multiset removes **69 diagnostics and
introduces none**, ignoring line shifts. All 227 Python files remain included.
All admin modules, concrete checker inlines and the checker example have no
strict diagnostics; the 12 new regression tests introduce none. Strict rules,
dependencies, runtime Django and the Python minimum are unchanged.

- `CheckerInline` is generic over its concrete Checker subclass, with Task as
  the parent model. Every concrete inline and the documented example specialize
  this shared producer rather than overriding an invariant `Checker` model.
  TaskAdmin retains its heterogeneous subclass-discovered inline registry; one
  localized cast describes the framework's mixed-model registry. Runtime
  discovery and generated concrete forms remain covered.
- Checker fieldsets use the public `django_stubs_ext.FieldsetSpec` alias only
  during analysis, rather than importing private Django stub types or duplicating
  them locally. Their four control fields remain grouped exactly once. A narrow
  class-attribute cast handles the generated formset's `form` attribute, which
  upstream describes as a generic instance attribute. ScriptChecker now calls
  the typed superclass factory directly, removing its earlier factory cast;
  request injection and the always-changed inline forms are preserved.
- Existing display/action function-attribute assignments use Django's supported
  `@admin.display` and `@admin.action` decorators, preserving descriptions,
  boolean flags and ordering fields. Account role columns, solution checker and
  plagiarism actions, task actions, and existing admin URLs retain their behavior.
- AttestationAdmin's form factory accepts Django's `change` argument and narrows
  each generated grade field to the attestation task's rating scale. It no longer
  writes an undeclared `request.obj` attribute. Missing objects/scales produce no
  grade choices instead of dereferencing a missing scale; omitted grade fields
  are supported, and unexpected field types raise explicitly. Interleaved form
  factories retain independent choices, and an actual no-scale change page renders.
- Solution admin columns validate database annotations at the boundary, accepting
  booleans and integer zero/one rather than pretending they are declared model
  fields. Missing/invalid annotations raise explicitly. Existing SQL, filtering,
  ordering and execution modes remain unchanged.

Added **12 regressions**; the final combined admin-page/checker-contract run
passes all **49 tests**. The full run executes **287 tests: 284 pass, one skipped,
two fail with the same missing `fakechroot` executable**. Python 3.10 grammar
parsing passes for all 227 included Python files; runtime verification used
Python 3.12/Django 5.2, not an actual Python 3.10 interpreter. B8-touched whitespace
checks pass. No database fields, schema or migrations changed. Remaining
HTTP/migration/legacy-test work stays assigned to B9-B12.

**B9 complete: 309 -> 148 errors, 0 warnings.**

The pinned full-project diagnostic multiset removes **161 diagnostics and
introduces none**, ignoring line shifts. All 227 Python files remain included.
All view and URL modules now have no strict diagnostics. Strict rules,
dependencies, runtime Django and the Python minimum are unchanged.

- Accounts and SSO query trainers through the custom User manager instead of
  an unrepresented `Group.user_set`. The account CSV consumers read validated
  uploaded files through a checked byte-upload boundary, retain their delimiter,
  quoting, identifier modes and import counts, and create numeric stub usernames
  as strings. Tutorial assignment no longer risks an uninitialized queryset.
  The raw reactivation-mail Template receives a Django Context; backend-loaded
  templates retain dictionary contexts.
- Shibboleth header parsing describes optional normalized attributes and checks
  non-string header values. It retains first-value selection and WSGI
  Latin-1/UTF-8 decoding. The selected username is narrowed before lookup or
  creation; optional matriculation numbers are converted to integers. Invalid
  numbers return the existing forbidden/error page. Only a missing account
  triggers account creation: operational database failures no longer enter the
  missing-user fallback. Existing new-user/manual-validation/deadline/group and
  local-redirect policies are regression-tested.
- Attestation statistics use typed rating sources, runtime points/series, median
  buckets and tutor counters. Date values come from typed queryset projections.
  Missing grade scales yield empty categories, and no-student cumulative data
  remains a chart array instead of becoming a scalar. Runtime series retain the
  actual checker index rather than the reused bucket-loop index.
- Attestation row/cell contracts preserve nullable solutions/grades and Decimal
  warning thresholds. The task iterable is materialized once so every user gets
  the same task columns, including for generator callers. Only numeric labels
  contribute to grade arithmetic; plagiarism options, SUM/AVG behavior and
  nullable tutorial averages remain intact.
- Invalid attestation-preview POSTs now render the bound form rather than
  returning None. Trainer-only list/publish collections stay typed without
  widening the underlying queryset to None; their template visibility and
  permission gates are preserved. The author flag no longer references an
  undefined variable for a superuser without Trainer/Tutor membership.
  Task/attestation import failures use `add_error()` and retain visible messages.
- Checker-result tables use concrete checked checker targets and Solution
  instances, building separate result maps and aligned nullable display cells
  instead of mutating dictionaries into lists. Existing ordering, links and
  trainer/superuser access remain covered. File responses explicitly import
  URL quoting and preserve X-Sendfile MIME/length/path headers, development
  serving, and missing-file responses. URL declarations retain all routes while
  explicitly describing both patterns and resolvers.

Added **27 regressions**, all passing in the final focused run. The initial
affected-module run also passed all **193 tests**. The full run executes
**314 tests: 311 pass, one skipped, two fail with the same missing `fakechroot`
executable**. Python 3.10 grammar parsing passes for all 227 included Python
files; runtime verification used Python 3.12/Django 5.2, not an actual Python
3.10 interpreter. B9-touched whitespace checks pass. No database fields, schema
or migrations changed.

Remaining diagnostics: **59 historical migrations, 80 tests/test helpers,
9 model-boundary residuals**. These remain assigned to B10-B12; the strict
command is not yet expected to exit successfully.

**B10 complete: 148 -> 89 errors, 0 warnings.**

The pinned full-project diagnostic multiset removes **59 diagnostics and
introduces none**, ignoring line shifts. All historical migration modules now
have no strict diagnostics. All 227 Python files remain included, with the same
strict rules, dependencies, runtime Django and Python minimum.

- Historical byte-valued help text and verbose names remain bytes at runtime.
  Localized `cast(str, b"...")` expressions bridge the newer stubs' text-only
  metadata parameters; they do not decode, replace or normalize the historical
  values. Each affected module documents this compatibility boundary. Historical
  choice labels, spelling, defaults, field types and operation order are retained.
- Three historical tutorial/tutor many-to-many fields have explicit contextual
  field annotations before being passed into their operations. Both model type
  parameters use the base Model contract: the target and through-model classes
  are generated by the historical app registry, not imported from current
  application models. Their string target, related name and later Tutor-choice
  restriction are unchanged.
- Removed unused imports from historical schema/data migrations. Existing typed
  RunPython callbacks still receive Django's Apps and schema editor and resolve
  historical models through `apps.get_model()`. No callbacks, dependencies,
  reverse handlers or migration files were added or removed.

Added **five historical migration regressions** covering byte metadata/date
defaults, correction operation order, author/checker labels and byte choices,
tutor relation targets/options and historical model identity, and serialized
RunPython callback identity/reversibility. The focused configuration/accounts
run passes **86 tests**.

Before/after snapshots of **all 92 first-party migrations** compare identically
for serialized operations, dependencies, run-before edges, replacements and
initial flags. An isolated fresh in-memory SQLite database migrates to all
**11 leaf targets**, with expected Trainer/Tutor/User/Coordinator groups, all
five configuration chunks and zero deadline tolerance. Configuration
**0007 -> 0008 -> 0007** forward/rollback execution also succeeds and preserves
settings rows. Irreversible data migrations remain irreversible.

The full run executes **319 tests: 316 pass, one skipped, two fail with the same
missing `fakechroot` executable**. The migration dry-run reports only the same
two pre-existing DejaGnu field changes (`test_defs` and `test_case`); no new
migration was generated. Python 3.10 grammar parsing passes for all 227 files;
runtime verification used Python 3.12/Django 5.2, not an actual Python 3.10
interpreter. B10-touched whitespace checks pass.

Remaining diagnostics: **80 tests/test helpers and 9 model-boundary residuals**,
assigned to B11/B12. The full strict command still exits unsuccessfully until
those remaining diagnostics are resolved.

**B11 complete: 89 -> 9 errors, 0 warnings.**

The pinned full-project diagnostic multiset removes **80 diagnostics and
introduces none**, ignoring line shifts. All tests and test helpers now pass
strict checking. All 227 Python files remain included, with unchanged strict
rules, dependency pins, runtime Django and Python minimum.

- Group-admin tests use the inherited primary key and custom-user membership
  queries. Gave the two identically named group-replacement tests distinct names,
  restoring coverage of replacement without creating missing users as well as
  replacement with new users.
- Checker-result tests use the checked generic relation accessor. R-checker
  fixtures assert the guessed MIME type is present before storing it; missing
  MIME registrations still fail explicitly, with no default masking the failure.
- CUnit metadata assertions narrow model fields before reading their labels.
  The rename-file test selects concrete checker forms rather than matching
  generated class names, copies their initial mapping and explicitly requires
  an inline form. It uses the form's initial model values instead of protected
  model attributes. Both the filename-error and force-save assertions remain.
- Statistics tests use the supported URL resolver and typed introspection
  results; unused imports and unpacked values are removed. Diff tests use the
  default `splitlines()` behavior rather than an integer boolean argument.
- The test runner narrows the configured storage to filesystem storage before
  redirecting uploads to its test directory. Unsupported storage raises an
  explicit error rather than assigning an undeclared attribute.

The focused accounts/checker/solutions/statistics run executes **185 tests:
184 pass and one is skipped**. The full run executes **320 tests: 317 pass, one
is skipped and two fail with the same missing `fakechroot` executable**. The
count increases by one because the previously shadowed group test now runs.
The final CUnit rename-file regression also passes separately after the
mapping-copy refinement. No tests were skipped or assertions relaxed to hide
the environmental failures.

Python 3.10 grammar parsing passes for all 227 files. Runtime verification uses
Python 3.12/Django 5.2, not an actual Python 3.10 interpreter. B11-touched
whitespace checks pass. No model, migration or dependency changes were needed.

Remaining diagnostics: **six in attestation models and three in task models**.
These remain assigned to B12 alongside final closure and enforcement; the
project-wide strict command still exits unsuccessfully until they are resolved.

**B12 complete: 9 -> 0 errors, 0 warnings.**

The pinned full-project diagnostic multiset removes **nine diagnostics and
introduces none**. All 227 files pass the configured strict check, including
tests, historical migrations and the checker example. The end-to-end reduction
from the bundle planning baseline is **1,364 -> 0 errors**. No exclusions,
diagnostic suppressions, relaxed rules, dependency changes or Python-minimum
changes were needed for closure.

- Removed unused model imports and an unused attestation-export task collection.
  Removed only the unused assignment of the final-checker result: the checker
  call, its arguments, task-completion updates and returned solution count are
  preserved.
- Annotation diffs now use `splitlines()` rather than an integer boolean
  argument. Added three regressions for CRLF/CR normalization and blank borders,
  added/removed lines and interior blank lines, and empty/blank-only inputs.
- Added an independent **Strict Pyright (Python 3.10 target)** job to the existing
  workflow. It installs required native build dependencies, uses a Python 3.10
  `.venv` matching the existing Pyright configuration, installs runtime and
  pinned development requirements, and runs
  `.venv/bin/python -m pyright --project . --warnings`. Errors and warnings fail
  the job. It does not depend on the runtime-test job succeeding.
- Updated the README with reproducible environment setup, the enforced command
  and runtime prerequisites. The CI job is configured for pushes and pull
  requests; no branch-protection settings were changed.

Verification:

- The exact strict command exits successfully locally: **zero errors, warnings
  or informational diagnostics**. Local Pyright remains 1.1.414 with
  django-stubs 6.0.9, static Python 3.10 and runtime Django 5.2.
- All **54 focused attestation/task tests pass**.
- The full enabled-application run executes **323 tests: 320 pass, one skipped,
  two fail** with the same `fakechroot: command not found` output in the C upload
  integrations. No failures were hidden or newly skipped.
- Re-ran the full suite in the disposable Docker app container using Python
  3.14.4/Django 5.2.17 and a compatible JDK 21, installing checker OS packages
  only inside that one-off container. With `CI=1`, **320 tests pass and three
  are skipped**: the two C upload tests have an existing `skipIf('CI'...)`
  guard, and one other test is already skipped. The remaining enabled suite is
  green. A no-CI container run confirms those two C tests also need a compatible
  sandbox path setup; the image's default Java 26 separately breaks the legacy
  DejaGnu Security Manager test. These are Docker/toolchain limitations, not
  evidence those tests pass. No Docker service was started and no Docker
  repository configuration or persistent data was changed.
- Installed the pinned development typing requirements in a separate
  disposable Docker app container and ran the complete strict Pyright check
  against its Python 3.14 interpreter: **zero errors and zero warnings**.
- Django startup/system checks pass. Fresh in-memory SQLite migration replay
  reaches all **11 leaf targets**, preserving all four role groups, five chunks
  and zero deadline tolerance. Configuration **0007 -> 0008 -> 0007** rollback
  validation preserves settings primary keys. All **92 first-party migration
  operation/graph snapshots** still match B10 exactly.
- The schema dry-run still reports only the two pre-existing DejaGnu field
  differences (`test_defs` and `test_case`); no migration was generated.
- Python 3.10 grammar parsing passes for all 227 files. Runtime tests were run
  on Python 3.12/Django 5.2, not an actual Python 3.10 interpreter. The workflow
  YAML parses and its Python 3.10 interpreter/strict command were checked
  locally; a hosted GitHub Actions execution has not been run from this session.
- The legacy `sessionprofile` app and middleware remain disabled in the default
  settings. Attempting to include its runtime suite in that configuration fails
  at model import because the app is not installed; it is not part of the
  323-test enabled-application run. Its source remains in the passing strict
  scope. Enabling or modernizing that optional PHP integration is outside B12.
- B12-touched code, workflow and documentation whitespace checks pass.

**Typing remediation is complete.** Remaining runtime prerequisites and existing
schema drift are recorded above; they are not suppressed by the passing type
check or treated as successful runtime validation.

### Bundle order and original sizing

The order below is a dependency-level plan, not a strict file-by-file sequence.
The domain models reference each other, so their shared ORM contracts belong in
one foundational bundle rather than an artificial ordering of individual models.
Independent bundles can run earlier or alongside the main dependency chain.

Counts assign each current diagnostic to one primary file group, exactly once.
They sum to 1,364, but are **not estimates of errors fixed by that bundle**:
upstream fixes can remove diagnostics in downstream groups, and more accurate
types can expose previously masked errors. Recount after each bundle.

| Bundle | Scope and intended outcome | Current file-group errors | Prerequisites |
| --- | --- | ---: | --- |
| B1 | Domain/ORM foundations: model identities, managers, primary keys, reverse relations, inherited field contracts | 88 | None |
| B2 | Application request/user contract: authentication middleware, lazy user resolution, generic view decorators | 42 | B1 |
| B3 | Settings and process-execution primitives: dynamic defaults, configuration overrides, subprocess/container option lifetimes | 70 | None; independent lane |
| B4 | File, upload, serialization and mail contracts, primarily solution models | 63 | B1 for model-facing contracts |
| B5 | External integration and rendering boundaries: LDAP, statistics, syntax highlighting, template chunks | 142 | B1 for LDAP user integration; independent sub-batches otherwise |
| B6 | Checker engine and implementations: environment/results, compiler inheritance, concrete checkers and example | 148 | B1, B3, B4 |
| B7 | Form validation and formset contracts | 28 | B1, B4 |
| B8 | Admin contracts: model/inline generics, fieldsets, form factories, display/action metadata | 90 | B1, B6, B7 |
| B9 | HTTP consumers: views, Shibboleth views, routing and response/template contexts | 531 | B2, B4, B5, B6, B7 |
| B10 | Historical migration typing and metadata | 60 | Independent lane; preserve historical state |
| B11 | Remaining test-consumer and fixture typing | 102 | Relevant producer bundles B1-B9; B10 for final migration validation |
| B12 | Final strict-check closure and CI enforcement | Recount residuals | B1-B11 |

### B1: Establish the domain contracts first

- Start with `accounts.models.User`: manager specialization, inherited Django
  field descriptors, primary-key visibility, and the base-user/custom-user
  relationship. Do not replace descriptor types with incompatible plain fields
  or narrow an invariant inherited manager.
- Establish reverse-relation contracts used across User/Tutorial, Task,
  Solution/SolutionFile, Attestation and checker results. Include the ORM-facing
  portions of solution models here even though that file's diagnostics are
  counted under B4.
- Treat the mutually referencing models as one contract boundary. Resolve
  shared model identities before annotating individual consumers.
- Exit: actual manager results and relation element types are known, with
  runtime model registration and database behavior unchanged.

### B2: Carry the application user type through the HTTP boundary

- Fix the imported/custom authentication middleware name collision, lazy-user
  return contract and request cache contract.
- Describe the distinction between an anonymous request and a request whose
  user is Praktomat's custom User. Authentication alone must not be treated as
  proof of the custom subclass without verifying the middleware path.
- Preserve decorated callable parameters/return types and anonymous redirects.
  Do not narrow global `HttpRequest.user` or scatter unchecked casts over views.
- Verify login, inactive-account handling, disclaimer redirects and Shibboleth
  behavior before migrating view signatures to the established contract.
- Leverage: the baseline contains **211 direct missing-attribute diagnostics**
  against Django's generic `_User`/`AnonymousUser`, plus downstream unknown
  values. Those 211 are diagnostic instances, not independent root causes or a
  promised reduction.

### B3: Stabilize configuration and execution inputs

- Make the dynamic settings-default construction and intentional configuration
  overrides explicit without inventing production defaults for missing values.
- Resolve process/container branches that leave file-size limits, container
  names or volume lists possibly unbound; preserve error reporting and cleanup.
- Check Python 3.10 API availability, including uses of
  `string.Template.get_identifiers`.
- Exit: checker infrastructure receives defined, correctly typed settings and
  process options. This bundle can start alongside B1.

### B4: Settle file and serialization invariants

- Establish when stored files may lack a name, how required names are validated,
  and when underlying streams are available. Fix producers/validation rather
  than applying non-null assertions at every path operation.
- Settle real and generated/dummy file contracts, archive imports, upload
  validation and serializer input/output contracts.
- Handle regex-match failure explicitly where file paths are parsed.
- Keep Django 5.2 mail behavior authoritative: the newer stubs' lazy-string,
  MIME-message and `message(policy=...)` contracts need a deliberate compatible
  solution, not a Django 6 API change imposed on the runtime.
- Exit: path/content/upload contracts are reusable by checker implementations
  and forms; tests cover invalid/missing files and serialization paths.

### B5: Contain external and rendering boundaries

Implement as independent, reviewable sub-batches, not one large integration
rewrite:

- LDAP: verify dependency types and correlated string/bytes attribute values,
  then type authentication/import results consumed by account views.
- Statistics: establish query/aggregation rows and plotting-library inputs.
- Highlighting/lexer integration: settle actual token, formatter and HTML-result
  contracts before annotating their consumers.
- Template chunks: resolve possibly unbound result paths while preserving the
  intended missing-chunk/error behavior.

Use existing dependency typing where available. If a narrow local stub, helper
type or runtime correction is necessary, justify that separately rather than
substituting broad `Any` or permanent suppressions.

### B6: Fix the checker family from base to leaf

- Start with `CheckerEnvironment`, `CheckerResult`, generic checker relations,
  artefacts and optional executable/checker state.
- Then resolve compiler/builder/linker inheritance and mutable override
  contracts, followed by concrete checkers, scripts and the documented example.
- Reuse B4's file contracts instead of independently narrowing filenames.
- Exit: base/derived contracts agree, and targeted checker tests preserve
  execution, failure and cleanup behavior.

### B7-B9: Repair consumers after their producers

- B7: typed form instances and cleaned-data validation, optional `clean()`
  results, formset element types and compatible form `Meta` definitions.
- B8: admin model/inline relationships and form factories after model/checker
  contracts are established; prefer supported display/action decorators over
  assigning arbitrary attributes to functions where behavior is equivalent.
- B9: work through account, solution, attestation and utility views using B2's
  request contract and B7's validation contracts; then wire URL callbacks and
  template contexts. Resolve real missing-response/uninitialized-variable paths,
  not just their annotations.
- Prioritize attestation/solution views once B2 is ready: their current file
  totals are 296 and 125 respectively. Do not manually patch each occurrence of
  a missing user attribute before resolving the HTTP boundary.
- B8 is not a prerequisite for B9 merely because it appears first in the table.
  Only shared contracts and actual imports/calls create dependencies.

### B10: Keep migrations a separate historical-state lane

- Resolve constructor generics and historical bytes/string metadata without
  importing present-day model classes to stand in for historical models.
- Preserve field deconstruction and migration state; validate replay on a fresh
  test database. Do not add runtime subscripting of Django classes that only
  support generics in stubs.
- This is useful independent progress, but should not displace B1/B2 merely
  because its diagnostics are easier to count.

### B11-B12: Close the check, then enforce it

- Run targeted runtime tests throughout B1-B10; B11 is for remaining test-code
  contracts, not a reason to postpone tests until the end.
- Recheck fixtures, client-response contracts, checker integration tests and
  resolver callbacks against the settled producers.
- Fold unused-import/variable and similar local cleanup into the owning bundle;
  do not lead with cosmetic cleanup or count it as unlocking downstream work.
- B12: run the full configured strict check with zero errors/warnings, check
  startup and migration replay, run all runtime suites, then enable the same
  strict command in CI. Keep the missing-`fakechroot` environment failures
  separately visible; do not suppress or silently skip them.
- Preserve Python 3.10 support, Django 5.2 LTS and the full configured source
  scope throughout. Report baseline, removed/new diagnostics and runtime results
  after every bundle.

Recommended starting sequence: **B1 -> B2**, with B3 and B10 as independent
lanes; then B4, B5, B6 and B7 as their prerequisites become available. Finish
consumer work in B8/B9, followed by B11/B12. Split each bundle into small coherent
patches with its own verification; a bundle is not a single giant commit.

## Phases

1. **Inventory and baseline**
   - Confirm the supported Python range (currently documented as Python 3.10
     and newer) and enumerate all maintained first-party Python source files.
   - Check existing dependencies for type information and identify dynamic or
     untyped integration boundaries.
   - Install/run Pyright in strict mode and record the initial diagnostics for
     application code, tests, and migrations. Use this baseline to plan
     incremental fixes, not to justify permanent omissions.
   - **Initial baseline:** Pyright 1.1.414 analyzed 225 files in strict mode
     targeting Python 3.10. It reported 9,715 errors without Django stubs.
     The initially selected Django 5.2 stubs, django-stubs 5.2.9, reduced that
     to 7,015 errors (2,700 fewer) and support Python 3.10. They were later
     replaced by development-only django-stubs 6.0.9, which also supports
     Python 3.10 and partially supports Django 5.2; see the measured upgrade
     below. The newer django-stubs 6.1.2 release was rejected because it
     requires Python 3.11 or newer. That restriction does not apply to every
     6.x stub release.

2. **Configure the checker**
   - Add a `pyproject.toml` with strict Pyright settings, the Python 3.10 target,
     and explicit source/import paths appropriate to the repository layout.
   - Add Pyright as a development tool, without making it a runtime dependency.
     Since the project currently uses `requirements.txt` and has no packaging
     setup, use a separate development requirements file for Pyright and any
     typing support rather than adding these tools to runtime requirements.
   - Evaluate `django-stubs` against actual Django diagnostics. Pyright does not
     run the django-stubs mypy plugin, so use its available stubs and keep the
     dependency only if a small trial demonstrates a meaningful improvement
     for this project's Django typing.

3. **Resolve diagnostics incrementally**
   - Fix missing or inaccurate annotations and closely related type errors in
     small, reviewable batches.
   - Prefer precise types and existing project conventions.
   - Handle dynamic or untyped dependency boundaries narrowly and explicitly.
     Do not use broad `Any`, blanket exclusions, global suppressions, or
     globally relaxed rules merely to make the check pass. Keep any necessary
     suppressions local, minimal, and justified.
   - **Progress:** The first annotation batch added 19 verified return,
     parameter, and field annotations across eight source files. Full strict
     Pyright now reports 6,983 errors across 225 files, down from the
     7,015-error Django-stubs baseline, with no new diagnostic messages.
     `accounts.models` is down from 84 to 80 errors; its Django field typing
     remains a major source of baseline diagnostics. The changed utility and
     management-command files otherwise pass, except for the existing
     possibly-unbound `archive_name` diagnostic in `install_demo_db.py`.
     The `accounts` and `solutions` Django tests passed (17 tests), and a
     runtime check confirmed the activation-key field remains registered as
     a 40-character, non-editable `CharField`.
   - **Second annotation batch:** Added verified `str | bytes -> str` and
     `str -> bytes` signatures to the encoding helpers; made `nub` generic
     over hashable iterable elements; and annotated supported signatures in
     `file_operations.py`, `update_model_graph.py`, `exceptionlogger.py`, and
     `TestSuite.py`. The middleware and `nub` pass targeted strict Pyright;
     the Django test-utility module retains unrelated diagnostics, including
     an untyped test-client response contract and Django-stub gaps. The
     `accounts` and `solutions` test suites passed again (17 tests).
     Full strict Pyright now reports 6,864 errors across 225 files: 119 fewer
     than the 6,983-error baseline after the first annotation batch and 151
     fewer than the initial 7,015-error Django-stubs baseline. Two new
     call-site diagnostics remain from stronger contracts: an unknown `nub`
     input in `attestation.models` and imprecisely typed subprocess output in
     `checker.checker.DejaGnu`. The `create_file` content parameter in
     `file_operations.py` remains unannotated: its accepted type depends on
     the `binary` flag, and a partial signature introduced a downstream
     diagnostic, so that change was reverted rather than masking the
     relationship with `Any`. The `assertRedirectsToView` helper in
     `TestSuite.py` also remains unannotated because its response uses a
     dynamic `redirect_chain` attribute not represented by Django's stubs;
     annotating only part of its public signature caused new unknown-type
     diagnostics at its callers, so the partial edit was reverted. The
     pre-existing malformed `UnicodeDecodeError` construction in
     `encoding.py` is unchanged.
   - **Third annotation batch:** Added parameter and return annotations to
     `DeletingFileField.contribute_to_class` and `delete_file`. Targeted
     Pyright now reports only two existing diagnostics in that module: the
     override's pre-existing signature mismatch with Django's `FileField`
     stub, and the pre-existing unknown receiver type in the signal stub.
     Full strict Pyright reports 6,847 errors across 225 files (136 fewer
     than the 6,983-error baseline after the first annotation batch and 168
     fewer than the initial 7,015-error Django-stubs baseline). The same two
     stronger-contract call-site diagnostics remain in `attestation.models`
     and `checker.checker.DejaGnu`; no additional diagnostics were introduced
     by this batch.
   - **Fourth annotation batch:** Added string input/return types to the
     Isar decoder, a regex match type to its replacement callback, and a
     string input type to the lexer override. An Isar lexer smoke check
     passed. Its existing global decode-table mutation prevents Pyright from
     narrowing `symbol_table` reliably, so that variable remains unannotated;
     the method's return type also remains unresolved because Pygments
     exposes a private token type and its override has a pre-existing
     signature mismatch. The verified `str` decoder input surfaces two
     additional diagnostics in existing code: a redundant `isinstance` and
     the closure's inability to narrow the global table. Full strict Pyright
     reports 6,835 errors across 225 files (148 fewer than the 6,983-error
     baseline after the first annotation batch and 180 fewer than the initial
     7,015-error Django-stubs baseline). The two previous call-site
     diagnostics remain; no other new diagnostics were introduced.
   - **Fifth annotation batch:** Added model-specific generic types to the
     `SessionProfile` foreign-key fields and typed the obsolete management
     command's unused keyword options. `sessionprofile.models` now passes
     targeted strict Pyright with no diagnostics; the two remaining
     `cleanup_inactive_sessions.py` diagnostics are for the pre-existing
     removed `transaction.commit_unless_managed` API. Full strict Pyright now
     reports 6,829 errors across 225 files, six fewer than the 6,835-error
     prior run. The session-profile runtime test could not complete because
     its custom test database setup attempted to create an auth user before
     the `auth_user` table existed; no application-code failure was observed.
   - **Sixth annotation batch:** Typed the reusable list template filter and
     the WSGI test loader, and added return annotations and optional-value
     checks to system-locale and WSGI tests. The affected modules pass targeted
     strict Pyright; the WSGI tests passed (3 tests), and the system-locale
     tests passed (7 tests) when run with their required `LANGUAGE=en`
     environment value. Full strict Pyright now reports 6,817 errors across
     225 files, six fewer than the 6,823-error prior run.
   - **Seventh annotation batch:** Added lifecycle and test return annotations
     to `hbrs_tests.test_admin_tasks_listview` and removed its unused
     `TaskAdmin` import. The module passes targeted strict Pyright and its two
     Django tests pass. Full strict Pyright now reports 6,816 errors across
     225 files, one fewer than the 6,817-error prior run.
   - **Eighth annotation batch:** Added lifecycle and test return annotations
     to `hbrs_tests.test_admin_solutions_listview`, removed its unused admin
     import and unused local variables, and retained the existing view checks.
     The module passes targeted strict Pyright and all three Django tests pass.
     Full strict Pyright now reports 6,813 errors across 225 files, three
     fewer than the 6,816-error prior run.
   - **Ninth annotation batch:** Added lifecycle and test return annotations
     to `configuration.tests` and removed its unused date imports. Targeted
     strict Pyright passes and both configuration tests pass. Full strict
     Pyright now reports 6,811 errors across 225 files, two fewer than the
     6,813-error prior run.
   - **Tenth annotation batch:** Removed five unused imports from
     `update_model_graph.py` using Pylance's unused-import refactoring. The
     management command passes targeted strict Pyright. Full strict Pyright
     now reports 6,806 errors across 225 files, five fewer than the
     6,811-error prior run.
   - **Eleventh annotation batch:** Added return annotations to the
     `sessionprofile` tests and removed unused imports and request-result
     variables; targeted strict Pyright passes. Fixed the malformed
     `UnicodeDecodeError` construction in `encoding.py`, and removed the
     unused Django admin import from `taskstatistics/admin.py`. Encoding smoke
     checks passed and all three changed modules pass targeted strict Pyright.
     Full strict Pyright now reports 6,800 errors across 225 files, six fewer
     than the 6,806-error prior run. The session-profile Django test remains
     blocked by the custom test runner trying to insert fixture users before
     creating the `auth_user` table.
   - **Twelfth annotation batch:** Typed the MOTD template tag callback and
     node with Django's `Parser`, `Token`, and `Context` types, confirmed
     against Django's runtime signatures. It passes targeted strict Pyright;
     only intentionally unused framework callback parameters remain as
     editor hints. Full strict Pyright now reports 6,791 errors across 225
     files, nine fewer than the 6,800-error prior run.
   - **Thirteenth annotation batch:** Added model type arguments to the
     configuration admin inline and model admin, and typed the permission
     request and return. Django's admin classes are not subscriptable at
     runtime, so the type arguments are guarded by `TYPE_CHECKING`; the
     project's Django system check and configuration tests pass. Two
     pre-existing Django-stub diagnostics remain for the inline list and
     `admin.site.register`. Full strict Pyright now reports 6,787 errors
     across 225 files, four fewer than the 6,791-error prior run.
   - **Fourteenth annotation batch:** Reworked the demo-database command's
     backup error path to handle filesystem errors without referencing an
     uninitialized archive variable, include the backup location only after
     a backup is successfully created, and preserve the original exception
     as the cause. Targeted strict Pyright now passes for this command. The
     command itself was not executed because it deletes and replaces the
     configured upload directory; Django's system check passed. Full strict
     Pyright now reports 6,786 errors across 225 files, one fewer than the
     6,787-error prior run.
   - **Fifteenth annotation batch:** Typed the checker management command's
     `CommandParser` and Django's dynamic positional/keyword pass-through
     arguments, and added model-specific field types for `Task.title` and
     `Task.all_checker_finished` so the command can be checked without
     unknown task attributes. Targeted strict Pyright passes for the command,
     and Django's system check passes. Full strict Pyright now reports 6,772
     errors across 225 files, 14 fewer than the 6,786-error prior run.
   - **Sixteenth annotation batch:** Added the known `int` type for Task's
     default AutoField primary key and annotated the two Task fields used by
     the command. Added lifecycle and test return annotations to
     `tasks.tests` and removed its unused `Solution` import. The nine task
     tests passed, Django's system check passed, and the command passes
     targeted strict Pyright; one unresolved diagnostic remains in the test
     helper call. Full strict Pyright now reports 6,738 errors across 225
     files, 34 fewer than the 6,772-error prior run.
   - **Seventeenth annotation batch:** Removed the obsolete
     `transaction.commit_unless_managed()` call from the session cleanup
     management command. Modern Django runs database operations in
     autocommit by default; removing the unavailable API also avoids forcing
     a commit if the command is called inside an outer transaction. Targeted
     strict Pyright and Django's system check pass. Full strict Pyright now
     reports 6,736 errors across 225 files, two fewer than the 6,738-error
     prior run. The command was not run because it deletes expired sessions.
   - **Eighteenth annotation batch:** Typed `settings.defaults.load_defaults`
     to accept a mutable string-keyed settings mapping and removed the
     overwritten first `UPLOAD_ROOT` assignment in test settings. Django's
     system check passes; Pyright no longer reports the test-settings constant
     redefinition or unknown loader call. The defaults module still has many
     dynamic-global diagnostics. Full strict Pyright now reports 6,728 errors
     across 225 files, eight fewer than the 6,736-error prior run.
   - **Nineteenth annotation batch:** Removed three overwritten initial
     assignments in development settings and explicitly typed/configured its
     middleware list. The explicit list preserves the defaults loader's
     middleware behavior while allowing the final exception-logging middleware
     to be appended without reassigning an uppercase constant. Targeted strict
     Pyright and Django's development-settings system check pass. Full strict
     Pyright now reports 6,723 errors across 225 files, five fewer than the
     6,728-error prior run.
   - **Twentieth annotation batch:** Added precise Django field generic types
     to 21 configuration model fields and annotated `Chunk.__str__`'s return
     type. The `DateTimeField` value type includes both `date` and `datetime`:
     a runtime check confirmed that a new `Settings` instance initially holds
     the configured `date` default, while persisted values are used as
     datetimes. The model passes targeted strict Pyright with no diagnostics;
     both configuration tests and Django's system check pass. Full strict
     Pyright now reports 6,649 errors across 225 files, 74 fewer than the
     6,723-error prior run.
   - **Twenty-first annotation batch:** Added the verified `Settings` return
     type to `configuration.get_settings`, using a type-checking-only import
     to preserve its lazy runtime model import. Targeted strict Pyright, the
     Django system check, and the post-change public-surface check pass; the
     full strict check remains at 6,649 errors across 225 files.
   - **Twenty-second annotation batch:** Added explicit generic types to all
     28 existing Django model fields in the unmanaged task-statistics view,
     using the field declarations in its migration as evidence for the
     database view's ORM schema. A type-checking-only import supplies the
     related `Task` model without changing runtime imports. Targeted strict
     Pyright and Django's system check pass, and all 12 task-statistics tests
     pass. The two remaining missing-annotation entries are the unmanaged
     model's `Meta` options. Full strict Pyright now reports 6,625 errors
     across 225 files, 24 fewer than the 6,649-error prior run.
   - **Twenty-third annotation batch:** Added verified Django field generics
     and method signatures in `attestation.models`, including the XML export's
     `str` return. The attestation tests (9) and Django's system check pass.
     Full strict Pyright now reports 6,427 errors across 225 files, down from
     6,625.
   - **Twenty-fourth annotation batch:** Typed the existing Django fields and
     verified method/helper contracts in `solutions.models`, including the
     solution number's transient `None` state, the solution-file callback,
     checker-result lists, and the email-wrapper byte/message APIs. Related
     model imports are type-checking-only and privately aliased to avoid
     runtime re-exports. All 11 solution tests and Django's system check pass.
     The compact public-surface report has one remaining ambiguity,
     `User.mat_number`, which is declared in `accounts.models` rather than this
     target. Twenty-one syntactic annotation candidates remain in the module:
     dynamic Django `save`/signal/email parameters and an untyped `FileField`
     boundary are unresolved; the regex declarations are directly inferred
     from their literal/constructor expressions and were left without
     score-only annotations. Full strict Pyright now reports 6,213 errors
     across 225 files, down from 6,427.
   - **Twenty-fifth annotation batch:** Added verified nullable/non-nullable
     Django field generics and method return types in `accounts.models`,
     including the transient nullable student number and tutorial relation.
     The accounts tests (6) and Django's system check pass. The compact
     public-surface report has no ambiguous items in this module. Remaining
     annotation candidates involve Django's validator and inherited model
     stubs, dynamic constructor/import/signal inputs, and metadata or dynamic
     staticmethod assignment; they remain unresolved rather than being given
     guessed types. An explicit `User.objects` manager annotation was omitted
     because it conflicts with the inherited class-level manager declaration.
     Full strict Pyright now reports 6,156 errors, down from 6,213 across the
     same 225 files.
   - **Twenty-sixth annotation batch:** Added verified `HttpRequest`,
     route-captured `str` task IDs, and `HttpResponse` return contracts to
     the task views, plus an iterable/task-list contract for their nested
     template-data helper. Annotation-only imports are privately aliased so
     the module's implicit public re-export surface stays unchanged. The
     tasks tests (9) and Django's system check pass; `tasks.views` has no
     remaining function or parameter annotation candidates. Its two form
     field declarations are already inferred from Django field constructors
     and were left untouched. The only ambiguous public-surface item remains
     the imported `Task.jplag_up_to_date` field in `tasks.models`; existing
     diagnostics around custom user fields, task methods, and Django form
     internals remain outside this annotation batch. Full strict Pyright now
     reports 6,101 errors, down from 6,156 across the same 225 files.
   - **Twenty-seventh annotation batch:** Added all 27 verified return
     annotations, 17 of 18 parameter annotations, and 26 concrete Django
     field generics in `tasks.models`. This resolves its compact public-surface
     ambiguity count from one (`Task.jplag_up_to_date`) to zero without
     changing the module's re-export surface. The `Task.import_Tasks` file
     parameter remains unresolved because the standard-library ZIP reader
     accepts a private readable-file protocol that cannot be represented
     faithfully inline without a helper declaration. `Meta.ordering` is a
     directly inferred configuration literal; the two custom
     `DeletingFileField` declarations remain constructor-inferred and do not
     appear as ambiguous public types. The combined task and solution tests
     (20) and Django's system check pass. Full strict Pyright now reports
     5,941 errors, down from 6,101 across the      same 225 files.
   - **Twenty-eighth annotation batch:** Added verified request, queryset,
     response, and URL-pattern contracts to the task admin actions and display
     helpers. The annotation-only Django imports are privately aliased, leaving
     the module's public re-export surface unchanged; its compact public-surface
     report has no ambiguous items. Nineteen remaining candidates are Django
     admin configuration values and inline metadata, which are inferred or
     framework-managed and were not annotated just to reduce the candidate
     count. The task tests (9) and Django's system check pass. Full strict
     Pyright now reports 5,870 errors across 225 files, down from 5,941.
   - **Twenty-ninth annotation batch:** Typed solution-admin queryset and
     action contracts, filter lookups, read-only-field configuration, and
     display helpers; added model-specific Django admin generics without
     changing runtime bases or the module's re-export surface. The two
     queryset-derived boolean display methods remain unresolved because Django
     stubs do not expose their dynamically annotated fields. The remaining
     19 annotation candidates are framework configuration metadata. The
     solution tests (11), Django's system check, and whitespace check pass.
     Full strict Pyright now reports 5,790 errors across 225 files, down from
     5,870.
   - **Thirtieth annotation batch:** Added model-specific types to the
     attestation admin classes and verified request, queryset, response,
     display, URL-pattern, and permission contracts. The `get_form` and
     foreign-key form-field hooks remain unresolved because they communicate
     through a dynamically attached `request.obj`; annotating only part of
     that contract would leave the boundary unsound. The public re-export
     surface remains unchanged. Attestation tests (9), Django's system check,
     and whitespace check pass. Full strict Pyright now reports 5,764 errors
     across 225 files, down from 5,790.
   - **Thirty-first annotation batch:** Added verified form, queryset, request,
     and display contracts to the checker-result admin and typed its
     model-specific admin base. The polymorphic checker inline formset hook
     remains untyped because its subclasses use different model types; the
     inline's base form is likewise generic across those models. Its implicit
     re-export surface is unchanged. Django's system check and whitespace
     check pass. Full strict Pyright now reports 5,749 errors across 225 files,
     down from 5,764.
   - **Thirty-second annotation batch:** Added verified boolean display,
     admin-action, export, URL, save, and user/tutor display signatures in
     `accounts.admin`; specialized its Django user and tutorial admin bases
     without altering their runtime classes. Twelve remaining annotation
     candidates are framework configuration values. The module's public
     re-export surface remains unchanged. The accounts tests (6), Django's
     system check, and whitespace check pass. Full strict Pyright now reports
     5,675 errors across 225 files, down from 5,749.
   - **Thirty-third annotation batch:** Added the typed projected-queryset
     return, the statistics-data and graphic-list contracts, and request and
     response types to the statistics views. The DataFrame row passed to
     `boxblot_to_graphic_list` remains dynamic because pandas creates its
     named-tuple fields from runtime columns. The `fliers` mapping remains
     unresolved because its heterogeneous list values cannot be described
     faithfully inline without a helper declaration, and `None` is the
     default although the implementation rejects it. Public-surface
     completeness remains unchanged. Task-statistics tests (12), Django's
     system check, and whitespace check pass. Full strict Pyright now reports
     5,574 errors across 225 files, down from 5,675.
   - **Thirty-fourth annotation batch:** Annotated all 14 test methods with
     verified `None` returns and typed the test helpers' string parameters
     and CSRF-stripping return. The table-description helper retains its
     return type unresolved because Django's database-introspection API is
     `Any` in the available stubs. The test module's public-surface report
     remains unambiguous. Task-statistics tests (12), Django's system check,
     and whitespace check pass. Full strict Pyright now reports 5,560 errors
     across 225 files, down from 5,574.
   - **Thirty-fifth annotation batch:** Added verified `HttpRequest` parameter
     types to the lazy-user descriptor and accounts middleware hooks, with
     response-or-`None` returns for the redirecting middleware. `LazyUser`
     retains an unresolved return because it caches the dynamically wrapped
     custom/anonymous user, and the middleware's existing class-name shadowing
     and request-user monkeypatch remain outside inline typing scope. The
     module's compact public-surface report is unambiguous. Accounts tests (6),
     Django's system check, and whitespace check pass. Full strict Pyright now
     reports 5,544 errors across 225 files, down from 5,560.
   - **Thirty-sixth annotation batch:** Added verified request, path, captured
     ID, and response types to all seven file-serving views and helpers in
     `utilities.views`. File-serving responses use `HttpResponseBase` because
     Django's development server can return a `FileResponse`. Strict Pyright
     now reports 5,471 errors across 225 files, down from 5,544. The focused
     C/Cpp checker tests ran 18 cases; two failed because the test execution
     environment lacks `fakechroot`, causing checker assertions to fail.
     Django's system check passes. Remaining diagnostics in this module
     concern Django's custom-user typing boundary, the imported untyped
     `access_denied` view, and the existing `urllib.parse` attribute usage.
   - **Thirty-seventh annotation batch:** Resolved the existing `datetime`
     name in `Settings.deny_registration_from`'s explicit `DateTimeField`
     generic using a private import alias. This removes all three strict
     diagnostics from `configuration.models` without changing its public
     surface. Configuration tests (2), Django's system check, and whitespace
     checks pass. Full strict Pyright now reports 5,464 errors across 225
     files, down from 5,471.
   - **Thirty-eighth annotation batch:** Added the `create_file` path/content
     contract (`str`/`bytes`) and explicit validation for binary writes, and
     typed the session-profile response middleware and nullable profile user
     field. Runtime checks confirmed both UTF-8 text and byte-for-byte binary
     writes; all changed files type-check. The session-profile test command
     is blocked during the custom runner's fixture setup by a missing
     `auth_user` table, while Django's system check passes.
   - **Thirty-ninth annotation batch:** Replaced the Isar lexer wildcard token
     import with explicit imports, typed the symbol table, removed the
     redundant string conversion branch, and matched the inherited lexer
     stack parameter. Runtime decoding and tokenization checks pass. The two
     remaining lexer diagnostics are external Pygments typing gaps (theorem
     lexer stub and `bygroups`).
   - **Fortieth annotation batch:** Typed the test redirect assertion's
     response and view parameters and its dynamically added redirect chain;
     the four call sites are signature-compatible. Removed an unused
     test-fixture assignment. The helper's remaining diagnostics concern
     Django's dynamic storage location and incompletely typed group managers.
   - **Forty-first annotation batch:** Matched `DeletingFileField`'s
     `contribute_to_class` signature to Django's `**kwargs` contract and
     forwarded those arguments to the base field method. Added the explicit
     integer primary-key type for `Attestation` and `None` returns throughout
     the attestation tests; the test module now type-checks cleanly. Task
     tests (9), attestation tests (9), Django's system check, and whitespace
     validation pass. The session-profile tests remain blocked by the runner
     setup issue above. Full strict Pyright now reports 5,392 errors across
     225 files, down from 5,464. Remaining diagnostics in edited files are
     limited to Django/Pygments stub boundaries and pre-existing
     `attestation.models` diagnostics.
   - **Forty-second annotation batch:** Added explicit `Any` keyword
     passthrough parameters and `None` returns to the compiler `CheckerForm`
     constructors in the C, C++, Fortran, Java, Scala, Haskell, and C-linker
     builders. Pylance found no direct call sites for these initializers;
     Django's system check passes. Their calls to `ModelForm.__init__` still
     expose an unknown `instance` parameter in django-stubs, while unrelated
     diagnostics in the builder modules remain. Full strict Pyright now
     reports 5,301 errors across 225 files (94 affected), down from 5,392.
   - **Forty-third annotation batch:** Made the compiler package's existing
     lazy submodule exports visible to static analysis with `TYPE_CHECKING`-
     only imports, preserving its runtime lazy-loading and `import *` module
     exports. A runtime check confirmed no submodules load on package import
     and all eight star exports remain modules. The package initializer now
     passes strict Pyright. Django's system check and CRLF-aware whitespace
     validation pass. Full strict Pyright now reports 5,293 errors across
     225 files (93 affected), down from 5,301.
   - **Forty-fourth annotation batch:** Typed the shared checker environment,
     result creation, result fields/setters, and log truncation contracts.
     Added matching execution signatures for LineCounter, AnonymityChecker,
     RChecker, and ScriptChecker, and completed the R-checker field and
     AnonymityChecker helper annotations. The subprocess helper retains its
     existing heterogeneous positional list and exposes it as `list[Any]`
     rather than changing the runtime return shape. The LineCounter and
     AnonymityChecker tests (2), Django's system check, and whitespace
     validation pass. Full strict Pyright now reports 4,877 errors across
     225 files (92 affected), down from 5,293.
   - **Forty-fifth annotation batch:** Typed the model fields, checker
     signatures, and string-processing helpers in `LineWidthChecker` and
     `InterfaceChecker`. Both modules now pass strict Pyright with zero
     diagnostics. Their focused checker tests (2), Django's system check,
     and whitespace validation pass. Full strict Pyright now reports 4,758
     errors across 225 files (90 affected), down from 4,877.
   - **Forty-sixth annotation batch:** Typed `KeepFileChecker`'s filename,
     title, and execution contracts, and typed the shared artefact-creation
     method's filename/path parameters. Removed unused imports and wildcards
     from the checker module without changing its behavior. Both KeepFile
     tests, Django's system check, and whitespace validation pass; the module
     passes strict Pyright. Full strict Pyright now reports 4,731 errors
     across 225 files (89 affected), down from 4,758.
   - **Forty-seventh annotation batch:** Typed the custom user's inherited
     first- and last-name attributes and the input signature of the shared
     `execute_arglist` helper. All 18 helper call sites are signature-
     compatible; typed the R checker's environment mapping and removed
     unnecessary conversions in the anonymity checker. Both checker modules
     pass targeted strict Pyright. The R and anonymity checker tests (5),
     Django's system checks, and CRLF-aware whitespace validation pass. Full
     strict Pyright now reports 4,684 errors across 225 files (87 affected),
     down from 4,731.
   - **Forty-eighth annotation batch:** Added `TYPE_CHECKING`-only imports for
     `checker.checker`'s 18 submodule exports, matching the package's existing
     `__all__` without importing them at runtime. Targeted strict Pyright is
     clean; a runtime check confirmed all 18 `import *` exports remain
     submodule objects, and Django's system check passes. Full strict Pyright
     now reports 4,666 errors across 225 files (86 affected), down from 4,684.
   - **Forty-ninth annotation batch:** Typed CheckStyleChecker's display name,
     checker methods, and execution environment; removed unused imports and
     replaced a wildcard import with its single used helper. Its focused test
     and Django's system check pass, and targeted strict Pyright is clean. Full
     strict Pyright now reports 4,642 errors across 225 files (85 affected),
     down from 4,666.
   - **Fiftieth annotation batch:** Typed IsabelleChecker's model fields,
     output predicate, and execution contract; removed unused imports and
     annotated its subprocess arguments and environment. Fixed the existing
     undefined `setting` reference to use Django's `settings`; a mocked
     runtime check verified Isabelle command construction and result handling.
     Targeted strict Pyright, Django's system check, and CRLF-aware whitespace
     validation pass. Full strict Pyright now reports 4,602 errors across 225
     files (84 affected), down from 4,642.
   - **Fifty-first annotation batch:** Typed JavaChecker's model fields,
     checker methods, execution environment, and subprocess arguments; removed
     the duplicate title declaration and replaced a wildcard import with
     explicit dependencies. Added inherited `id` and `username` types to the
     custom user model, resolving its checker call-site unknowns. Targeted
     strict Pyright is clean; a mocked runtime check verified the Java command
     arguments and result handling, and Django's system check and
     CRLF-aware whitespace validation pass. Full strict Pyright now reports
     4,513 errors across 225 files (83 affected), down from 4,602.
   - **Fifty-second annotation batch:** Typed TextChecker's model fields,
     matching/comment-processing helpers, run method, and log-formatting
     inputs. Targeted strict Pyright is clean; its focused test, Django's
     system check, and CRLF-aware whitespace validation pass. Full strict
     Pyright now reports 4,420 errors across 225 files (82 affected), down
     from 4,513.
   - **Fifty-third annotation batch:** Typed CreateFileChecker's file, path,
     and option fields; sandbox helper methods; run contract; and form
     constructor. Replaced wildcard imports with the two used helpers and
     made its abstract `Meta` inherit the base checker metadata. Added shared
     boolean-field and `show_publicly` types to `Checker`. All five focused
     CreateFileChecker tests, Django's system check, and CRLF-aware whitespace
     validation pass. One targeted Pyright diagnostic remains at the
     django-stubs `ModelForm.__init__` boundary (`instance` is `Unknown`). Full
     strict Pyright now reports 4,293 errors across 225 files (82 affected),
     down from 4,420.
   - **Fifty-fourth annotation batch:** Typed DejaGnu's directory helpers,
     model fields, output processing, requirements, and both checker execution
     methods; replaced wildcard imports and annotated the setup form
     constructor. Added explicit guards where the shared environment's program
     name can be absent. Its focused integration test, Django's system check,
     and CRLF-aware whitespace validation pass. The only remaining local
     diagnostic is the known django-stubs `ModelForm.__init__` unknown
     `instance` type. Full strict Pyright now reports 4,189 errors across 225
     files (82 affected), down from 4,293.
   - **Fifty-fifth annotation batch:** Added typed file-pattern fields and
     string return contracts to the shared builder's `rxarg()` methods,
     typed the Haskell builder execution contract, and completed
     `HaskellTestFrameWorkChecker`'s fields, helpers, and run contract. Its
     runtime helper checks passed and the checker module reached zero
     targeted Pyright errors. CreateFileChecker's five focused tests and
     DejaGnu's focused integration test passed, along with Django's system
     check and CRLF-aware whitespace validation. Full strict Pyright reports
     4,087 errors across 225 files (81 affected), down from 4,189.
   - **Fifty-sixth annotation batch:** Typed AutoAttestChecker's nullable
     author, comment and publication fields, method contracts, environment
     parameter, form model, and nullable `author_id` assignment. Also typed
     the shared checker task/result foreign keys and the checker-result
     `required()` return. The compact public-surface report now has no
     ambiguous exports; remaining module diagnostics are existing unused
     imports and Django-stubs gaps for dynamic model defaults and reverse
     relations. Django's system check, source syntax validation, and
     CRLF-aware whitespace check pass. Full strict Pyright now reports 4,033
     errors across 225 files (81 affected), down from 4,087.
   - **Fifty-seventh annotation batch:** Typed ScriptChecker's text and
     boolean fields, display/path methods, form and formset method contracts,
     admin model, and injected request. The custom file field and generated
     inline-formset contracts remain dependent on Django's dynamic/stub
     boundaries, and the existing undefined `shell_script` name in
     `CopyForm.clean_filename` remains; the checker module has 35 targeted
     Pyright diagnostics, down from 112. The ScriptChecker execution and
     timeout tests (2), Django system checks, syntax validation, and
     CRLF-aware whitespace validation pass. Full strict Pyright now reports
     3,956 errors across 225 files (81 affected), down from 4,033.
   - **Fifty-eighth annotation batch:** Added compiler method and inline
     contracts to CBuilder, CXXBuilder, and ScalaBuilder; typed the shared
     Builder execution contract and CompilerOrLinker hooks; and typed the
     JUnitChecker and DiffChecker fields and methods. Replaced DiffChecker's
     removed `force_unicode` reference with Django's `force_str`, and writes
     the generated UTF-8 bytes in binary mode. JUnitChecker and DiffChecker
     pass targeted strict Pyright. The three compiler modules retain one
     django-stubs `ModelForm.__init__` unknown-instance diagnostic each.
     Django's system check passes. The focused C/C++ checker tests ran 18
     cases: 16 passed and two solution-upload response assertions failed
     because the expected final-solution phrase was absent. Full strict
     Pyright now reports 3,831 errors across 225 files, down from 3,956.
   - **Fifty-ninth annotation batch:** Typed CUnitChecker2's model fields,
     checker methods, and custom builder contracts; typed CLinker's execution
     hooks and its dynamically initialized main-object field; and completed
     shared compiler contracts for CompilerOrLinker, Compiler, Linker, and
     Builder. Propagated the verified contracts through HaskellBuilder and
     JavaBuilder. The changed compiler/checker modules have no ambiguous
     public-surface items. Three focused CUnit model-field tests and Django's
     system check pass. Full strict Pyright now reports 3,236 errors across
     225 files, down from 3,831.
   - **Sixtieth annotation batch:** Typed `kill_proc_tree`, `safe_docker`,
     its nested volume-mount helper, and `safe_docker_cleanup` in
     `utilities/safeexec.py`, including the Docker volume record and return
     contracts. Existing call sites for `kill_proc_tree` and `safe_docker`
     are compatible, and the module's compact public surface has no ambiguous
     items. The heterogeneous legacy return from `execute_arglist` remains
     explicitly `Any` rather than claiming an unverified positional-list
     contract. Full strict Pyright now reports 3,186 errors across 225 files,
     down from 3,236.
   - **Sixty-first annotation batch:** Typed the request and response
     contracts for the account views, the route-captured `user_id` and
     `group_id` strings, and the custom `MyRegistrationForm.domain` and
     `use_https` instance fields. The compact public surfaces for
     `accounts/views.py` and `accounts/forms.py` now report zero ambiguous
     items. Left `activate.activation_key` unresolved: Pyright treats
     `User.activate_user`, which is assigned to `staticmethod` after its
     definition, as an instance method, so annotating the input as `str`
     creates a binding error. The six account tests and Django system check
     pass. Full strict Pyright now reports 3,058 errors across 225 files,
     down from 3,186.
   - **Sixty-second annotation batch:** Completed the checker base-model
     execution contracts and result/helper method returns, typed the storage
     path callbacks, and added known Django field generics for checker
     timestamps, ordering, result relations/IDs, runtime, and artefact names.
     `check_solution`, connection helpers, `check_multiple`, and `run_checks`
     have caller-compatible signatures; the checker base-model module's
     targeted Pyright count fell from 110 to 87 and its compact public
     surface remains free of ambiguous items. The accounts tests (6) and
     Django system check pass. The checker test label fails in custom test
     database setup with `no such table: auth_user`, before tests execute.
     Full strict Pyright now reports 2,911 errors across 225 files, down
     from 3,058.
   - Follow-up checker contract cleanup: completed the verified Django
     `FileField` constructor and artefact field types, typed the checker
     generic relation and its result relation, and narrowed the post-delete
     signal callback to its registered sender/instance types. Left the
     framework's open-ended `**kwargs` on `CheckerFileField` as `Any`, the
     lazy-translation `verbose_name` unresolved because Django exposes only a
     private stub alias for its accepted string-like type, the generic foreign
     key unresolved because its descriptor is not assignable to its related
     model annotation, the signal's unused keyword values as `object`, and
     the literal `Meta` configuration unannotated rather than adding
     redundant annotations. All eight `CheckerFileField` call sites remain
     compatible; its targeted Pyright count fell from 87 to 45, and the full
     strict check now reports 2,869 errors across 225 files, down from 2,911.
     The Django system check and all six account tests pass.
   - **Sixty-third annotation batch:** Added 19 return annotations, 38
     parameter annotations, and a Django form-field annotation in
     `attestation/views.py`. The file now has no missing annotations in the
     Pylance queue and its compact public surface has zero ambiguous items.
     URL patterns establish string route IDs; the solution helper also
     accepts the optional model ID it receives internally. Its three call
     sites and both `tutor_attestation_stats` call sites are compatible.
     Kept `tutorial_overview.to_float.a` as `Attestation | None`, matching
     callers that pass a missing rating; its intentional `AttributeError`
     fallback now has a corresponding optional-member diagnostic. The
     `user_task_attestation_map` contract correctly requires the project's
     custom `User`, while one call site remains statically incompatible
     because Django types `HttpRequest.user` as the generic auth user despite
     the view's login requirement. The Django system check and all nine
     attestation tests pass, and `git diff --check` is clean. The focused
     strict check reports 363 errors in this legacy view module; the full
     strict check reports 2,683 errors, down from 2,869.
   - **Sixty-fourth annotation batch:** Added return and parameter
     annotations to all nine views in `solutions/views.py` (33 annotations
     total), and completed the known return, forwarding-parameter, and form
     field annotations in `attestation/forms.py`. The solution views now
     have no missing annotations in the Pylance queue; both files' compact
     public surfaces have zero ambiguous items. Kept explicit `Any` on the
     form constructor forwarding arguments and left Django `ModelForm`
     generics, generated formset classes, and literal `Meta` configuration
     unresolved rather than inventing framework types. The combined
     solutions, attestation, and taskstatistics test run passed all 32 tests
     with a clean Django system check. Full strict Pyright now reports 2,514
     errors across 225 files, down from 2,683; the typing effort remains
     incremental and CI enforcement remains deferred. The repository-wide
     `git diff --check` still flags trailing whitespace in existing
     `sessionprofile` diffs; it reports none in this batch's changed files.
   - **Sixty-fifth annotation batch:** Added 10 return and 18 parameter
     annotations across the solution template-tag modules
     `highlight.py` and `tasks_extras.py`. These cover Pygments lexer and
     highlighted HTML contracts, diff-rendering helpers, and the upload
     count filter's integer/solution-queryset inputs. Both modules' compact
     public surfaces have zero ambiguous items. Left constructor-inferred
     template registration/constants unannotated; the basename filter's
     nested path traversal retains an explicit `Any` because it supports
     both mapping lookup and attribute access across different model objects.
     The combined 32 solution, attestation, and task-statistics tests and
     Django system check pass. Focused strict Pyright diagnostics for these
     two modules fell from 135 to 32; the full configured check now reports
     2,411 errors, down from 2,514. The remaining highlighter diagnostics
     are chiefly the existing partially typed Pygments/Django boundaries and
     optional regex-match handling. Changed-file syntax checks and
     `git diff --check` pass.
   - **Sixty-sixth annotation batch:** Added three return annotations and
     five parameter annotations to the configuration chunk template tag.
     `Parser` and `Token` are imported privately from `django.template.base`,
     and `Context` privately from `django.template.context`, preserving the
     module's prior public surface. The three signatures follow Django's
     template-node contract; the chunk content is a `TextField[str, str]`,
     and the cache timeout accepts either the parser's string token or the
     default integer zero. Compact public surface remains at 25 exports with
     zero ambiguous items. Configuration tests (2) pass with a clean system
     check. Focused strict Pyright diagnostics fell from 29 to 7, all
     remaining parser-flow narrowing issues; the full configured count
     dropped from 2,411 to 2,389. Also reviewed the Isabelle lexer return
     contract, but left it unannotated because its exact Pygments `_TokenType`
     is private and a public `object` return violates the inherited method.
     Rejected a generic admin inline annotation because `InlineModelAdmin`
     is not a runtime attribute of `django.contrib.admin`; it was reverted
     after that incompatibility was observed. Changed-file syntax and
     whitespace checks pass.
   - **Sixty-seventh annotation batch:** Added a verified `str | bytes` input
     and `bool` return contract to `solutions.forms.contains_NUL_char`, plus
     the `None` return contract to the custom inline formset's `clean`
     override. The helper's accepted input matches `utilities.encoding.get_unicode`,
     and the override follows Django's formset hook. Left
     `SolutionFileForm.clean_file` unresolved because its unparameterized
     Django form exposes cleaned file data as `Any`; the public surface
     remains at 130 exports with zero ambiguous entries. A trial
     specialization of Django's generic form base raised a runtime
     `TypeError` (`ModelForm` is not subscriptable), so it was reverted.
     The focused Pyright run reports 12 existing framework-generic and
     formset-content diagnostics; all 11 solution tests and Django's system
     check pass after the annotation-only changes. The full configured
     strict check reports 2,386 errors, down from 2,389.
   - **Sixty-eighth annotation batch:** Added request/response and SSO
     attribute parsing signatures to `accounts/shib_views.py`; added string
     arguments and string return typing to the diff-rendering helper and
     `None` returns to solution tests; and added `None` returns to the
     checker test hooks plus concrete `Solution`/`Task` fixture field types.
     Also typed the concurrent-test wrapper's integer repetition count and
     its no-value worker returns. The two test modules' compact public
     surfaces now report zero ambiguous exports (204 and 192 exports,
     respectively); the Shibboleth view surface remains at 99 exports with
     zero ambiguous items. The concurrent decorator's generic callable
     parameter and return remain unresolved because an accurate preserved
     callable signature would require a helper type declaration.
     `accounts` and `solutions` tests passed together (17 total), then the
     solution suite passed again after the final test-helper annotations
     (11 tests); one focused checker test passed. Django system checks are
     clean. Focused Pyright still reports 14 errors in `shib_views.py`, 28
     in `solutions/tests.py`, and 174 in `checker/tests.py`, mostly existing
     dynamic framework/model boundaries. The full strict check now reports
     2,303 errors, down from 2,386. The Shibboleth `listMissingAnnotations`
     response appears stale (it still lists signatures that are explicitly
     annotated in the saved source); those lines were verified on disk and
     terminal Pyright was used for validation.
   - **Sixty-ninth annotation batch:** Added test return annotations and
     concrete fixture types in `accounts/tests.py`, `tasks/tests.py`, and
     `attestation/tests.py`; typed the account URL pattern list and the
     session-profile test's `User` fixture. The account, task, and
     attestation tests passed (24 tests combined; six account tests also
     passed independently), and the relevant task/attestation public
     surfaces have no ambiguous members. The session-profile test remains
     unavailable under the active test settings because that app is not
     registered there; its fixture type is supported by the model
     assignment, but no runtime result is claimed for that module.
   - **Seventieth annotation batch:** Added 29 `None` return annotations,
     five helper parameter/return annotations, and nine concrete fixture
     field types across the account admin, solution admin, and C/C++ checker
     integration tests. The helper paths are `str`, their Task primary key
     is `int`, and the upload helper returns `bool`; the solution-admin
     `task` fixture remains ambiguous as `dict[str, Any]` rather than being
     given an unsupported narrower type. Compact public surfaces now have
     zero ambiguity for the account-admin and C/C++ checker test modules;
     the solution-admin test retains that one `Any`-based ambiguity. The
     two admin integration modules passed (9 tests), and the C/C++ checker
     model tests passed (11 tests), all with clean Django system checks.
     Focused Pyright passes the two admin integration modules with zero
     errors; the C/C++ checker module still reports 66 errors around its
     existing Django model-field metadata and imports. The full configured
     strict check now reports 2,282 errors, down from 2,303. Repository-wide
     `git diff --check` continues to report trailing whitespace in the
     already-modified `sessionprofile` files; it reports no new issue from
     these integration-test annotations.
   - **Seventy-first annotation batch:** Added explicit `User`, `Task`, and
     `AdminSite` fixture field types to `hbrs_tests/test_admin_tasks_listview.py`.
     Its compact public surface now has zero ambiguous exports (down from
     three), and its missing-annotation queue and Pylance diagnostics are
     empty. The focused Pyright check for this file, `test_systemlocale.py`,
     and `test_wsgi.py` passes with zero errors. The combined runtime test
     command ran 12 tests: 11 passed, while the existing locale test
     `test_LANGUAGE_environmentvariable_is_not_None` failed because this
     environment does not define `LANGUAGE`; no environment or test behavior
     was changed to mask that condition.
   - A follow-up audit of `utilities/exceptionlogger.py`, `utilities/nub.py`,
     and `utilities/mimetypes.py` found no missing signatures in their
     annotation queues. The first two have no ambiguous public exports.
     `mimetypes.py` still exposes its module-loop targets `mimetype` and
     `extension` as `Any`; there is no later simple assignment where an
     inline annotation can be added without changing executable code, so
     these remain unresolved rather than introducing a separate declaration.
   - **Seventy-second annotation batch:** Added `bool` return contracts to
     `SolutionAdmin.tests_failed` and `SolutionAdmin.latest_of_only_failed`.
     Their queryset annotations use `Exists` expressions, including a
     `SELECT EXISTS` expression in the raw SQL for the latter. Pyright still
     reports the dynamically attached `Solution` attributes as unknown; the
     return contracts follow the verified database expressions. The admin
     module's compact public surface remains unambiguous.
   - **Seventy-third annotation batch:** Added the `File | None` return
     contract to `SolutionFileForm.clean_file` and imported Django's `File`.
     The method handles and returns the cleaned model `FileField` value,
     which may be an existing `FieldFile` or an uploaded file, both file
     objects. Solution tests pass (11 tests); existing Django form generic
     diagnostics remain. Pylance's annotation queue is stale for several
     signatures already explicitly annotated in this module, including the
     newly verified line; the saved source was checked directly.
   - **Seventy-fourth annotation batch:** Added `_Model | None` to the
     `obj` parameter of `CheckerInline.get_fieldsets`, matching Django's
     `BaseModelAdmin.get_fieldsets` parameter contract while retaining
     compatibility with any model used by the generic inline. The return
     remains unresolved: the model-specific `description()` call and the
     generic inline formset contract are not recoverable precisely from the
     current Django stubs without asserting an incompatible fieldset type.
     Focused Pyright still reports the pre-existing Django generic and
     fieldset-shape issues. The combined account and solution tests passed
     (17 tests), and the solution suite passed again independently (11
     tests). The full configured strict check now reports 2,280 errors, down
     from 2,282; scoped `git diff --check` passes for the edited source files.
   - **Seventy-fifth annotation batch:** Added the activation-key parameter
     types to `User.activate_user` and the `activate` view, string returns for
     `AnonymityChecker.title` and `.description`, complete argument/return
     types for the settings proxy's `__setattr__` and `show_toolbar`, and an
     `HttpRequest` type for `CheckerInline.get_fieldsets`. Pylance confirms
     zero ambiguous public exports in the four non-admin modules. The
     `CheckerInline.get_fieldsets` return remains unresolved because Django's
     current stubs do not express the model-dependent description fieldset
     shape soundly. Focused Pyright across the five touched modules reports
     147 errors, mainly at existing Django generic, dynamic settings, and
     decorator boundaries. The focused account and anonymity tests pass (7
     tests), and the full configured strict check reports 2,267 errors, down
     from 2,280.
   - **Seventy-sixth annotation batch:** Added explicit `int` and `str` types
     for `CheckerInline.extra` and `.template`, and the concrete
     `type[CheckerResult]` model type for `CheckerResultAdmin.model`. The
     admin class's compact public surface has zero ambiguous exports, and
     its missing-annotation queue is reduced to the unresolved fieldset
     return and list configuration attributes. Explicit `list[str]`
     annotations for those mutable lists were rejected because they conflict
     with Django's invariant, model-dependent admin attribute contracts.
     Focused Pyright reports 17 remaining diagnostics, mostly around those
     Django generic and dynamic admin boundaries. The focused checker test
     passes (1 test); the full strict check remains at 2,267 errors.
   - **Seventy-seventh annotation batch:** Added `str` to the configured
     `testSuiteUploadRoot` path and the `help` metadata on four custom Django
     management commands. Pylance infers the path as `str` and each help
     literal as a string; the public surfaces remain unambiguous. The
     management-command `args`/`options` parameters and test-runner `kwargs`
     remain `Any` because they implement Django's variadic override contracts.
     A utility test invocation found no tests for that label, then failed
     during the custom test-runner setup because the database lacked the
     `auth_user` table; it did not validate these metadata-only changes.
   - **Seventy-eighth annotation batch:** Typed the example checker's string
     metadata, `CheckerEnvironment -> CheckerResult` run contract, model
     `CharField[str, str]`, and inline model class. The return and environment
     types are grounded in the checker base implementation in
     `checker/basemodels.py`; the field follows Django's `CharField` generic
     contract. Its missing-annotation queue is now empty and its compact
     public surface has zero ambiguous exports. The existing unknown
     `checker.models` re-exports and malformed classmethod signature remain
     pre-existing strict diagnostics.
   - **Seventy-ninth annotation batch:** Added `list[str]` annotations to the
     `Meta.ordering` settings for `Task`, `RatingScaleItem`, and `User`, whose
     existing values are lists of field names and whose inferred type is
     `list[str]`. The task and attestation model missing-annotation queues
     are now clear; remaining task-model gaps concern custom file-field
     generics and a ZIP upload input whose complete accepted stream type is
     not established. Account/task/attestation regression tests pass (24
     tests), and Django's system check is clean. The full strict Pyright check
     now reports 2,262 errors, down from 2,267; `git diff --check` passes.
   - **Eightieth annotation batch:** Added `models.FileField` to
     `SolutionFile.file`, `DeletingFileField`-compatible regex metadata types,
     `re.Pattern[str]` for both compiled patterns, and concrete signal sender
     and instance types for `solution_file_delete`. Typed the variadic
     `save` wrappers and the representable `ConfirmationMessage` constructor
     parameters against Django's `EmailMessage` stub. `subject` and `body`
     remain unresolved: the stub requires private `_StrOrPromise`, which
     triggers a private-use diagnostic when imported, while the public
     `Promise` base is too broad to pass through to the superclass. The
     solutions model's compact public surface remains unambiguous; its
     remaining annotation queue consists of these two parameters and Django's
     dynamic `Any` variadics/connection. The solution test suite passes (11
     tests), with a clean Django system check. The full strict Pyright check
     reports 2,219 errors, down from 2,262; no new diagnostics were found for
     the edited signature or fields.
   - **Eighty-first annotation batch:** Added the custom `DeletingFileField`
     type to `MediaFile.media_file` and `HtmlInjector.html_file`. Pylance
     reports no diagnostics in `tasks.models`, and the full strict Pyright
     check remains at 2,219 errors with none reported on these declarations.
     Task tests could not be run: the selected `.venv` does not contain
     Django, and the generic unit-test runner does not discover Django's
     `TestCase` classes.
   - **Eighty-second annotation batch:** Declared the Django-generated
     `Task.solution_set` reverse manager as `models.Manager[_Solution]`.
     Its type matches the default reverse relation from `Solution.task` and
     covers the manager operations used by task methods and their callers.
     The full strict check fell from 2,219 to 2,049 errors, with no remaining
     unknown `solution_set` diagnostics.
   - **Eighty-third annotation batch:** Declared the default reverse managers
     `Solution.attestation_set`, `.checkerresult_set`, and `.solutionfile_set`
     using their related model types. The strict total fell from 2,049 to
     1,796 errors; no diagnostics remain for these relations. The compact
     public surface for `solutions.models` remains unambiguous.
   - **Eighty-fourth annotation batch:** Declared `Task.rating_set` and
     `RatingScale.ratingscaleitem_set` from their corresponding foreign keys.
     Full strict Pyright fell from 1,796 to 1,779 errors, with no diagnostics
     on the new manager declarations or uses.
   - **Eighty-fifth annotation batch:** Declared `Task` reverse managers for
     `CheckStyleChecker`, `CreateFileChecker`, `JUnitChecker`, and
     `ScriptChecker`, using type-only imports of each concrete related model.
     This removed 60 diagnostics across model and caller files; the focused
     three-model check reports 131 existing errors, and full strict Pyright
     fell from 1,779 to 1,719 errors. No diagnostics remain for the four
     manager relations. `git diff --check` passes for the touched files.
   - **Eighty-sixth annotation batch:** Added nullable integer types for
     `Task.model_solution_id` and `Task.final_grade_rating_scale_id`, matching
     their nullable foreign keys and the configured `AutoField` primary keys.
     Full strict Pyright fell from 1,719 to 1,714 errors; no new diagnostics
     were introduced.
   - **Eighty-seventh annotation batch:** Added integer types for the
     `Solution.task_id` and `.author_id`, `SolutionFile.solution_id`, and
     `RatingScaleItem.scale_id` foreign-key ID attributes. The source foreign
     keys are non-nullable and point to models with integer `AutoField` keys.
     This removed 17 diagnostics across callers; full strict Pyright now
     reports 1,697 errors, with no errors on the new declarations.
   - **Eighty-eighth annotation batch:** Added model type arguments to the
     `ModelForm` bases in solutions, accounts, and attestation forms, including
     the typed inline formset and user admin form. The targeted strict check
     reports no missing model type arguments on these declarations; its
     remaining 104 diagnostics concern existing imports, Django stubs, and
     dynamic form contracts. Full strict Pyright reports 1,677 errors, 20
     fewer than the prior 1,697-error result.
   - **Eighty-ninth annotation batch:** Added model type arguments to the four
     task admin inline bases and `TaskAdmin`. Full strict Pyright remains at
     1,677 errors with no missing generic diagnostics on these admin classes;
     `git diff --check` reports no whitespace errors (Git also reports
     existing line-ending conversion warnings).
   - **Ninetieth annotation batch:** Declared the required hidden
     `solution_file` field's cleaned value as an integer, and formatted the
     missing-object validation message with an f-string. This removes the
     invalid string-plus-integer operation and its associated unknown-type
     diagnostic without changing the successful validation path. Also removed
     the unused `formset_factory` import. Targeted strict Pyright for
     `attestation.forms` falls from six errors to three pre-existing Django
     stub/generic diagnostics; the full strict result falls from 1,677 to
     1,674 errors. Syntax and scoped whitespace checks pass.
   - **Ninety-first annotation batch:** Added `Apps` and
     `BaseDatabaseSchemaEditor` parameter types and `None` return types to
     seven historical `RunPython` callbacks in the accounts and configuration
     migrations. Focused Pyright no longer reports callback parameter or
     callable-argument unknowns; the only diagnostics in the migration batch
     are six pre-existing unused `models` imports. These callbacks leave
     `Apps.get_model` results dynamically typed, so model-operation
     diagnostics remain at that boundary.
   - **Ninety-second annotation batch:** Added the Django `HttpRequest | None`
     and optional string credential parameters plus `User | None` return
     types to `LDAPBackend.authenticate`; typed `get_user` as an integer
     primary key to `User | None`. This removed ten diagnostics in the
     targeted LDAP backend run (73 to 63); its remaining errors concern the
     unavailable python-ldap stubs and dynamic LDAP dictionaries/group
     adapters. Attempts to type the LDAP dictionary helper parameters
     surfaced incompatible `None`/unknown call-site arguments, so those
     annotations were reverted. The module's compact public surface still
     reports only its dynamic import-loop globals `a` and `lga` as ambiguous.
     Remaining missing annotations are the helper contracts for
     `fetch_ldapuser_dict`, `create_localuser_from_ldapuser`, and
     `_select_attribute`: the LDAP result is a heterogeneous, mutated mapping
     from an untyped dependency, and `_select_attribute` intentionally handles
     both byte and string values. Typing those more precisely would require a
     helper type or additional runtime changes, neither of which is justified
     for this inline batch.
     Full strict Pyright now reports 1,567 errors, down from 1,674; changed
     migration and authentication signatures have no new diagnostics.
   - **Ninety-third annotation batch:** Declared the `validate_mat_number`
     input as `int | None`, matching the nullable `IntegerField` that registers
     this validator. This resolves its unknown-parameter diagnostics without
     changing the already-incompatible validator return (`True | None` versus
     Django's declared `None` contract); the existing validator-argument
     diagnostic remains. Full strict Pyright falls from 1,567 to 1,564 errors.
     An attempted `CheckerFileField.verbose_name` annotation was reverted:
     Django stubs expose the accepted `_StrOrPromise` type, while the public
     `Promise` type is too broad to pass to the superclass and the precise
     alias is private.
   - **Ninety-fourth annotation batch:** Typed the concurrency-test decorator's
     accepted callable and produced wrapper, its variadic arguments, exception
     collection, and worker-thread list. The callable contract is based on the
     decorator invoking the wrapped function with arbitrary supplied arguments
     and discarding its return value. This removes the decorator's unknown and
     missing-annotation diagnostics without introducing helper declarations or
     changing runtime behavior. Full strict Pyright now reports 1,546 errors,
     down from 1,564. The focused `solutions/tests.py` check still reports six
     unrelated existing issues (unused imports, an untyped imported helper,
     and its existing `splitlines`/return-type diagnostics); no diagnostics
     remain on the decorator.
   - **Ninety-fifth annotation batch:** Typed
     `boxblot_to_graphic_list.fliers` as the dictionary shape supplied by
     `prepare_graphic_list` (`dict[str, list[int | str]]`), retaining the
     existing `None` default and runtime validation. Pyright's call-site
     compatibility check confirms the one caller fits the annotated
     signature.
   - **Ninety-sixth annotation attempt (reverted):** Tried to type
     `ConfirmationMessage.subject` and `.body` using the public Django
     `Promise` type. Pyright showed `Promise` is broader than the base
     constructor's private `_StrOrPromise` contract at the `super().__init__`
     call, so both parameter annotations were reverted rather than claiming
     an incompatible override. These parameters remain unresolved unless a
     safe public representation of Django's exact alias is available.
   - **Ninety-seventh annotation batch:** Specialized the generic file return
     type of `SolutionFileForm.clean_file` to `File[bytes] | None`. The local
     Django stub declares `File` as `IO[AnyStr]`; the solution form uses
     uploaded binary file content.
   - **Ninety-eighth annotation batch:** Specialized
     `WarningScriptCheckerFormSet` as
     `BaseInlineFormSet[ScriptChecker, Task, ModelForm[ScriptChecker]]` only
     under `TYPE_CHECKING`; these exact model, parent, and form parameters
     already appear in `ScriptCheckerInline.get_formset`'s return contract.
     Runtime continues to inherit the same unparameterized Django class.
     The focused `ScriptChecker.py` run no longer reports the missing generic
     arguments for this formset; its remaining diagnostics were present
     independently of this base annotation.
   - **Ninety-ninth annotation batch:** Annotated `User.__init__`'s variadic
     parameters with `Any`, exactly matching Django's `Model.__init__`
     signature in the installed django-stubs (`*args: Any, **kwargs: Any`).
     The method forwards both collections unchanged to `super()`, preserving
     Django's flexible model-construction API. Pylance confirms the existing
     call remains compatible. This is an explicit dynamic boundary rather
     than a fully precise public contract; the type-authoring inventory
     continues to classify those `Any` parameters as incomplete.
     The fresh full strict Pyright run reports **1,518 errors**, down from
     1,546 at the start of batches 95–99. The incompatible email annotations
     were reverted; focused checks show no diagnostics introduced by the
     retained signatures or generic arguments.
   - An attempted `Task.import_Tasks.zip_file: BinaryIO` annotation was
     reverted: Django's form stub exposes the caller value as
     `UploadedFile | list[object]`, which is not assignable to the ZIP reader's
     file-object contract. Accepting the union would claim the implementation
     handles lists, while narrowing to `BinaryIO` rejects the stub's caller
     type; this remains an honest unresolved boundary.
   - Other attempted contracts left unresolved: `TasksStatisticTest
     .get_table_description` delegates to Django database-backend
     introspection, whose public stub returns `Any`; `validate_mat_number`
     cannot satisfy Django's `_ValidatorCallable` contract honestly because
     it returns `True` for dummy values but Django declares validator returns
     as `None`. An experimental `int -> bool | None` annotation was reverted
     after Pyright confirmed it is incompatible with the model field's
     validator type.
   - **One-hundredth annotation batch:** Typed
     `MyRegistrationForm.__init__` and `save`'s variadic forwarding parameters
     as `Any`, reflecting their dynamic pass-through to Django form APIs;
     declared the constructor's `None` return and the save method's `User`
     return, consistent with its `Meta.model`. The assignment from the
     superclass save is also identified as `User`, though Django's
     unparameterized `AdminUserCreationForm` stub still leaves downstream
     member types partially unknown. The full strict Pyright count fell from
     1,518 to **1,509**. The focused form check remains at 41 errors, all in
     existing unused-import, Django-stub, or untyped-model-field areas; no
     runtime tests were run for these annotation-only changes.
   - **One-hundred-first annotation batch:** Marked the post-save receiver's
     variadic signal payload as `Any`; Django signals supply a dynamic keyword
     payload containing `created` and `instance`, and the receiver forwards
     the instance state directly. Its focused module check dropped from 33 to
     30 errors, and the full strict check now reports **1,506 errors**. A
     possible stream annotation for `User.import_user` was not retained:
     although Django's deserializer expects text, bytes, or an IO stream, the
     form-file stub at its only call site also includes `list[object]`, so
     annotating the true runtime input would currently introduce a caller
     incompatibility.
   - **One-hundred-second annotation batch:** Annotated the two
     `AttestationAdmin` hooks with the contracts verified from Django's
     admin stubs: `get_form` returns a model form for `Attestation`, and
     `formfield_for_foreignkey` accepts any foreign key and can return a
     model-choice field for any related model. The latter's `request.obj`
     attribute is added dynamically by the existing `get_form` override, so
     that parameter remains an explicit dynamic boundary. Focused diagnostics
     show the pre-existing request extension and incompatible `get_form`
     parameter-count issues remain, with no new issues from the annotations.
     The full strict Pyright count is **1,492 errors**, down from 1,506.
   - **One-hundred-third annotation batch:** Specialized the static base of
     `AlwaysChangedModelForm` as `ModelForm[Any]`. This shared admin form is
     reused for checker subclasses with different concrete model classes, so
     `Any` reflects that dynamic model association; the runtime base remains
     unchanged. The corresponding missing-generic diagnostic was removed, and
     resolving the form's type also reduced downstream unknown diagnostics.
     The full strict Pyright count is **1,480 errors**, down from 1,492. The
     `CheckerInline` base remains unresolved: it is shared across many
     checker-model subclasses, while the Django inline stub's `get_fieldsets`
     signature conflicts with the runtime parent-object argument needed by
     `get_formset`; a guessed generic base introduces a call-site error.
   - **One-hundred-fourth annotation batch:** Declared
     `create_localuser_from_ldapuser`'s return as `User`, based on both return
     paths obtaining the value from `User.objects.get` or
     `User.objects.create_user`. Focused checking confirms the existing
     unknown-manager diagnostic remains and no new diagnostics were
     introduced; at that point the function's LDAP payload and username
     parameters remained unresolved because their call-site types are dynamic
     or optional. The
     full strict Pyright count remains **1,480 errors**.
   - **One-hundred-fifth annotation batch:** Typed the LDAP payload parameter
     of `create_localuser_from_ldapuser` as `dict[str, Any]`. LDAP attribute
     keys and values are supplied by the external LDAP server and do not have
     a stable project-defined schema; `Any` is retained only at that dynamic
     boundary. The focused LDAP module count decreased from 63 to 60, with no
     new diagnostics, and the full strict Pyright count fell to **1,477**.
     The compact public-surface check reports no newly ambiguous members;
     the pre-existing adapter-loop names remain ambiguous.
   - **One-hundred-sixth annotation batch:** Added `str | Promise` and
     `str | Promise | None` annotations to the subject and body parameters of
     `ConfirmationMessage.__init__`. Django's `EmailMessage` stub confirms
     these accepted types, and the subject call site passes Django's lazy
     translation proxy. The focused check reports no diagnostics on the
     annotated parameters; an unrelated existing unknown email type remains
     at the constructor call. The full strict Pyright count remains
     **1,477 errors**. A proposed annotation for `Task.import_Tasks.zip_file`
     was not retained: Django's form-files stub includes `list[object]` at the
     sole call site, which is incompatible with the ZIP reader's verified
     file/path contract.
   - **One-hundred-seventh annotation attempt:** A candidate annotation of
     `create_localuser_from_ldapuser.username` as `str | None` matched the
     caller's optional username, but exposed a genuine mismatch at
     `User.objects.create_user`, whose username parameter requires `str`.
     The annotation was not retained because the function's nullable input
     and existing behavior are incompatible without a logic change. A
     candidate annotation for
     `CheckerFileField.verbose_name` was reverted: Django's stub expects its
     private `_StrPromise` protocol, and the public `Promise` base type does
     not satisfy that constructor contract. The remaining LDAP fetch signature
     was not edited because its source line is masked by the editor tooling;
     its external LDAP result schema also remains dynamic.
   - **One-hundred-eighth annotation batch:** Typed the dynamically assembled
     LDAP group adapter list as `list[Callable[[User], object]]`. Every stored
     adapter is invoked with a project `User`, and its return value is ignored,
     so `object` is the opaque result contract; plugin implementation details
     remain at the dynamic import boundary. The focused LDAP module check
     decreased from 58 to 56 errors with no new diagnostics. Its public
     surface still has the same two ambiguous loop variables (`a` and `lga`),
     which arise from the untyped optional settings import and dynamic module
     import and cannot be annotated as loop targets without changing runtime
     behavior.
   - **One-hundred-ninth annotation batch:** Added the verified
     `bool | None` return type to `validate_mat_number`: the dummy-number
     branch returns `True`, the configured-regex branch returns the validator's
     `None`, and the no-regex path falls through with `None`. This truthfully
     exposes an existing compatibility mismatch: Django's validator stub
     requires a `None` return, so the `mat_number` field now reports a
     call-site type error. The runtime currently ignores validator return
     values; the return was not changed to avoid altering behavior.
   - **One-hundred-tenth annotation attempt:** An annotation of
     `_select_attribute` as accepting `Iterable[bytes | str]` and returning
     `bytes | str` matches its byte-valued LDAP and text-valued normalized
     dictionary call paths. However, the wider return type newly produced
     assignment diagnostics where callers require user-name strings, and it
     exposes the helper's input correlation that inline annotations cannot
     express without adding a TypeVar or overload. Both annotations and the
     added import were reverted. The earlier
     `create_localuser_from_ldapuser.username` annotation was also removed:
     although its caller's value is optional, the implementation passes it to
     `create_user`, which requires a non-null `str`; the existing signature
     therefore remains unresolved rather than making a false nullable claim.
   - **One-hundred-eleventh annotation batch:** Annotated
     `CreateFileCheckerInline.model` as `type[CreateFileChecker]`. It is an
     existing Django admin model binding, and Pyright previously inferred
     `type[Unknown]`; the focused strict check passes for the entire module
     with zero errors, warnings, or information diagnostics. Its public
     surface remains fully known. The full strict check reports **1,475
     errors**, three more than the preceding 1,472-error run; this reflects
     restored unknown-type propagation after removing the unsound nullable
     LDAP username annotation, not new diagnostics in the checker module.
   - **One-hundred-twelfth annotation batch:** Added precise `type[Model]`
     annotations to the existing Django admin inline model bindings in
     `AnonymityChecker`, `CheckStyleChecker`, `DejaGnu` (both inline models),
     `DiffChecker`, `HaskellTestFrameWorkChecker`, `InterfaceChecker`,
     `IsabelleChecker`, `JavaChecker`, `JUnitChecker`, `KeepFileChecker`,
     `LineCounter`, `LineWidthChecker`, `RChecker`, and `TextChecker`.
     Also annotated the existing CheckStyle XML configuration model field as
     `CheckerFileField`. These assignments preserve their runtime values and
     admin/model behavior. The focused strict check across all 14 changed
     checker modules passes with zero diagnostics; their compact public
     surfaces report no ambiguous exports. The full strict check remains at
     **1,475 errors, 0 warnings** with no diagnostics in the touched checker
     modules.
   - **One-hundred-thirteenth annotation batch:** Typed the existing admin
     inline `model` bindings in `CLinker`, `FortranBuilder`, `JavaBuilder`,
     and `HaskellBuilder` as `type[TheirCheckerClass]`. Each is a direct
     binding to the concrete checker class, matching Django's inline model
     contract and the established checker-admin annotation pattern. All four
     modules retain fully known compact public surfaces; focused Pyright
     reports no new diagnostics (its existing CLinker/JavaBuilder issues are
     unrelated and unchanged).
     A follow-up experiment to parameterize the shared `CheckerInline` base
     with `Checker` and `Task` was reverted: it introduced incompatible
     `obj` argument errors in the base helper's calls to `get_formset` and
     `get_readonly_fields`, without resolving its fieldset return contract.
     The full strict check remains at **1,475 errors, 0 warnings**.
   - **One-hundred-fourteenth annotation batch:** Added `type[Model]`
     annotations to the remaining direct Django admin model bindings in
     `tasks.admin`, `solutions.admin`, `accounts.admin`, `configuration.admin`,
     and `attestation.admin` (17 bindings). The right-hand sides are the
     concrete model classes used by the corresponding typed admin base classes.
     The compact public surfaces remain unchanged and fully known, except for
     the four pre-existing, trivially inferred integer exports in
     `attestation.admin`. Focused Pyright reports only existing issues in
     admin configuration and custom methods, with no model-binding errors;
     full strict Pyright remains **1,475 errors, 0 warnings**.
   - **One-hundred-fifteenth annotation batch:** Annotated the existing
     `ImportForm.file` and `ImportForm.is_template` fields in `tasks.views` as
     `forms.FileField` and `forms.BooleanField`, respectively. Pylance confirms
     these are the concrete types constructed by the existing assignments;
     the declarations remain Django form fields collected by the same
     metaclass. The focused diagnostics and compact public surface show no
     regressions, and the annotation queue for the module is empty. Full
     strict Pyright remains at **1,475 errors, 0 warnings**.
   - **One-hundred-sixteenth annotation batch:** Narrowed the values mapping
     returned by `taskstatistics.views.getQuerySet` from `dict[str, Any]` to
     `dict[str, object]`. Its only in-project consumer stores database values
     opaquely, so `object` accurately represents the heterogeneous values
     without permitting unchecked operations. Pylance diagnostics are
     identical before and after the change; the compact public surface remains
     fully known. The generated pandas row parameter in
     `boxblot_to_graphic_list` remains unresolved because its dynamic named-tuple
     fields need a helper declaration, which inline annotation work disallows.
     The full strict check remains at **1,475 errors, 0 warnings**.
   - **One-hundred-seventeenth annotation batch:** Annotated the five
     `DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_*` defaults as `str | None`. They
     default to `None`; when present, `safeexec.safe_docker` treats each value
     as a template string, confirming the optional path-string contract.
     `settings.defaults` diagnostics are unchanged, its compact public surface
     remains fully known, and its missing-annotation queue is reduced from six
     entries to the trivially inferred `no_defaults` list. Full strict Pyright
     remains at **1,475 errors, 0 warnings**.
     Two explored candidates remain unresolved: `CheckerInline.get_fieldsets`
     has an inferred return incompatible with Django's `_FieldsetSpec`
     override contract, and `IsarLexer.get_tokens_unprocessed` requires
     Pygments' private `_TokenType` to express its override return (a public
     tuple widening fails the override check). Neither was changed.
   - **One-hundred-eighteenth annotation batch:** Added return contracts to
     `accounts.forms.MyRegistrationForm.clean_email` (`str`) and
     `clean_mat_number` (`int`), matching the declared `EmailField` and the
     `User.mat_number` integer model field. Added the `AdminUserChangeForm.clean`
     return as `dict[str, Any] | None`, matching Django's inferred cleaned-data
     contract. The focused module check remains at **41 pre-existing errors**;
     the compact public surface remains fully known, and full strict Pyright
     remains at **1,475 errors, 0 warnings**. `clean()` retains dynamic `Any`
     values, and its `**kwargs`/`*args` wrappers remain unmodified to preserve
     Django's call contracts.
   - **One-hundred-nineteenth annotation candidate (not retained):** A follow-up
     compatibility check showed that Django's `FileField.__init__` accepts
     `str | _StrPromise | None` for `verbose_name`; annotating the override as
     `str | None` would narrow the supported lazy-translation input. The
     `_StrPromise` alias is private to Django's stubs and is not available at
     runtime, so using it also triggers `reportPrivateUsage`. The annotation
     was reverted rather than publishing an incomplete constructor contract.
     Full strict Pyright therefore remains at **1,475 errors, 0 warnings**.
   - **Follow-up annotation sweep:** Left the remaining candidates unresolved
     where the type cannot be expressed honestly inline: the Django decorator
     login URL uses the same private `_StrPromise` contract, the user/task
     import methods receive a form file value typed as
     `UploadedFile | list[object]` although their implementations consume a
     single file, and the LDAP attribute selector returns whichever of `str`
     or `bytes` it receives (a precise correlated return needs a helper type).
     No new annotation was retained from this sweep.
   - **Django-stubs upgrade and first compatibility fixes:** Pinned
     `django-stubs==6.0.9` in `requirements-dev.txt`, keeping runtime Django
     at 5.2.18 and the configured Python target at 3.10. Repeated the old- and
     new-stub measurements using the pinned Pyright 1.1.414, the same source,
     and all 225 configured files:

     | State | Errors | Warnings |
     | --- | ---: | ---: |
     | django-stubs 5.2.9, before upgrade | 1,475 | 0 |
     | django-stubs 6.0.9, before source fixes | 1,396 | 0 |
     | django-stubs 6.0.9, after first fixes | 1,364 | 0 |

     The dependency upgrade alone removes 155 diagnostics and introduces 76.
     This batch fixes 20 of those 76, leaving 56 upgrade-introduced
     diagnostics. It also removes 14 older diagnostics and re-exposes two
     pre-existing lazy-string mail-argument diagnostics that the new
     positional-argument error had masked. No diagnostic messages absent
     from both measured baselines were introduced. Accounting preserves
     duplicate diagnostics and ignores source-line shifts after edits.
     The final net improvement is 111 errors against the pre-upgrade state.
     The `resolve_url` import diagnostic disappears through the dependency
     upgrade, without a suppression or changes to installed Django source.

     - Specialize both user-creation forms with `User` only under
       `TYPE_CHECKING`, following the existing form-base pattern and retaining
       the runtime bases and constructor/save forwarding contracts.
     - Correct six test middleware callbacks to return an `HttpResponse`,
       rather than returning the input request.
     - Forward optional mail constructor arguments by keyword, preserving
       the existing public positional interface of `ConfirmationMessage`.
       A new regression test checks all forwarded mail options.
     - Specialize the attestation upload as `UploadedFile[bytes]` using a
       quoted annotation, and consume the validated form upload rather than
       the raw multi-value file dictionary. Regression tests exposed an
       existing XML-import bug: passing `read()` bytes made Django treat them
       as a stream and fail on a missing `read` method. Pass the upload stream
       directly to the XML deserializer; tests cover successful and malformed
       uploads.
     - Runtime startup validation exposed three eager-evaluated annotations
       from earlier batches: `ModelForm` and `ModelChoiceField` returns in
       attestation admin, and `File[bytes]` in solution forms. Quote those
       annotations because the Django 5.2 classes are not runtime-subscriptable.

     Remaining upgrade diagnostics include migration field generics,
     nullable file names, inherited mutable/`Meta` contracts, and Django
     6-oriented mail API differences. In particular, do not add Django 6's
     `EmailMessage.message(policy=...)` argument to a Django 5.2 implementation
     solely to satisfy the newer stubs.

     Validation on Python 3.12.3 / Django 5.2.18: the six focused upload/mail
     tests pass. The full suite runs 114 tests: 111 pass, one is skipped, and
     two C checker integration tests fail because `fakechroot` is unavailable.
     Use explicit module labels for the first seven apps to avoid unittest
     discovering duplicate `src.checker` models:

     ```bash
     cd src
     ../.venv/bin/python -m django test accounts.tests attestation.tests checker.tests configuration.tests solutions.tests tasks.tests taskstatistics.tests hbrs_tests --settings=settings.test --noinput
     ```

     Python 3.10 compatibility remains the static target, not a claim of a
     fresh runtime test on Python 3.10. An older global Pyright 1.1.411 reports
     slightly different totals; use the installed, pinned checker from the
     project environment for reproducible counts.

4. **Make the check part of normal development**
   - Make the configured strict Pyright command runnable locally from the
     beginning, so developers can check progress against the baseline.
   - After strict Pyright passes for the intended full scope, add that same
     command as a separate CI step. Keep it distinct from the existing Django
     test step for clear failures.

5. **Validate**
   - Run the configured strict Pyright check and inspect its complete output.
   - Run the existing Django test suite to check runtime behavior.
   - Run `git diff --check` and confirm the configured Python target remains
     consistent with the project's supported versions.

## Completion criteria

- A developer can run the strict Pyright check using the documented command.
- The strict check covers all maintained first-party Python code, including
  tests and migrations, unless a specific technical exclusion is documented.
- CI runs the same configured command once it passes for that intended scope.
- Strict rules have not been globally relaxed to hide errors; any local
  suppressions have narrow, documented reasons.
- The existing Django tests pass, or any unrelated/pre-existing failures are
  clearly identified.
- Pyright and any Django typing support are development-only dependencies.

## Scope and decisions to confirm during implementation

- The initial configuration is runnable, but the strict baseline is not yet
  passing. CI enforcement remains deferred until all maintained first-party
  Python code passes.
- An initial Django test run discovered 111 tests; 107 passed, one was skipped,
  and three failed. Two checker integration tests reported that `fakechroot`
  is unavailable in this environment; the KeepFile checker test could not find
  its expected `GgT.java` file. These runtime failures are separate from the
  type-check baseline and need reproduction in the project's fully provisioned
  CI environment.
- Use the baseline to prioritize the incremental work. If a temporary staged
  scope is necessary, record its boundaries and exit criteria; it must not
  become the permanent target or silently omit tests or migrations.
- Keep Django stubs only if Pyright can use them effectively in this project.
- Keep `pyproject.toml` as the preferred home for checker configuration and use
  a separate development requirements file for typing tools unless project
  packaging conventions change.
