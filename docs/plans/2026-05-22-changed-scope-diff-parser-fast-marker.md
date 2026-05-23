# Changed-scope coverage diff marker fast path

## Scope

This slice keeps the changed-scope coverage behavior unchanged and only trims the
hot diff-parser loop in `scripts/changed_scope_coverage.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`.
That probe already declares focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Change

`_parse_changed_lines()` now binds `changed_by_path.setdefault` once before the
loop and treats any diff line beginning with `\` as a metadata marker. Git emits
these marker lines outside the old/new line streams (for example `\ No newline
at end of file`), so skipping them directly avoids an extra `startswith()` call
without changing added-line accounting.

## Local evidence

Baseline registered probe (`changed-scope-coverage-diff-parser`), three runs:

- `elapsed_ms_mean=3.435669932514429`
- `elapsed_ms_mean=2.9468576540239155`
- `elapsed_ms_mean=3.06025294897457`

Updated registered probe, three runs:

- `elapsed_ms_mean=3.4006948311192295`
- `elapsed_ms_mean=2.908959499715517`
- `elapsed_ms_mean=2.921043293705831`

Mean-of-means moved from `3.147593511837636` ms to `3.076899208846527` ms
(`-0.070694302991109` ms, about `2.25%` faster). The probe output preserved
`file_count=240` and `changed_line_count=7680`.

## Verification

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q tests/test_changed_scope_coverage.py`
- Registered probe command from `changed-scope-coverage-diff-parser`

## Boundaries

This is a Linux-local Python tooling slice. No Swift runtime behavior is changed.
