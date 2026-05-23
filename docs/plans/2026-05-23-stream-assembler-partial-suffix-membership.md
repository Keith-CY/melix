# Stream assembler partial suffix membership slice

## Scope

This slice is limited to the Python stream assembler partial structural tag suffix check in `services/mlx-worker-python/worker/runtime/stream_assembler.py`.

## Registered probe

The affected path is already covered by the registered PR-scoped performance probe `stream-assembler-structural-prefixes` in `infra/perf/pr_scoped_probes.json`. The registration includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `scripts/stream_assembler_structural_prefix_probe.py`

## Optimization plan

Replace repeated structural open-tag `startswith(...)` checks in `_partial_structural_tag_suffix()` with cached per-mode partial-suffix membership sets. The check still scans only the last `<` marker candidate, preserves incomplete Harmony reasoning markers such as `<|channel>tho`, and keeps tool prefixes disabled for non-tool parser requests.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and registered local probe on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate for CI validation.
