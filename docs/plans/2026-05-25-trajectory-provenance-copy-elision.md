# Trajectory Provenance Copy Elision

## Scope

This Python-only performance slice is limited to trajectory provenance
normalization in `services/mlx-worker-python/worker/trajectory_provenance.py`.
The slice preserves the existing behavior that mutable provenance containers are
isolated from caller-owned inputs, while replacing unconditional `copy.deepcopy`
for common JSON-shaped provenance payloads with a targeted recursive copy.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`trajectory-provenance-copy-elision` in `infra/perf/pr_scoped_probes.json`. The
probe provides focused `test_command`, `coverage_command`, and `probe_command`
entries for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/trajectory_provenance_copy_elision_probe.py`

The probe compares the previous deepcopy-based normalization against the new
copy helper on a deterministic synthetic provenance payload and reports elapsed
mean, delta, speedup, peak memory, sample count, iteration count, and component
count. Because this slice introduces a new probe script, the registered
`probe_command` falls back to the head checkout's script when the base checkout
lacks `scripts/trajectory_provenance_copy_elision_probe.py`, while still running
from the base checkout so imports measure the base implementation. The probe
script also falls back to `copy.deepcopy` when the base checkout lacks the new
helper symbol, keeping base/head command execution symmetric.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and local
registered probe on Linux before opening the PR. The GitHub Actions PR-scoped
performance workflow remains the merge gate for the registered probe result in
CI.
