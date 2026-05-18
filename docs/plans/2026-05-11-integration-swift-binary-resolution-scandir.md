# Integration Swift Binary Resolution Scandir Slice

## Context

Integration acceptance helpers resolve SwiftPM product binaries from `.build` trees before
starting end-to-end Melix stacks. The previous fallback used
`Path.glob("*/debug/<product>")`, which asks pathlib to allocate candidate paths for every
triple directory before executable filtering.

## Slice

Replace the fallback glob in `tests/integration/helpers.py` with a shared
`os.scandir()` candidate enumerator. The direct `.build/debug/<product>` lookup remains
first, and architecture-specific SwiftPM products are still selected by the existing
`(mtime, path-depth)` preference. Candidate validation should reuse one `Path.stat()`
result for regular-file filtering and mtime comparison so the resolver does not restat
executable candidates, and the scan should skip the already-checked top-level `debug`
directory rather than probing a non-existent nested `debug/debug/<product>` path.

## Probe

Registered PR-scoped probe: `integration-swift-binary-resolution-scandir`.

The probe builds a synthetic SwiftPM `.build` tree with many triple directories, compares
the legacy glob candidate enumerator with the new scandir enumerator, and reports:

- `candidate_count`
- `legacy_elapsed_ms_mean`
- `elapsed_ms_mean`
- `delta_ms_mean`
- `legacy_peak_bytes_mean`
- `peak_bytes_mean`
- `peak_bytes_delta_mean`

`delta_ms_mean` is a derived improvement margin against the legacy resolver, not
the direct resolver latency. The registered PR-scoped metric keeps a small
absolute tolerance so sub-5 ms timing noise cannot block a PR when direct
`elapsed_ms_mean` remains stable.

## Verification

Focused tests cover both package-scoped and root/scoped binary resolution and monkeypatch
`Path.glob` to fail, proving the fallback no longer depends on pathlib glob allocation.
Changed-scope coverage and the registered probe are required before merge.
