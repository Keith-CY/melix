# Maintenance benchmark normalized-value add binding performance

## Scope

This slice targets the registered `maintenance-benchmark-parameter-normalization-single-convert` PR-scoped performance probe. The affected path is `services/mlx-worker-python/worker/engine/maintenance_core.py`, specifically `_positive_sorted_values` and `_normalized_string_values`.

## Probe coverage

The existing registry entry in `infra/perf/pr_scoped_probes.json` covers this path and includes focused `test_command`, `coverage_command`, and `probe_command` entries. The probe exercises benchmark parameter normalization over repeated numeric and string parameter inputs.

## Implementation plan

- Keep benchmark parameter normalization behavior unchanged.
- Bind each temporary set's `add` method once per helper invocation and reuse the local binding inside the normalization loop.
- Run the focused registered tests, changed-scope coverage, and the registered probe locally on Linux.

## Validation boundary

This is a Python-only Linux-verifiable slice. No Swift runtime effect is claimed.
