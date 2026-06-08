# Dataset split first-character match fast path

## Scope

Optimize one Python hot path in `services/mlx-worker-python/worker/dataset_registry/catalog.py`: split matching for dataset file and parent path parts. The previous first-character guard used `first_char.lower()` when the incoming path part started with an uppercase letter, allocating a lowercased one-character string on mismatch checks. This slice replaces that guard with an ASCII ordinal comparison helper while preserving mixed-case split matching.

## Registered probe coverage

The affected path is covered by the registered PR-scoped `dataset-registry-limited-read-streaming` command-json probe in `infra/perf/pr_scoped_probes.json`. The probe watches `catalog.py`, `test_dataset_registry.py`, `test_pr_scoped_performance.py`, and `scripts/dataset_registry_split_match_probe.py`, and includes focused `test_command`, `coverage_command`, and `probe_command` entries.

The probe reports `elapsed_ms_mean`, `path_constructor_calls_mean`, and `peak_bytes_mean` for `_path_matches_split()` across a synthetic dataset path set. This slice uses `elapsed_ms_mean` as the primary Linux performance signal and keeps `path_constructor_calls_mean` at zero.

## Implementation plan

1. Add a small ASCII helper that compares an arbitrary one-character string with an already-normalized lowercase split first character without calling `.lower()`.
2. Use the helper in `_path_part_matches_split()` only for the existing first-character rejection guard.
3. Add focused regression assertions for uppercase, lowercase, and non-matching first-character behavior.
4. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before pushing.
5. Use the PR-scoped performance GitHub Actions report as the final registered probe validation source before merge.

## Success metrics

- Behavior parity: focused dataset registry and PR-scoped performance tests pass.
- Changed-scope coverage: registered coverage command remains at or above 95%.
- Performance: `dataset_registry_split_match_probe.py` improves `elapsed_ms_mean` versus same-branch pre-change baseline while keeping `path_constructor_calls_mean=0`.
