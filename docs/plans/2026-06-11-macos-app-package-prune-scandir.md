# macOS app package-prune scandir slice

This Python performance slice is limited to `worker.productization.macos_app_bundle._prune_python_package_baggage`.

## Slice

- Replace the package baggage pruning `os.walk` pass with an explicit `os.scandir` stack so app bundle packaging can stream package directories while deleting prunable `tests`, `docs`, and `__pycache__` subtrees.
- Preserve existing semantics: directory symlinks with prunable names are unlinked instead of traversed, non-prunable symlinks are not followed, metadata and deletion errors are ignored, and byte accounting still uses `_path_size_bytes` before deletion.
- Register the focused PR-scoped probe `macos-app-package-prune-scandir` because adjacent macOS app bundle probes cover resource bundle, native binary, path-size, and signing-target scans but did not directly measure package pruning.

## Verification

- Focused regression tests for package-prune behavior and a guard that fails if `_prune_python_package_baggage` returns to `os.walk`.
- `test_pr_scoped_performance` registry checks proving the macOS app bundle path selects the new probe and that the probe script emits JSON metrics.
- Changed-scope coverage via the registered probe `coverage_command`.
- Local Linux probe execution for `_prune_python_package_baggage`; GitHub Actions PR-scoped performance remains the base-vs-head merge gate.

## Expected outcome

The packaging prune pass should reduce traversal overhead on synthetic package trees while keeping package slimming output and byte accounting stable.
