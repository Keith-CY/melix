# macOS app path-size scandir slice

This Python performance slice is limited to `worker.productization.macos_app_bundle._path_size_bytes`.

## Scope

- Replace the current `os.walk` directory-size pass with an explicit `os.scandir` stack so package-pruning size accounting avoids per-root `Path` and filename joins on large app-bundle trees.
- Preserve existing semantics: files and symlinks contribute their `lstat`/non-following stat size, directory symlinks are not traversed, metadata errors are ignored, and missing/unreadable roots return zero contribution.
- Add a registered PR-scoped probe, `macos-app-path-size-scandir`, because the current macOS app bundle probes cover adjacent resource/native/signing scans but do not directly measure `_path_size_bytes`.

## Verification plan

- Focused tests for `_path_size_bytes` metadata-error tolerance and direct `os.scandir` traversal.
- `test_pr_scoped_performance` registry checks proving the macOS app bundle path selects the new probe and that the probe script emits JSON metrics.
- Changed-scope coverage via the registered probe `coverage_command`.
- Local Linux registered probe run for `scripts/macos_app_path_size_probe.py`; CI remains the PR-scoped merge gate.

## Metrics

The probe synthesizes a 2,500-file package tree plus a directory symlink and reports:

- `elapsed_ms_mean` / `elapsed_ms_min` (lower is better)
- `file_count` (informational)
- `measured_size_bytes` and sample count for evidence sanity checks
