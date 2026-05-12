# Multimodal Image Scheme Branch Comparisons

## Goal

Keep the Python multimodal image URI preprocessing behavior unchanged while reducing per-image branch overhead in `worker.runtime.multimodal_preprocessing`.

## Slice

The existing image URI parser already guarantees one `urlparse` call per `file://` image reference. This follow-up slice narrows the two hot scheme dispatch sites from set-membership checks to direct string comparisons after binding `reference.parsed.scheme` once. The change is intentionally limited to `_path_from_uri(...)` and `_bytes_from_image_uri(...)`.

## Probe coverage

Existing registered PR-scoped probe: `multimodal-preprocessing-image-uri-single-parse` in `infra/perf/pr_scoped_probes.json`.

The registered probe covers:

- `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/multimodal_image_uri_parse_probe.py`

It provides focused `test_command`, `coverage_command`, and `probe_command` entries and reports:

- `elapsed_ms_mean` — lower is better
- `urlparse_calls_mean` — lower is better and should remain `320.0` for the 640-image mixed local/file URI workload

## Verification plan

Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe result in CI.
