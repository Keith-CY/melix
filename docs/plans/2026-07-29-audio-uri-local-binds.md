# Audio URI local field binding

## Scope

This Python performance slice is limited to `prepare_audio_input()` in the
worker audio preprocessing path. The registered PR-scoped probe is
`mlx-audio-local-uri-zero-copy-preprocess`, which covers
`services/mlx-worker-python/worker/runtime/audio_preprocessing.py`, the focused
audio runtime tests, and `scripts/mlx_audio_local_uri_probe.py`.

## Optimization

For local URI preprocessing, cache `request.audio_bytes` and `request.audio_uri`
once at function entry and reuse those local values through path resolution,
error reporting, and the prepared-input reference. This avoids repeated protobuf
field/property lookups on the hot transcription URI path while preserving the
existing zero-copy mode and metadata derivation behavior.

## Verification

Run the registered focused test command, changed-scope coverage command, and
registered probe command locally on Linux before pushing. CI remains the source
of truth for the PR-scoped performance report and before/after probe delta.
