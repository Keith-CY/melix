# Multimodal File URI Filename Fast Path

## Status

Accepted for one PR-scoped performance slice on 2026-08-25.

## Scope

This Python-only slice is limited to `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`, specifically the unescaped `file:///...` image URI fast path in `_parse_image_reference()`.

## Optimization

The local file URI fast path already avoids `urlparse()` when the URI has no percent escapes. This slice also derives the filename and extension directly from the decoded path string instead of asking the newly created `Path` object for `.name` and `.suffix`. The `Path` object is still created for the downstream existence/read path, and behavior remains equivalent for normal local image filenames used by the vision request path.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `multimodal-preprocessing-local-uri-parse-elision` in `infra/perf/pr_scoped_probes.json`.

Focused validation uses:

- `test_command`: vision runtime URI/preprocessing tests plus PR-scoped probe selection/registry tests.
- `coverage_command`: focused coverage for `multimodal_preprocessing.py`, vision runtime tests, PR-scoped performance tests, and `scripts/multimodal_preprocessing_uri_probe.py`.
- `probe_command`: `scripts/multimodal_preprocessing_uri_probe.py` with JSON metrics including `elapsed_ms_mean`, `urlparse_calls_mean`, and `read_bytes_calls_mean`.

## Success Criteria

- Focused tests pass.
- Changed-scope coverage is at least 95%.
- The registered probe shows lower `elapsed_ms_mean` on the changed implementation compared with `origin/main` under the same local Linux workload.
- GitHub Actions PR-scoped performance completes successfully before merge.