# Audio prepared input slots performance slice

## Scope

This Python-only performance slice is limited to the audio preprocessing hot path
that returns `PreparedAudioInput` for inline and local URI audio requests. The
slice keeps request parsing, byte accounting, zero-copy URI behavior, and
decoded-text behavior unchanged.

## Registered probe

The affected path is covered by the existing PR-scoped registered probe
`mlx-audio-local-uri-zero-copy-preprocess` in `infra/perf/pr_scoped_probes.json`.
That probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries and measures elapsed time, peak memory, and local URI
read-byte calls.

## Implementation plan

- Add regression coverage proving `PreparedAudioInput` uses slots while still
  exposing the same fields and `decoded_text()` helper.
- Add `slots=True` to the frozen `PreparedAudioInput` dataclass to avoid a per
  instance `__dict__` allocation on repeated preprocessing calls.
- Do not change audio URI parsing, file stat/read behavior, or transcription
  runtime integration.

## Verification

Run the registered focused tests, changed-scope coverage, and local Linux probe
before opening the PR. Use the registered PR-scoped performance CI report as the
merge gate.
