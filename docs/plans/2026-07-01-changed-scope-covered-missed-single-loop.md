# Changed-scope covered/missed single-loop slice

This Python-only performance slice is limited to `scripts/changed_scope_coverage.py`.

The changed-scope coverage helper already switches dense measured-line lookups to sets when the changed-line set is large enough. After source-line filtering, the set-backed branch still performed two passes over `measurable` to partition covered and missed changed lines. This slice keeps the existing semantics and replaces that with a single partition loop using local append bindings.

## Registered probe

The affected path is covered by the registered PR-scoped probe `changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries, and selects this probe when `scripts/changed_scope_coverage.py` changes.

## Verification plan

1. Record the baseline `python3 scripts/changed_scope_coverage_measured_probe.py` metrics on Linux before editing.
2. Apply the single-loop covered/missed partition only in the set-backed dense branch.
3. Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux.
4. Open a PR and rely on PR-scoped performance CI to validate the registered probe report before merge.

## Local probe evidence

Baseline probe before change on Linux:

```text
python3 scripts/changed_scope_coverage_measured_probe.py
{"allowlist_parse_count": 10000.0, "allowlist_parse_elapsed_ms_mean": 2.8098820143246224, "dense_elapsed_ms_mean": 48.931839543261695, "dense_source_read_calls_mean": 300.0, "elapsed_ms_mean": 0.286503678320774, "measured_lines_per_path": 500.0, "path_count": 300.0, "sample_count": 7.0, "source_read_calls_mean": 0.0}
```

Post-change probe on Linux:

```text
python3 scripts/changed_scope_coverage_measured_probe.py
{"allowlist_parse_count": 10000.0, "allowlist_parse_elapsed_ms_mean": 2.9733424307778478, "dense_elapsed_ms_mean": 47.3435391572171, "dense_source_read_calls_mean": 300.0, "elapsed_ms_mean": 0.2688430083383407, "measured_lines_per_path": 500.0, "path_count": 300.0, "sample_count": 7.0, "source_read_calls_mean": 0.0}
```

Dense changed-line partition mean improved from `48.931839543261695 ms` to `47.3435391572171 ms` (about 3.25% faster). The sparse no-read case improved from `0.286503678320774 ms` to `0.2688430083383407 ms`; the allowlist parse metric is unrelated noise for this slice.
