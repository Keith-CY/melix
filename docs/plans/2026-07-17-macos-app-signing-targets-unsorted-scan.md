# macOS app signing-target unsorted scan

## Scope

This Python-only performance slice is limited to `_iter_nested_macho_signing_targets()` in `services/mlx-worker-python/worker/productization/macos_app_bundle.py`.

The helper must still return a stable sorted list of nested Mach-O signing targets and must continue to avoid following symlinked directories. The optimization removes the per-directory `sorted(os.scandir(...))` materialization because the function already sorts the final target list before returning it.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `macos-app-signing-targets-scandir` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries, and watches:

- `services/mlx-worker-python/worker/productization/macos_app_bundle.py`
- `services/mlx-worker-python/tests/test_macos_app_bundle.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/macos_app_signing_targets_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Plan

1. Keep the existing final target ordering contract by retaining the final `targets.sort(...)`.
2. Stream each `os.scandir()` iterator directly instead of sorting every directory's entries before traversal.
3. Add a regression guard that fails if this helper reintroduces built-in `sorted(...)` for per-directory scans.
4. Run the registered focused tests, changed-scope coverage command, and registered local probe on Linux before opening the PR.

## Acceptance

- Focused macOS app bundle signing-target tests pass locally.
- Changed-scope coverage for the touched scope is at least 95%.
- Registered local probe reports directionally lower `elapsed_ms_mean` versus `origin/main`.
- GitHub Actions and the PR-scoped performance report complete successfully before merge.
