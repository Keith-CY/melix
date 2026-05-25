# Trajectory Manifest JSON Byte Loading

## Scope

This Python-only performance slice is limited to loading trajectory snapshot
manifests in `services/mlx-worker-python/worker/trajectory_provenance.py`.
The existing loader read UTF-8 text with `Path.read_text()` and then parsed the
string with `json.loads()`. This slice reads manifest bytes directly and lets the
JSON decoder consume the UTF-8 bytes, avoiding the separate Python string decode
allocation while preserving the same provenance field normalization behavior.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The probe
provides focused `test_command`, `coverage_command`, and `probe_command` entries
for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

The probe builds a deterministic synthetic `agentic_tool_trace` manifest and
compares the previous `read_text()` + `json.loads(str)` path against the new
`read_bytes()` + `json.loads(bytes)` path. It reports elapsed mean, delta,
speedup, peak memory, sample count, iteration count, and component count. The
registered `probe_command` can fall back to the head checkout's probe script when
a base checkout lacks the new probe file, while imports continue to run from the
checkout under measurement.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and local
registered probe on Linux before opening the PR. The GitHub Actions PR-scoped
performance workflow remains the merge gate for the registered probe result in
CI.
