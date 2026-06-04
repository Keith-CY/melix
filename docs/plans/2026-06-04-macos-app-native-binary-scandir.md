# macOS App Native Binary Candidate Scandir Slice

This Python-only performance slice narrows `worker.productization.macos_app_bundle._iter_python_native_binary_candidates()`.
The helper runs during app bundle slimming to locate packaged Python runtime executables and native extension libraries before stripping.

## Scope

- Replace `Path.rglob("*")` traversal in `_iter_python_native_binary_candidates()` with an explicit `os.scandir()` stack.
- Preserve behavior for Python runtime executables (`python`, `python3`, `python3.*`) and native binary suffixes (`.so`, `.dylib`).
- Continue skipping symlinks and metadata errors.
- Do not change stripping, signing, archive, or Swift/macOS runtime behavior.

## Registered probe

The affected path is covered by the PR-scoped probe `macos-app-native-binary-scandir` in `infra/perf/pr_scoped_probes.json`.
The probe exposes focused `test_command`, `coverage_command`, and inline `probe_command` entries and runs a synthetic packaged-runtime tree through `_iter_python_native_binary_candidates()` with repeated samples.

## Local verification

This slice is Python-only and locally verifiable on Linux. The local gate is:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_macos_app_bundle.py::test_bundle_slimming_helpers_cover_runtime_edge_cases services/mlx-worker-python/tests/test_macos_app_bundle.py::test_iter_python_native_binary_candidates_tolerates_scandir_metadata_errors services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_macos_app_bundle_probes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_macos_app_bundle.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_macos_app_bundle_probes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/macos_app_bundle.py services/mlx-worker-python/tests/test_macos_app_bundle.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id macos-app-native-binary-scandir --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/macos_app_native_binary_probe.json
```

GitHub Actions PR-scoped performance remains the merge gate for the registered base-vs-head probe report.
