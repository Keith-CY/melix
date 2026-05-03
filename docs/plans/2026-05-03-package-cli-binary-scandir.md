# Package macOS CLI build product scandir slice

## Scope

This Python-only performance slice is limited to Swift build-product resolution inside `scripts/package_macos_menubar_app.py`.

Touched paths:

- `scripts/package_macos_menubar_app.py`
- `scripts/package_macos_resolve_probe.py`
- `services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Goal

Reuse the existing `_resolve_built_product(...)` `os.scandir()` fallback for `resolve_built_cli_binary(...)` so CLI package resolution avoids allocating `Path.glob("*/debug/melix")` candidate lists on large Swift `.build` trees. Direct `.build/debug/melix` lookup remains first.

## Registered probe

The affected script is covered by registered PR-scoped probe `package-macos-resolve-fallback-scandir` in `infra/perf/pr_scoped_probes.json`. This slice keeps the existing focused commands and extends the probe command/metrics to time both:

- menubar fallback build-product resolution (`elapsed_ms_mean`, `elapsed_ms_min`)
- CLI fallback build-product resolution (`cli_elapsed_ms_mean`, `cli_elapsed_ms_min`)

## Linux validation boundary

This path is Python packaging tooling and is locally verifiable on Linux. It does not claim Swift runtime performance effects; it only measures Python build-product lookup cost over a synthetic Swift `.build` tree.

## Implementation plan

1. Add a regression test proving `resolve_built_cli_binary(...)` falls back through `os.scandir()` without `Path.glob(...)`.
2. Reuse `_resolve_built_product(repo_root / ".build", "melix")` for CLI resolution.
3. Extend the registered probe command to emit CLI lookup metrics alongside the existing menubar lookup metrics.
4. Run focused tests, changed-scope coverage, and the registered probe locally against `origin/main` and head.

## Success metrics

- Focused tests pass.
- Changed-scope coverage for touched Python paths is at least 95%.
- Local registered probe shows a lower `cli_elapsed_ms_mean` for head than `origin/main` on the same synthetic workload.
