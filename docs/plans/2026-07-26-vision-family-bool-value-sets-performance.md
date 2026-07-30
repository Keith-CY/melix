# Vision family bool value set performance slice

## Scope

Optimize the Python vision family configuration resolver by reusing module-level
boolean literal membership sets in `_bool_value` instead of allocating the true
and false literal sets on each resolve call.

## Registered probe

Affected path is covered by the existing PR-scoped probe entry
`vision-family-prompt-token-count-scan` in `infra/perf/pr_scoped_probes.json`.
That registered probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/vision_family_adapters.py`
- `services/mlx-worker-python/worker/runtime/token_counting.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `scripts/vision_family_prompt_token_count_probe.py`

The probe reports `config_resolve_elapsed_ms_mean` and
`metadata_iteration_calls_mean`, which directly cover this resolver slice.

## Behavior

No behavior changes are intended. Accepted and rejected boolean text values stay:

- true: `1`, `true`, `yes`, `on`
- false: `0`, `false`, `no`, `off`

Invalid, blank, and missing values still fall back to the descriptor default.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux before opening the PR. The CI PR-scoped
performance workflow remains the merge gate.
