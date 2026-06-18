# Startup product version regex cache

## Scope

This Python-only performance slice is limited to `read_product_version()` in
`services/mlx-worker-python/worker/productization/startup_signals.py`. The
function reads `pyproject.toml` during startup/update metadata paths and should
reuse a module-level compiled version pattern instead of compiling the same
regular expression on every call.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`startup-signals-version-compare-single-pass` in
`infra/perf/pr_scoped_probes.json`. This slice extends that registered probe so
its focused `test_command`, `coverage_command`, and `probe_command` include the
product-version read path and emit `product_version_*` metrics alongside the
existing startup version comparison/update-result metrics.

## Implementation plan

1. Add a regression test proving `read_product_version()` uses the compiled
   pattern rather than `re.search`.
2. Hoist the product-version regex to a module-level compiled pattern and call
   `.search()` on that object.
3. Extend `scripts/startup_signals_version_probe.py` with repeated
   `read_product_version()` measurements over a synthetic `pyproject.toml`.
4. Run the registered focused test command, changed-scope coverage command, and
   base-vs-head registered probe locally on Linux.

## Acceptance

Accept only if behavior tests and changed-scope coverage pass and the registered
probe reports a clear improvement for `product_version_elapsed_ms_mean` without
breaking existing comparison/update-result metrics.
