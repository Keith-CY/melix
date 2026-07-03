# Dataset Source Lightweight Conversion Slice

## Goal

Reduce Python overhead in dataset ingest source discovery for the common source
path materialization step used by the registered source records probe.

## Linux Verification Scope

This slice is Python-only under `services/mlx-worker-python`, so it is locally
verifiable on Linux with the registered focused tests, changed-scope coverage,
and PR-scoped performance probe.

## Touched Files

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `docs/plans/2026-07-03-dataset-source-path-list-comprehension.md`

## Registered Probe

The affected path is already covered by the `dataset-source-records-scandir`
entry in `infra/perf/pr_scoped_probes.json`:

- `watch_globs` includes `services/mlx-worker-python/worker/productization/dataset_preparation.py`, the focused tests, the probe script, and the registry.
- `test_command` covers the source-kind fast paths, source path scandir traversal, record construction, and probe registry dispatch checks.
- `coverage_command` replays the focused tests and reports changed-scope coverage for the dataset preparation code and probe surface.
- `probe_command` runs `scripts/dataset_source_records_probe.py`, which seeds a 250-directory / 7,000-file synthetic tree and measures path discovery, source-kind classification, and record construction.

## Optimization Slice

Keep the existing `os.scandir()` traversal and sorted string ordering, but reduce
lightweight conversion overhead in the source path materialization hot path:

1. Replace `list(map(Path, file_paths))` with an explicit list comprehension after
   sorting collected path strings.

The change preserves returned `list[Path]`, source-kind classification, record
payload, and ordering semantics. The earlier `_record(...)` helper-call elision
was not retained because local repeated probe runs and the CI report showed it
could add record-construction p95 noise without a stable improvement.

## Success Metrics

- Functional behavior remains unchanged for nested source trees and scandir error handling.
- Changed-scope coverage remains at least 95%.
- The registered `dataset-source-records-scandir` probe should show directionally lower `elapsed_ms_mean` for source path discovery versus the `origin/main` baseline, with neutral record-construction metrics and no source-kind correctness or file-count changes.

## Verification Commands

- Registered focused `test_command` from `infra/perf/pr_scoped_probes.json`.
- Registered `coverage_command` from `infra/perf/pr_scoped_probes.json`.
- Registered `probe_command` from `infra/perf/pr_scoped_probes.json`, run locally before and after implementation.
- `git diff --check`.
