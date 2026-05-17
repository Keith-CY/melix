# Video Prepared Input Slots Performance Slice

## Scope

This Python-only slice is limited to video preprocessing record containers in
`services/mlx-worker-python/worker/runtime/video_preprocessing.py`. It preserves
video request parsing, URI validation, filename/format inference, identity hash
construction, and public field access while removing per-instance `__dict__`
allocation for the prepared input and parsed reference records.

## Registered Probe

The affected path is covered by the existing PR-scoped registered probe
`video-preprocessing-uri-byte-length-reuse` in
`infra/perf/pr_scoped_probes.json`. The registry entry watches
`video_preprocessing.py`, `test_video_preprocessing.py`, the PR-scoped
performance tests, and `scripts/video_preprocessing_uri_probe.py`; it includes
focused `test_command`, `coverage_command`, and `probe_command` entries.

The probe reports elapsed time, parsed-reference call counts, byte-length read
counts, and checksum stability for repeated URI preprocessing.

## Implementation Plan

1. Add regression coverage proving `PreparedVideoInput` and
   `ParsedVideoReference` are slotted while retaining field access.
2. Add `slots=True` to both frozen dataclasses.
3. Run the registered focused tests, changed-scope coverage, and local Linux
   probe before pushing.
4. Use the PR-scoped performance CI report as the merge gate.

## Validation Boundary

This is a Python-only slice and can be locally verified on Linux. No Swift
runtime effect is claimed for this slice.
