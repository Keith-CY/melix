# Code eval sorted payload compact offsets

## Scope

This Python-only performance slice is limited to the sorted code-evaluation
payload fast path in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The existing sorted payload extractor already avoids full `json.loads(...)` for
successful probe-style payloads. This follow-up slice keeps the same accepted
field order and values, then searches the compact sorted suffix from the end of
the payload back toward the already-validated `failure_detail` prefix. That keeps
large `metadata` objects and any metadata-owned reserved key names off the hot
path before falling back to the existing whitespace-tolerant scanner for
non-compact payloads.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries, and watches:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_payload_json_probe.py`

## Validation plan

Run locally on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_extracts_sorted_payload_without_json_parse services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_uses_compact_field_offsets services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_returns_none_for_missing_or_malformed_fields services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_extracts_sorted_payload_without_json_parse services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_uses_compact_field_offsets services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_returns_none_for_missing_or_malformed_fields services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/tests/test_code_eval_runner.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/code_eval_payload_json_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id code-eval-payload-json-bytes --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/code_eval_sorted_payload_compact_offsets_probe.json
```

GitHub Actions PR-scoped performance remains the final registered probe
validation source before merge.

## 2026-07-18 Follow-up: whitespace fallback known-index reuse

This follow-up Python-only slice stays within the same sorted code-evaluation
payload fast path and registered `code-eval-payload-json-bytes` probe. Compact
field lookup already knows the matched key index before detecting whitespace
around the colon; the fallback now resumes value-start parsing from that known
cursor instead of invoking the generic token scanner and repeating the same
`bytes.find(...)` lookup. Behavior is unchanged for compact payloads,
whitespace-tolerant payloads, malformed payloads, and reserved metadata-key
fallbacks.

Expected metrics are lower `elapsed_ms_mean` in
`scripts/code_eval_payload_json_probe.py` for the default JSON payload workload;
`peak_bytes_mean` should remain stable because the change only removes redundant
search work.

## 2026-07-24 Follow-up: leading empty failure-detail prefix

This follow-up Python-only slice keeps the sorted code-evaluation payload fast
path and registered `code-eval-payload-json-bytes` probe. The default sorted
payload emitted by the probe begins with the compact
`{"failure_detail":""` prefix. The extractor now recognizes that prefix before
calling the generic compact key scanner, reusing the known value offset while
leaving whitespace-tolerant, non-prefix, malformed, and full-JSON fallback paths
unchanged.

Expected metrics are lower or neutral `elapsed_ms_mean` for
`scripts/code_eval_payload_json_probe.py`; `peak_bytes_mean` should remain stable
because the slice only removes the first successful key scan on the compact
sorted payload path.

## 2026-07-26 Follow-up: bound key-token constants

This follow-up Python-only slice keeps the sorted code-evaluation payload fast
path and registered `code-eval-payload-json-bytes` probe. The extractor now binds
the known JSON key tokens at module import time and reuses those constants in the
runner-friendly and sorted payload hot paths, avoiding repeated global dict
lookups while keeping full-JSON fallback and generic field lookup behavior
unchanged.

Expected metrics are lower or neutral `elapsed_ms_mean` for
`scripts/code_eval_payload_json_probe.py`; `peak_bytes_mean` should remain stable
because the slice only reuses immutable key-token constants.

## 2026-07-26 Follow-up: cached integer sign byte

This follow-up Python-only slice stays within the same code-evaluation payload
JSON byte-loading fast path and registered `code-eval-payload-json-bytes` probe.
The integer parser now reuses a module-level `_ORD_MINUS` byte constant instead
of calling `ord("-")` on each parsed integer field, preserving positive and
negative integer handling while removing a repeated builtin call from the hot
payload extraction loop.

Expected metrics are lower or neutral `elapsed_ms_mean` for
`scripts/code_eval_payload_json_probe.py`; `peak_bytes_mean` should remain stable
because the slice only replaces a repeated constant computation with an immutable
module constant.
