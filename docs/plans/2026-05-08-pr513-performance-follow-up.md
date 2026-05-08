# PR 513 Performance Report Follow-Up Plan

## Goal

Correct the PR-scoped performance report semantics that misclassified
informational metrics in PR 513, then reduce avoidable peak allocations in the
shared WAV PCM chunking helper used by the speech runtime.

## Scope

This follow-up is intentionally narrow. It does not change the progressive
speech streaming protocol, the HTTP streaming contract, or generated protocol
artifacts from PR 513.

## Work Items

1. Teach the PR-scoped performance reporter that `direction: informational`
   metrics are measured and rendered but never counted as regressions or
   improvements.
2. Add focused coverage proving informational metrics remain neutral when head
   values are higher or lower than base values.
3. Reduce `worker.runtime.wav_helpers.audio_to_pcm_chunks` peak live memory by
   resetting the reusable PCM array before yielding the materialized bytes, and
   inline the per-sample clamp/scale operation on the hot path.
4. Keep the existing WAV byte output contract unchanged for nested iterables,
   array-like `.flat` values, and big-endian byte swapping.

## Metrics

Primary probes:

- `mlx-audio-wav-streaming-pcm`
  - `peak_bytes_mean`: lower is better, with the existing 5 percent warning
    threshold.
  - `elapsed_ms_mean`: informational; a lower value should be rendered as data
    but must not contribute to regression or improvement counts.
- `mlx-audio-speech-signature-cache`
  - `elapsed_ms_mean`: lower is better.
  - `inspect_signature_calls_mean`: lower is better and should remain `0.0`.

Success criteria:

- Targeted Python tests pass.
- Changed-line coverage for touched Python paths is at least 95 percent.
- The two primary probes run locally and show no report-level false regression
  from informational metrics.
- Any remaining runtime probe variance is reported explicitly in the PR body.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_metric_and_probe_helpers_cover_error_branches \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_rendering_marks_regressions_and_builds_sticky_comment \
  services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_audio_to_wav_bytes_streams_nested_samples_and_clamps_values \
  services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_audio_to_wav_bytes_does_not_materialize_flat_sample_list \
  services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_audio_to_wav_bytes_writes_little_endian_chunks_on_big_endian_hosts

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_metric_and_probe_helpers_cover_error_branches \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_rendering_marks_regressions_and_builds_sticky_comment \
  services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_audio_to_wav_bytes_streams_nested_samples_and_clamps_values \
  services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_audio_to_wav_bytes_does_not_materialize_flat_sample_list \
  services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_audio_to_wav_bytes_writes_little_endian_chunks_on_big_endian_hosts

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o /tmp/pr513-performance-followup-coverage.json

python3 scripts/python_changed_line_coverage.py \
  --coverage-json /tmp/pr513-performance-followup-coverage.json \
  services/mlx-worker-python/worker/productization/pr_scoped_performance.py \
  services/mlx-worker-python/worker/runtime/wav_helpers.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  services/mlx-worker-python/tests/test_mlx_audio_runtime.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/mlx_audio_wav_streaming_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/mlx_audio_speech_signature_probe.py
```
