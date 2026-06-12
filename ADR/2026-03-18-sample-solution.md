# Context and Problem Statement

Some checkers (like the llm-tutor checker) need access to the sample solution
of an assignment, as well as the pdf for the exercise sheet. Other checkers
should not have access to the sample solution to avoid leakage. Hence, the
question is how to give make access to the sample solution configurable.

Note: when writing "checker" we always mean the ScriptChecker.

# Options

We discussed several options. At the end, we had the following two on the table:

## Variant 1 (simple and pragmatic)

- In addition to the configuration variable `DOCKER_CONTAINER_EXTERNAL_DIR`, the
  local.py config file now also contains variables `DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_1`, ...,
  `DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_5`.
- These configuration variables have the format `"HOST_DIR:CONTAINER_DIR"`.
- For the ScriptChecker, there is a checkbox in the task configuration
  labelled ‘provide extra dirs for checker’. By default, this is unchecked. If the checkbox is
  ticked and any of `DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_i` is set, the `HOST_DIR`
  from the variable is mounted to the `CONTAINER_DIR`.

Note: we usually run the praktomat via docker. In the praktomat-docker repo, we configure
various options from local.py via environment variables. The plan is to map the environment
variable `PRAKTOMAT_CHECKER_EXTERNAL_EXTRA_DIR_1` to `DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_1`
and so on.

## Variant 2 (more flexible but more work)

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

- Variant 1 is sufficient for the current problem of "having a sample solution available
  for the LLM Tutor".
- Variant 2 is more complex to implement, and the checker scripts become more complicated
  and prone to errors.
