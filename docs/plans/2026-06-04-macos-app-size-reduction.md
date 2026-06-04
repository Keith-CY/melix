# macOS App Size Reduction

## Goal

Reduce the default packaged `Melix.app` size while keeping the app multimodal-ready.

## Decisions

- The default GitHub Actions app artifact must remain multimodal-ready.
- Do not remove vision, audio, dataset, or dataframe dependencies from the default artifact in this slice.
- Package Swift executables with release builds.
- Strip release Swift executables before app signing.
- Strip Python native binaries and the bundled Python executable/runtime dylibs before app signing.
- Prune package baggage that is not required at runtime: package `tests`, `test`, `testing`, `docs`, `doc`, and `__pycache__`; runtime `include`, `ensurepip`, `__pycache__`, static archives, and precompiled bytecode.
- Redirect packaged Python bytecode writes to `MELIX_RUNTIME_DIR/python-bytecode-cache` so imports do not recreate cache files inside the signed app bundle.
- Do not upload a separate debug-symbols artifact in this slice.

## Architecture

The packaging workflow remains owned by `.github/workflows/package-self-contained-app.yml`. It will build the three Swift products with `-c release` and then call `scripts/package_macos_menubar_app.py` as before.

The packaging script will resolve release build products first and pass a default slimming policy into `worker.productization.macos_app_bundle.write_unsigned_macos_app_bundle()`. The bundle writer owns file-level slimming because it already owns the copied app layout and runs before ad-hoc signing and archive creation.

## Implementation Slices

1. Add test coverage for release product resolution and workflow release build commands.
2. Add test coverage for bundle slimming: Swift strip, Python native strip, safe Python package pruning, and safe Python runtime baggage pruning.
3. Implement release-first product resolution and workflow release builds.
4. Implement app-bundle slimming helpers with manifest metrics.
5. Verify focused package tests and package smoke.
6. Rebuild a local package and compare size against the previous main artifact while preserving `xattr`, `codesign`, import, and launch-smoke behavior.

## Metrics

Baseline from the latest verified main artifact:

- `Melix.app`: about 1.13 GB logical size.
- Swift executables: about 333 MiB total.
- `python-site-packages`: about 672 MiB logical size.

Measured candidate savings:

- Swift `strip -x`: about 148 MiB.
- Python native `strip -x`: about 73 MiB.
- Safe Python package prune: about 54 MiB.
- Safe Python runtime baggage prune: about 7.5 MiB.

The final size gate is measured from a rebuilt package, not assumed from candidate probes.

Final local package measurement for this slice:

- `Melix.app`: 794 MiB on disk, 805,238,761 payload bytes.
- `Melix.zip`: 269,971,388 bytes.
- Payload reduction from the latest verified main artifact: 329,264,619 bytes, about 314.0 MiB or 29.0 percent.
- Manifest slimming savings: 234,567,796 bytes.

## Verification

Focused verification:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest \
  services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py \
  services/mlx-worker-python/tests/test_macos_app_bundle.py \
  -q
```

Package smoke:

```bash
make package-smoke
```

Local package acceptance must record:

- zip size and extracted app size.
- `codesign --verify --deep --strict --verbose=4`.
- `xattr -lr` and `xattr -cr` without `PrivateHeaders` errors.
- imports for `mlx`, `mlx_lm`, `mlx_vlm`, `cv2`, `pyarrow`, `scipy`, and `pandas`.
- app launch smoke where both worker sockets become ready and no fatal logs appear.

## Known Gaps

This slice does not reduce dependency scope. Further size reductions that remove `cv2`, `pyarrow`, `scipy`, `pandas`, `datasets`, `mlx-vlm`, or audio support require a separate product decision because the default artifact must remain multimodal-ready.
