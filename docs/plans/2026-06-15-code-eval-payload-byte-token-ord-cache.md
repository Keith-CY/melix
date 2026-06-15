# Code Eval Payload Byte Token Ord Cache

## Scope

Optimize one Python hot path in `worker.engine.code_eval_runner`: the compact
JSON payload fast path used by `_load_payload_file()` for code evaluation result
payloads.

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. That probe
provides focused `test_command`, `coverage_command`, and `probe_command` entries
for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `scripts/code_eval_payload_json_probe.py`

## Change

Cache the single-byte JSON structural ordinals used by the payload fast path at
module import time and reuse those constants in object-bound checks, colon checks,
and string-opening quote checks. This avoids repeated `ord()` calls in helpers
that run for every payload parsed by the fast path while preserving the existing
fallback behavior for malformed, escaped, or non-object JSON payloads.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and the
registered local probe on Linux. Compare the registered probe against an
`origin/main` baseline worktree using repeated samples before accepting the
slice.
