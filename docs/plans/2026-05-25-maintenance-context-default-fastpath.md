# Maintenance context default fast path

## Scope

This Python-only performance slice targets default maintenance benchmark context
length and prompt-token helpers in `worker.engine.maintenance_core`. The
benchmark prompt-shaping probe repeatedly asks for default context lengths with
an empty parameter mapping and re-counts the same prompt text; that path only
needs a single token count tuple and can reuse token counts for repeated prompt
strings.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`maintenance-prompt-shape-vector-repeat` in `infra/perf/pr_scoped_probes.json`.
That entry includes focused `test_command`, `coverage_command`, and
`probe_command` fields for `maintenance_core.py` and the maintenance tests.

## Implementation

Add a narrow empty-parameter fast path in
`MaintenanceCore._benchmark_context_lengths()` that returns the default prompt
count tuple directly, and cache `_benchmark_prompt_token_count()` for repeated
prompt strings. Keep the existing parsing behavior for explicit
`context_lengths`, `context_length`, invalid values, and non-empty parameter
mappings.

## Verification

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux before opening the PR. The PR-scoped
performance workflow remains the merge gate after the PR is opened.
