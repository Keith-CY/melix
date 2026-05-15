# Startup version v-prefix fast path

## Goal

Reduce Python startup update-check overhead for version comparisons where package
metadata alternates between semver strings with and without a leading `v` prefix.
The comparison result stays unchanged: `v1.2.3` and `1.2.3` are equivalent after
trimming surrounding whitespace.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`startup-signals-version-compare-single-pass` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/startup_signals_version_probe.py`
- `scripts/changed_scope_coverage.py`

## Slice

`compare_versions()` now recognizes strings that differ only by a single leading
`v` before entering the component-by-component parser. The probe workload keeps
its existing differing-version comparisons and adds equivalent `v`/non-`v` pairs
so the registered metric covers the new fast path.

## Local evidence

Linux local registered probe (`scripts/startup_signals_version_probe.py`, three
runs, default 7 samples/run, `pair_count=12000` with half differing pairs and
half `v`/non-`v` equivalent pairs):

- base `elapsed_ms_mean` samples: `49.255820`, `47.349513`, `49.424493`
- head `elapsed_ms_mean` samples: `15.558594`, `16.808802`, `15.713704`
- aggregate base mean `48.676609 ms`; aggregate head mean `16.027033 ms`
- delta `-32.649576 ms` (`-67.07%`)
- `comparison_total=-48.0`, `peak_bytes_mean=112.0`, `sample_count=7` in the
  registered probe output

Focused pytest and changed-scope coverage passed locally with 100% changed-line
coverage for the modified Python source, tests, and probe script.
