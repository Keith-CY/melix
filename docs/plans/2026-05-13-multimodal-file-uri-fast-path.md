# Multimodal File URI Parse Fast Path

## Goal

Avoid calling `urllib.parse.urlparse` for local `file:///...` image references in
`prepare_vision_request(...)`. The local `Path.as_uri()` form is common in
Vision runtime tests and operator file inputs, and it can be decoded with the
same path semantics directly.

## Scope

- `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`

This is a Python-only worker runtime slice and is locally verifiable on Linux.
Remote `http`/`https` image URI handling still uses `urlparse`; non-canonical
`file://host/...` references intentionally fall through to the existing parser.

## Registered Probe

Affected path coverage is already registered as
`multimodal-preprocessing-image-uri-single-parse` in
`infra/perf/pr_scoped_probes.json` with focused `test_command`,
`coverage_command`, and `probe_command` entries.

The probe reports:

- `urlparse_calls_mean` — lower is better; this slice should reduce local file
  URI parse calls to zero while preserving remote URI parsing.
- `elapsed_ms_mean` — lower is better; expected to improve on local file URI
  batches by avoiding the general URL parser.

## Verification

Run the registered focused tests, changed-scope coverage, and local registered
probe on Linux before opening the PR. GitHub Actions PR-scoped performance is
still the merge gate after push.
