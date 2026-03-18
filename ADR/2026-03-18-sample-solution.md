# Context and Problem Statement

Some checkers (like the llm-tutor checker) need access to the sample solution
of an assignment. Other checkers should not have access to the sample
solution to avoid leakage. Hence, the question is how to give make access
to the sample solution configurable.

Note: when writing "checker" we always mean the ScriptChecker.

# Options

We discussed several options. At the end, we had the following two on the table:

## Variante 1 (pragmatisch und sehr einfach):

- In addition to the configuration variable `PRAKTOMAT_CHECKER_EXTERNAL_DIR`, the
  env file now also contains the variable `PRAKTOMAT_CHECKER_SOLUTION_DIR`.
- For the ScriptChecker, there is a checkbox in the task configuration
  labelled ‘provide solution for checker’. By default, this is unchecked. If the checkbox is
  ticked and `PRAKTOMAT_CHECKER_SOLUTION_DIR` is set,
  `PRAKTOMAT_CHECKER_SOLUTION_DIR` is mounted to `/solution`.

## Variante 2 (flexibel aber aufwändiger):

Currently, Praktomat determines whether CheckerScript runs under Docker, which volumes
are mounted, and so on. With variant 2, these decisions would be made within the script itself.
The script would then have complete flexibility: it could run under Docker, or not, and
it could mount any volumes, and so on.

Here is a sample invocation:

```
run-in-docker --volume DIR_1:/external:ro --volume DIR_2:/solution:ro MY_COMMAND ARGS
```

# Decision

We opted for variant 1.

# Rationale

- Option 1 is sufficient for the current problem of "having a sample solution available
  for the LLM Tutor".
- Option 2 is more complex to implement, and the checker's scripts become more complicated
  and prone to errors.
