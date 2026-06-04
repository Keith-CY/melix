# macOS app signing target scandir slice

This Python-only performance slice is limited to nested Mach-O signing target
discovery in `services/mlx-worker-python/worker/productization/macos_app_bundle.py`.
The previous implementation uses `Path.rglob("*")`, which allocates a `Path`
object for every directory and file before filtering to Mach-O files.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe
`macos-app-signing-targets-scandir` in `infra/perf/pr_scoped_probes.json`. The
probe includes focused `test_command`, `coverage_command`, and `probe_command`
entries and runs locally on Linux with synthetic Mach-O-like fixture files.

## Slice plan

1. Add a regression test that forbids `Path.rglob()` for nested signing target
   discovery and confirms directory symlinks are not traversed.
2. Replace the `Path.rglob("*")` scan with `os.walk(..., followlinks=False)` and
   inspect only filenames for Mach-O magic values.
3. Register the PR-scoped probe and script so CI compares origin/main and head.
4. Run focused pytest, changed-scope coverage, and the registered probe locally
   before opening the PR.
5. Use GitHub Actions PR-scoped performance as the final merge gate.

## Expected metrics

The probe reports `elapsed_ms_mean`, `elapsed_ms_min`, `discovered_count`, and
fixture shape counts for a synthetic `.app` with nested helper bundles and noise
files. The expected direction is lower scan latency while preserving the exact
number of discovered signing targets.
