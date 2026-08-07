# Real Model HF Cache Max-Entry Fallback Performance

## Scope

Optimize the local Hugging Face cache fallback used by `scripts.real_model_support` when `refs/main` is unavailable. The slice is limited to selecting the lexicographically latest snapshot directory under `models--*/snapshots/`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `real-model-support-hf-cache-latest-snapshot` in `infra/perf/pr_scoped_probes.json`. The probe includes focused tests, changed-scope coverage, and `scripts/real_model_support_hf_cache_probe.py` metrics for snapshot fallback and weight-file scan behavior.

## Implementation Plan

- Keep the existing `refs/main` resolution path unchanged.
- Add a fast pass over snapshot entry names to identify the lexicographically last entry without per-entry `is_dir()` calls.
- Verify that the selected max entry is a real directory without following symlinks.
- Fall back to the previous precise `DirEntry.is_dir(follow_symlinks=False)` scan only when the lexicographically max entry is not a directory.

## Success Metrics

- `hf_cache_elapsed_ms_mean` should improve on the registered local probe.
- `hf_cache_peak_bytes_mean` should remain stable or improve.
- Existing behavior for missing refs, non-directory entries, and no-symlink-follow semantics must be preserved by tests.

## 2026-07-24 builtin max follow-up

This follow-up keeps the same registered PR-scoped probe,
`real-model-support-hf-cache-latest-snapshot`, and narrows only the snapshot-name
selection loop when `refs/main` is unavailable. The previous fast path already
avoided sorting and avoided per-entry `is_dir()` calls, but still performed the
lexicographic max comparison in an explicit Python loop.

The slice delegates that max-name selection to the built-in `max(...,
default=None)` over the `os.scandir()` entry names. The behavior remains the
same for empty snapshot directories, non-directory lexicographic maxima,
non-symlink-follow directory checks, and precise fallback rescans. The registered
probe's primary metric for this follow-up is `hf_cache_elapsed_ms_mean`; peak
bytes and weight-scan metrics remain guardrails.
