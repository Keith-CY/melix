# Package macOS Fallback Build Product Scandir Plan

## Goal

Reduce Python packaging-script overhead when resolving Swift build products from triple-specific `.build/<triple>/debug/<product>` directories after the direct `.build/debug/<product>` candidate is absent.

## Linux Verification Boundary

This slice changes the Python packaging helper and its synthetic probe only. It is fully locally verifiable on Linux because the probe creates a fake Swift `.build` tree and does not execute Swift binaries.

## Touched Files

- `scripts/package_macos_menubar_app.py`
- `scripts/package_macos_resolve_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Optimization Slice

- Keep the existing direct `.build/debug/<product>` fast path unchanged.
- Replace the fallback `Path.glob("*/debug/<product>")` traversal with a single `os.scandir()` pass over build triples, preserving sorted triple-directory order before testing each `debug/<product>` candidate.
- Retarget the registered PR-scoped probe from the direct fast path to the fallback path so CI measures the changed behavior.

## Performance Probe

Registered probe: `package-macos-resolve-fallback-scandir` in `infra/perf/pr_scoped_probes.json`.

The probe builds 1,500 synthetic triple directories, omits the direct debug candidate, places `melix-menubar` in the first sorted triple, and reports `elapsed_ms_mean` and `elapsed_ms_min` over nine samples.

## Success Metrics

- Focused tests pass.
- Changed-scope coverage remains at least 95%.
- Registered probe shows lower fallback-resolution elapsed time versus the `origin/main` baseline.
