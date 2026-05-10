# Audio Preprocessing Integer Chunk Count Slice

## Scope

This performance slice is limited to the Python audio preprocessing hot path in
`services/mlx-worker-python/worker/runtime/audio_preprocessing.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`mlx-audio-local-uri-zero-copy-preprocess` in
`infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`,
`coverage_command`, and `probe_command` entries and measures local URI
preprocessing latency, peak bytes, and filesystem read/exists call counts.

## Change

Replace the floating-point `ceil(input_bytes / 8)` chunk-count calculation with
integer ceiling division, `(input_bytes + 7) // 8`, while preserving the minimum
chunk count of one. This avoids importing `math.ceil` and avoids float work on
every audio preprocessing request.

The same slice also normalizes this probe's registered Python invocations from
`python` to `python3` so scheduled and CI evidence follows the repository agent
contract.

## Verification plan

- Focused audio preprocessing/runtime tests for the registered probe.
- Changed-scope coverage through the registered probe coverage command.
- Local Linux execution of `scripts/mlx_audio_local_uri_probe.py` before and
after the change.
- GitHub Actions PR-scoped performance report remains the merge gate.

## Expected result

Behavior remains identical for all non-negative byte counts while
`elapsed_ms_mean` for the local URI preprocess probe is non-regressive or lower.
