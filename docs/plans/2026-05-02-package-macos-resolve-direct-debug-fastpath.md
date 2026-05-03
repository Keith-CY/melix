# Package macOS Resolve Direct Debug Fast Path

## Context

`package_macos_menubar_app.py` resolves Swift build products before writing the
self-contained macOS app bundle. The common local and CI shape places products
at `.build/debug/<product>`, but the resolver previously expanded and sorted
all `*/debug/<product>` triples before checking that direct path.

## Slice

This slice keeps behavior unchanged while making direct debug product lookup a
fast path:

- check `.build/debug/<product>` first for the menu bar app and Swift text worker;
- retain sorted triple fallback for platform-specific Swift build directories;
- register a PR-scoped probe that measures direct-path resolution with many
  unrelated build triples present.

## Probe

Registered probe: `package-macos-resolve-direct-debug-fastpath`.

The probe creates a synthetic `.build` tree with a direct debug product plus many
unrelated platform-triple directories, then repeatedly calls
`resolve_built_binary()`. Lower `elapsed_ms_mean` and `elapsed_ms_min` are better.

## Verification

Required local verification:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_package_macos_resolve_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_package_macos_resolve_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_package_macos_resolve_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_package_macos_resolve_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/package_macos_menubar_app.py scripts/package_macos_resolve_probe.py services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/package_macos_resolve_probe.py
```

CI must run the registered PR-scoped performance workflow for the same probe
before merge.
