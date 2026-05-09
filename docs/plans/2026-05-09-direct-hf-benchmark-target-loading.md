# Direct Hugging Face Benchmark Target Loading

## Goal

Fix direct Hugging Face benchmark and evaluation target loading so text-only
Qwen 3.x MLX repositories resolve to a loadable text model instead of a VLM
target, and so worker load failures preserve their original error code and
message instead of being masked as a missing benchmark target.

## Scope

- Control-plane direct `--repo-id` benchmark, benchmark-matrix, and evaluation
  resolution.
- On-demand model load error propagation from worker load responses.
- Swift regression tests for Qwen 3.6 direct imports, local Hugging Face cache
  snapshot preference, and worker load error surfacing.

## Performance Probes And Metrics

This slice changes target resolution and error handling, not the Python
benchmark execution loop. The verification probe is a focused Swift control
plane test path that exercises:

- direct Hub card classification for Qwen 3.6 text-only repositories with
  `processor_config.json`;
- registry snapshot reuse before Hub fallback;
- worker load rejection propagation without an unnecessary benchmark request.

Success metrics:

- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests`
  passes for the touched control-plane behavior.
- `python3 scripts/swift_changed_line_coverage.py --diff-from origin/main`
  reports at least 95 percent changed-line coverage for touched Swift lines, or
  the handoff records the exact blocker if the coverage tool is unavailable.
- `git diff --check` reports no whitespace errors.

## Implementation Plan

1. Add failing control-plane tests for the Qwen 3.6 direct Hugging Face import
   and worker load rejection paths.
2. Rescan worker registry before direct Hub import and prefer existing
   Hugging Face cache snapshots matching the requested repo.
3. Extend Qwen text classification to Qwen 3.x repositories while preserving
   Gemma/PaliGemma VLM behavior.
4. Propagate worker load rejection errors from `OnDemandModelLoader` through
   benchmark, matrix, and evaluation handlers.
5. Run focused tests, changed-line coverage, and diff checks before handoff.
