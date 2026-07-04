# Code evaluation JSON field value-start fast path

## Scope

This Python-only performance slice is limited to the code-evaluation payload
loader in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The affected path is already covered by the registered PR-scoped performance
probe `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the loader, tests, and probe script.

## Optimization

The code-evaluation subprocess writes JSON payloads where known fields usually
place the colon immediately after the key token. `_json_field_value_start_for_token(...)`
now takes that adjacent-colon path first, then skips any post-colon whitespace,
before falling back to the fully general whitespace-before-colon path.

This preserves fallback behavior for spaced JSON such as `"key" : value`,
malformed payloads, unknown keys, escaped strings, and full `json.loads` parsing
when the fast path cannot safely extract all required fields.

## Verification plan

1. Run the registered focused tests for `code-eval-payload-json-bytes` locally on
   Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run `scripts/code_eval_payload_json_probe.py` before and after the change and
   compare `elapsed_ms_mean` / `peak_bytes_mean`.
4. Use the PR-scoped performance GitHub Actions report as the merge gate.

## Validation boundary

This slice is Python-only and locally verifiable on Linux. It does not change
Swift runtime behavior or generated protobuf artifacts.