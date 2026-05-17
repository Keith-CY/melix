# Dataset split match filename-first optimization

## Scope

This Python-only performance slice is limited to selected-split matching in
`services/mlx-worker-python/worker/dataset_registry/catalog.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-registry-limited-read-streaming` in `infra/perf/pr_scoped_probes.json`.
The registry entry already has focused `test_command`, `coverage_command`, and
`probe_command` entries covering the catalog implementation, dataset registry
unit tests, PR-scoped performance selection tests, and
`scripts/dataset_registry_split_match_probe.py`.

## Change

`_path_matches_split(...)` now checks the filename before parent path segments.
Most selected-split hits are encoded in the dataset shard filename, for example
`validation-00000.jsonl`; checking the filename first avoids lowercasing and
scanning parent config segments on those hot-path hits while preserving directory
split matching such as `validation/shard-00000.jsonl`.

The per-segment comparison logic moved into `_path_part_matches_split(...)` so
filename and parent checks share the exact same equality, prefix, and suffix-stem
semantics.

## Validation plan

1. Run focused dataset registry tests plus registered probe-selection and probe
   smoke tests.
2. Run changed-scope coverage for the catalog/test/probe files.
3. Run the registered probe locally on Linux with repeated samples against this
   branch and compare with the `origin/main` baseline collected before the edit.
4. Use GitHub Actions PR-scoped performance as the final merge gate.

## Local registered probe result

Registered probe runner after implementation with `MELIX_DATASET_SPLIT_MATCH_PROBE_SAMPLES=7`:

- base (`origin/main`, `7553cbc7`): `elapsed_ms_mean=84.118718`,
  `peak_bytes_mean=42221.0`
- head: `elapsed_ms_mean=77.890096`, `peak_bytes_mean=42173.0`
- elapsed delta: `-6.228622 ms` (`-7.40%`)
- parity guards unchanged: `path_constructor_calls_mean=0.0`,
  `matched_files_mean=5000.0`, `file_count=20000.0`
- changed-scope coverage from the registered command: `96%`
