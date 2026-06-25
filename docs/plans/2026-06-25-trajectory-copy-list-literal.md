# Trajectory provenance scalar list literal copy slice

This Python-only performance slice is limited to the scalar-list branch in
`worker.trajectory_provenance._copy_json_list`.

## Scope

The trajectory provenance normalizer copies JSON-like containers before they are
attached to training, adapter, and evaluation payloads. Previous slices already
avoid recursive copying for exact scalar lists; this slice keeps the same
container isolation semantics while replacing the scalar-list `list.copy()` call
with a list-display unpack copy (`[*value]`).

## Registered probe

The affected path is covered by the registered PR-scoped probe
`trajectory-provenance-copy-elision` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` fields for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `scripts/trajectory_provenance_copy_elision_probe.py`

## Metrics

Target metric: lower `scalar_list_elapsed_ms_mean`, negative
`scalar_list_delta_ms`, and non-regressed `scalar_list_speedup` in the registered
`trajectory-provenance-copy-elision` command-json probe while preserving nested
container copy isolation. The existing full-provenance `optimized_elapsed_ms_mean`
remains reported as a broader guardrail.

## Verification plan

Run the focused registry test command, changed-scope coverage command, and the
registered probe locally on Linux before opening the PR. The probe compares the
deep-copy baseline with the optimized provenance copier and reports elapsed time,
peak bytes, speedup, sample count, iteration count, and component count.
