# Trajectory Manifest Open Fast Path

This Python-only performance slice is limited to `worker.trajectory_provenance.load_trajectory_provenance_from_snapshot_manifest`.

## Scope

The manifest loader is a hot path for agentic trajectory provenance extraction. The current implementation materializes a `Path` for string inputs and then delegates to `Path.read_bytes()`. This slice keeps the same JSON parsing and provenance projection behavior while reading the manifest through `open(..., "rb")`, which accepts both `str` and `Path` inputs and avoids the extra `Path` allocation/delegation for string paths.

## Registered performance probe

The affected path is covered by registered PR-scoped probe `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The probe includes focused tests, changed-scope coverage, and `scripts/trajectory_manifest_json_load_probe.py`.

## Verification plan

1. Run the registered focused test command for `trajectory-manifest-json-load` locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered probe command locally on Linux and record old/new metrics.
4. Use GitHub Actions PR-scoped performance as the final registered probe validation and merge gate.

## Metrics expectation

The expected improvement is small but directional: lower `new_mean_ms`/`elapsed_ms_mean` for manifest JSON loading by avoiding `Path.read_bytes()` delegation while preserving the existing byte-loading JSON parser behavior.
