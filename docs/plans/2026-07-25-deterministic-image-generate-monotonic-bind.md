# Deterministic image generate invariant binding performance slice

## Scope

This Python-only performance slice is limited to
`DeterministicImageGenerationRuntime.generate_images(...)` in
`services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`.

## Probe registration

The affected runtime path is covered by the existing registered PR-scoped probe
`deterministic-image-output-byte-accounting` in
`infra/perf/pr_scoped_probes.json`. That registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` values and watches the
runtime, image-runtime tests, PR-scoped performance tests, and
`scripts/deterministic_image_output_bytes_probe.py`.

## Optimization

Bind generate-path invariants once per image-generation call:

- reuse a local `time.monotonic` callable for artifact-publish timing and final
  job-latency accounting;
- build the constant generated-image payload prefix once per request, then append
  only the per-variant suffix inside the loop.

This avoids repeated module attribute lookups and repeated formatting of
request-invariant payload fields while preserving all observable request,
artifact, and probe fields.

## Verification plan

- Run focused image-runtime tests, including a regression guard that checks
  generated payload parity and counts the `time.monotonic` module lookup on the
  generate path.
- Run changed-scope coverage for the runtime, image tests, PR-scoped performance
  tests, and the registered probe script.
- Run the registered `deterministic-image-output-byte-accounting` probe locally
  on Linux and compare against the pre-change baseline.

## Validation boundary

This slice is Python-only and locally validated on Linux. No Swift runtime effect
is claimed.
