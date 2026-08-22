# Deterministic image artifact metadata local binding

## Scope

This Python-only performance slice is limited to local binding of deterministic image runtime artifact metadata construction constants in the hot loops in `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`.

## Registered performance probe

The affected runtime path is already covered by the registered PR-scoped probe `deterministic-image-output-byte-accounting` in `infra/perf/pr_scoped_probes.json`. That probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports:

- `elapsed_ms_mean` for deterministic generate/edit output-byte accounting workloads.
- `output_byte_scan_calls_mean` to ensure output byte accounting remains single-pass.

This slice adds a regression test proving generated artifact metadata class and generated-role constant lookup are bound once per generate/edit loop, then uses the existing registered probe for local Linux and CI performance evidence.

## Implementation plan

1. Add a focused test around deterministic image generate/edit artifact metadata type and generated-role lookup count.
2. Bind `common_pb2.ImageArtifactMetadata` and `common_pb2.IMAGE_ARTIFACT_GENERATED` once per generate/edit call before the generated artifact loop.
3. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux.
4. Use the PR-scoped performance GitHub Actions report as the merge gate.

## Acceptance criteria

- Focused deterministic image runtime tests pass.
- Changed-scope coverage for touched Python files remains at least 95%.
- The registered `deterministic-image-output-byte-accounting` probe shows no in-scope regression and preferably improves `elapsed_ms_mean`.
- CI, including the PR-scoped performance workflow, is green before merge.
