# Audio local URI unquote fast path

## Scope

This Python-only performance slice is limited to the MLX audio local URI
preprocessing path in `services/mlx-worker-python/worker/runtime/audio_preprocessing.py`.
It preserves local `file://` URI behavior while avoiding `urllib.parse.unquote(...)`
for the common local path case that contains no percent escapes.

## Registered probe

The affected path is covered by the existing `mlx-audio-local-uri-zero-copy-preprocess`
PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`. The entry includes
focused `test_command`, `coverage_command`, and `probe_command` values and reports:

- `elapsed_ms_mean` (`lower_is_better`)
- `peak_bytes_mean` (`lower_is_better`)
- `local_uri_read_bytes_calls_mean` (`lower_is_better` guard rail)

## Verification plan

Run the registered focused tests, changed-scope coverage command, and local Linux
probe before opening the PR. Use the GitHub PR-scoped performance workflow as the
merge gate for the registered probe report.

## Success criteria

- Local URI decoding behavior remains unchanged, including encoded paths.
- Changed-scope coverage remains at least 95%.
- The registered local probe shows a clear non-regression or improvement in
  `elapsed_ms_mean` while preserving zero local URI file reads.