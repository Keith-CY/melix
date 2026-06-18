# Trajectory Manifest Text Fast Path

## Scope

This slice optimizes `trajectory_provenance_from_snapshot_manifest()` and the
snapshot-manifest load path for the common schema-backed trajectory manifest case.
Manifest text fields are usually already normalized. `_strip_manifest_text()` now
returns exact `str` values directly when the first and last characters are not
whitespace, while preserving the existing `.strip()` behavior for padded strings
and non-string values. The extractor also avoids normalizing the `format` marker
when it already exactly matches `agentic_tool_trace`, and reuses the already-read
`trajectory_trace_digest` value later in the same extraction pass.

Behavior remains unchanged for padded, non-exact, or non-string manifest values:
those still fall back to the existing normalized text check before rejecting or
accepting the manifest.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The probe
watches `services/mlx-worker-python/worker/trajectory_provenance.py`, focused
trajectory provenance tests, PR-scoped performance tests, and
`scripts/trajectory_manifest_json_load_probe.py`; it includes focused
`test_command`, `coverage_command`, and `probe_command` entries.

## Verification plan

- Run the focused trajectory provenance tests named by the registered probe.
- Run the registered changed-scope coverage command for
  `worker.trajectory_provenance`.
- Run `scripts/trajectory_manifest_json_load_probe.py` locally on Linux before
  and after the change and compare `new_mean_ms`, `delta_ms`, `speedup`, and
  peak memory.
- Rely on GitHub Actions PR-scoped performance workflow for the final registered
  CI probe report before merge.

## Expected outcome

The common normalized-manifest path should avoid redundant strip work and one
redundant manifest lookup per extraction, producing a small reduction in
`new_mean_ms` without changing output fields or nested-copy behavior.
