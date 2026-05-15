# Code evaluation payload cursor scan

## Scope

This Python-only performance slice keeps code-evaluation payload loading behavior
unchanged while reducing repeated byte scans in the fast JSON payload extractor.

The affected implementation path is:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`

The affected tests and probe path are:

- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_payload_json_probe.py`

## Registered Probe

The path is covered by registered PR-scoped probe
`code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. The probe
already provides focused `test_command`, `coverage_command`, and
`probe_command` entries for this file, the focused unit tests, and the probe
script.

## Optimization

The current byte extractor searches the full payload from the beginning for
each required field. This is correct, but synthetic and runner-produced payloads
have stable top-level field layouts. This slice adds cursor-aware field lookup
orders for the two known layouts:

- runner-produced payloads beginning with `compile_status`
- sorted-key payloads used by the registered probe

Each field lookup starts at the previous field position and falls back to a
full-payload lookup when a payload uses a different key order. The fallback keeps
semantics equivalent for arbitrary valid payload orderings while reducing repeat
scans on the measured path.

## Verification Plan

Run the registered probe's focused local commands on Linux:

1. Focused pytest for payload loading and registered probe selection.
2. Changed-scope coverage via the registered `coverage_command`.
3. `scripts/code_eval_payload_json_probe.py` on `origin/main` and on this branch.

The registered PR-scoped performance CI report remains the merge gate.
