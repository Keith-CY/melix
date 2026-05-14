# Package macOS Lex-First Binary Resolution Slice

## Scope

This Python performance slice targets `scripts/package_macos_menubar_app.py` only.
The package helper already avoids `Path.glob()` and resolves Swift build products
from `debug/<product>` or `<triple>/debug/<product>` candidates. This slice keeps
that behavior and focuses on the common fallback shape where the lexicographically
first build triple contains the requested product.

## Optimization Hypothesis

For package probe workloads with many Swift build triple directories, the fallback
currently sorts every triple name before checking the first candidate. A first
`os.scandir()` pass can identify the lexicographically first triple name and check
that candidate directly. If it exists, resolution avoids allocating and sorting the
full triple-name list. If it does not exist, the helper falls back to the existing
sorted candidate walk to preserve behavior.

## Registered Probe

Existing registered probe: `package-macos-resolve-fallback-scandir`.

The probe has focused `test_command`, `coverage_command`, and `probe_command`
entries in `infra/perf/pr_scoped_probes.json` and watches:

- `scripts/package_macos_menubar_app.py`
- `services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py`
- `scripts/package_macos_resolve_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/changed_scope_coverage.py`

## Verification Plan

Run the registered focused tests, changed-scope coverage, and the registered probe
locally on Linux. Compare `scripts/package_macos_resolve_probe.py` against the
origin/main baseline and accept only if `elapsed_ms_mean` improves without behavior
regression.
