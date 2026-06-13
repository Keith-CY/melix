# Prepared Vision Request Slots

## Scope

This Python-only performance slice is limited to the hot prepared multimodal request container used by `prepare_vision_request()` and downstream VLM token accounting. The behavior and public fields stay unchanged; the container only drops the per-instance `__dict__` allocation via dataclass slots.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `multimodal-preprocessing-local-uri-parse-elision` in `infra/perf/pr_scoped_probes.json`. The entry watches:

- `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/multimodal_preprocessing_uri_probe.py`

The registry includes focused `test_command`, `coverage_command`, and `probe_command` entries. This slice adds the new slots regression to the registered focused test and coverage commands so CI validates both behavior parity and the object-layout expectation.

## Verification Plan

Run locally on Linux before pushing:

1. Focused pytest for the multimodal preprocessing probe scope.
2. Changed-scope coverage for the same registered files.
3. The registered `multimodal_preprocessing_uri_probe.py` probe.

GitHub Actions PR-scoped performance remains the merge gate after the PR is opened.
