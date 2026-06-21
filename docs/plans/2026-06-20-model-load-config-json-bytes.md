# Model Load Config JSON Bytes Performance Slice

## Scope

This Python-only performance slice is limited to model-load trust policy custom-loader detection in `services/mlx-worker-python/worker/model_load_trust.py`.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values and selects this probe when `worker/model_load_trust.py` changes.

## Optimization

`_read_model_config()` previously loaded `config.json` with `Path.read_text(encoding="utf-8")` before calling `json.loads()`. Python's JSON decoder accepts UTF-8 bytes directly, so this slice reads `config.json` with `Path.read_bytes()` and lets `json.loads()` decode during parse. The expected benefit is lower intermediate string allocation and slightly lower policy-resolution latency for repeated model-load trust checks on custom-loader model directories.

## Follow-up Slice: Plain Path Character Guards

The 2026-06-21 follow-up keeps the same registered probe and narrows the optimization to the hot plain-path config lookup. `_read_model_config()` now checks the first and last character of the already-normalized non-empty `model_path` instead of calling `str.startswith("~")` and `str.endswith(os.sep)`. This preserves tilde expansion and plain-path behavior while shaving method-call overhead from repeated trust-policy resolution.

## Verification Plan

1. Add regression coverage proving the trust policy reads `config.json` through `Path.read_bytes()` without using `Path.read_text()`.
2. Register `model-load-config-json-bytes` with focused test, coverage, and command-json probe commands.
3. Run the focused test command locally on Linux.
4. Run changed-scope coverage for the changed Python path.
5. Run the registered probe locally against `origin/main` and this branch before pushing.
6. Use GitHub Actions PR-scoped performance as the merge gate.

## Linux Validation Boundary

This slice only changes Python worker code and is locally verifiable on Linux. No Swift runtime effect is claimed.
