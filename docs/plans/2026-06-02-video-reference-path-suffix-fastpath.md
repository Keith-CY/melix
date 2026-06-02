# Video reference path suffix fast path

## Goal

Avoid the temporary string/list allocations from `path.rstrip("/").rsplit("/", 1)` while parsing video URI path metadata. `_parse_video_reference()` runs on the video preprocessing hot path and only needs the final path segment plus suffix, so this slice scans the original path string with indexes and slices once for the final path name.

## Scope

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/tests/test_video_preprocessing.py`
- `docs/plans/2026-06-02-video-reference-path-suffix-fastpath.md`

## Registered probe

The affected path is covered by the existing PR-scoped registered probe `video-preprocessing-uri-byte-length-reuse` in `infra/perf/pr_scoped_probes.json`. The entry has focused `test_command`, `coverage_command`, and `probe_command` values and watches `worker/runtime/video_preprocessing.py`, the focused tests, and `scripts/video_preprocessing_uri_probe.py`.

## Verification plan

Run the registered probe commands locally on Linux:

1. Focused pytest for video preprocessing and probe selection.
2. Changed-scope coverage using the registered `coverage_command`.
3. Registered probe comparison from an `origin/main` baseline worktree to the head worktree.
4. `git diff --check`.

## Success metric

The registered probe should preserve behavior, keep parse calls and byte-length reads at one per prepared URI video call, and reduce mean elapsed time by avoiding path `rstrip`/`rsplit` allocations in the URI parse helper.
