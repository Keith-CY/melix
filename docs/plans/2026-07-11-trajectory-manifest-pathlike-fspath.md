# Trajectory manifest pathlike fspath performance slice

## Scope

This Python-only performance slice is limited to `worker.trajectory_provenance.load_trajectory_provenance_from_snapshot_manifest(...)` in `services/mlx-worker-python/worker/trajectory_provenance.py`.

The affected path is covered by registered PR-scoped probe `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches the trajectory provenance module, focused tests, probe script, and registry.

## Change

Path-like manifest inputs now use `os.fspath(...)` and the same direct binary `open(...).read()` path used by exact `str` and `Path` inputs. This preserves the existing pathlike contract while avoiding the fallback `Path(...)` wrapper allocation and `Path.read_bytes()` bound-method path for custom `os.PathLike` manifest references.

## Verification Plan

Run the registered focused trajectory manifest tests, changed-scope coverage, `git diff --check`, and the registered `trajectory-manifest-json-load` probe locally on Linux before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe report.

No Swift runtime behavior is changed or locally claimed by this slice.
