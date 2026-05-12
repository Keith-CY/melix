# Deterministic VLM Completion Token Scan

## Scope

This Python-only performance slice is limited to deterministic VLM completion-token accounting in `services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py`.

The current deterministic VLM paths count completion tokens with `response_text.split()`. For long synthetic image/video descriptions this materializes a transient list even though the runtime only needs the token count. The slice replaces that list allocation with a whitespace scanner that preserves `str.split(None)` token-boundary semantics.

## Probe Registration

The affected path is covered by the registered PR-scoped probe `deterministic-vlm-completion-token-scan` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` for focused deterministic VLM behavior and probe-selection tests.
- `coverage_command` for changed-scope coverage on the runtime, focused tests, registry test, and probe script.
- `probe_command` using `command_json` to measure a synthetic long-response completion-token workload.

Metrics:

- `split_calls_mean` (`lower_is_better`, target `0`) verifies the split-list path is removed.
- `elapsed_ms_mean` (`lower_is_better`) tracks the repeated counting workload.
- `peak_bytes_mean` (`lower_is_better`) tracks transient allocation pressure.
- `completion_tokens` is informational parity evidence.

## Verification Plan

1. Run the focused pytest command from the registered probe locally on Linux.
2. Run the changed-scope coverage command from the registered probe locally on Linux and require at least 95% changed-scope coverage.
3. Run the registered probe locally against `origin/main` and this branch for before/after metrics.
4. Use the PR-scoped performance workflow as the merge gate for registered CI probe validation.

## Acceptance Criteria

- Deterministic VLM prefill and direct generation completion-token counts match `str.split(None)` semantics.
- The focused regression proves the completion-token path does not call `split()` on a tracking string.
- The registered local probe shows `split_calls_mean` dropping to `0` on head and no behavior-parity failures.
- PR-scoped CI completes successfully before merge.
