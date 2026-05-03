# Packaging Runtime Dependency Slimming

## Goal

Reduce the Python payload copied into the preview macOS app bundle by separating Python worker
runtime dependencies from test and build-time tooling dependencies.

## Scope

- Keep the default local developer bootstrap behavior intact for tests.
- Move Python-only test and code-generation tooling out of the worker's base runtime dependency set.
- Make the package workflow create a separate runtime-only virtual environment for the app bundle.
- Keep packaging smoke tests on the developer environment so they can still use pytest.

## Performance Probes and Metrics

- `packaging.python_runtime_site_packages_bytes`: size of the runtime-only package site-packages tree.
- `packaging.python_runtime_site_packages_file_count`: file count of the runtime-only package site-packages tree.
- `packaging.bundle_write_seconds`: elapsed time to materialize the app bundle.
- `packaging.archive_seconds`: elapsed time to create the zip archive.

The current local baseline for the developer environment is approximately 650 MB and 10,910 files
under `.venv/lib/python3.13/site-packages`; the self-contained app probe wrote a 704 MB bundle and
spent 13.675 seconds materializing the bundle plus 24.474 seconds archiving it.

## Files

- `services/mlx-worker-python/pyproject.toml`
- `uv.lock`
- `.github/workflows/package-self-contained-app.yml`
- `services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py`
- `services/mlx-worker-python/tests/test_packaging_dependencies.py`

## Verification

- Focused packaging dependency tests.
- `make package-smoke`
- Runtime-only environment size and file-count probe.

## Implementation Results

- Runtime-only package environment: `.venv-package/lib/python3.13/site-packages` measured at
  approximately 622 MB and 10,269 files.
- Developer environment baseline after the same lock update:
  `.venv/lib/python3.13/site-packages` measured at approximately 653 MB.
- Removed from the runtime-only package environment: `pytest`, `coverage`, and `grpc_tools`.
- Runtime-only bundle probe with fake Swift executables wrote a 676,480,751 byte `.app`, produced a
  216,059,040 byte archive, and reported `write_total_seconds=5.714668`,
  `copy_python_site_packages_seconds=4.719971`, and `archive_seconds=19.918`.
