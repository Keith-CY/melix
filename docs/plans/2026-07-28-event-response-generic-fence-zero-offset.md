# Event extraction response JSON fence zero-offset fast paths

## Scope

This Python-only performance series targets `services/mlx-worker-python/worker/productization/event_extraction.py`, specifically `_parse_response_json()` when model output starts at byte zero with fenced JSON blocks.

The affected path is covered by the registered PR-scoped probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries, and the checked-in probe emits `generic_fence_elapsed_ms_mean` and `generic_fence_peak_bytes_mean` for this exact generic-fence workload.

## Planned Changes

Completed previous slice: keep parser semantics unchanged while adding a zero-offset triple-backtick branch before the leading-whitespace scan for generic fences such as ` ```javascript\n{...}\n``` `.

Current slice: keep parser semantics unchanged while replacing the zero-offset canonical ` ```json\n ` prefix check with direct character comparisons. This avoids a `str.startswith()` method call on the registered JSON-fence hot path while preserving the existing leading-whitespace fenced fallback.

## Verification Plan

1. Add a focused regression test proving the zero-offset canonical JSON fence path does not call `str.startswith()`.
2. Run the registered focused test command for `event-extraction-response-json-fence-trim`.
3. Run the registered changed-scope coverage command for the same probe.
4. Run the registered probe locally on Linux before and after the change, comparing `elapsed_ms_mean` and guard metrics.

## Metrics

Expected direction for this slice: `json_fence_startswith_calls_mean` drops to zero for zero-offset canonical JSON-fenced responses, with `elapsed_ms_mean` monitored as the timing guard. Generic fence, direct-object, and leading-whitespace paths should remain behaviorally equivalent and are still included in the registered probe output.
