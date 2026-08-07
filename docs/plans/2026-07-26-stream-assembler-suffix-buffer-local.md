# Stream Assembler Structural Suffix Buffer Local Slice

## Scope

Optimize the `_partial_structural_tag_suffix` hot path by reading the assembler
buffer into a local variable once per call. This keeps structural tag suffix
behavior unchanged while reducing repeated instance attribute reads in the
registered stream assembler prefix probe.

## Probe

The affected path is covered by the registered PR-scoped probe
`stream-assembler-structural-prefix-cache` in
`infra/perf/pr_scoped_probes.json`. The entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/stream_assembler_structural_prefix_probe.py`

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and
`scripts/stream_assembler_structural_prefix_probe.py` locally on Linux before PR
creation. The PR-scoped performance workflow remains the merge gate.