# Event extraction generic fence zero-offset fast path

## Scope

This Python-only performance slice targets `services/mlx-worker-python/worker/productization/event_extraction.py`, specifically `_parse_response_json()` when model output starts at byte zero with a generic fenced JSON block such as ` ```javascript\n{...}\n``` `.

The affected path is covered by the registered PR-scoped probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries, and the checked-in probe emits `generic_fence_elapsed_ms_mean` and `generic_fence_peak_bytes_mean` for this exact generic-fence workload.

## Planned Change

Keep parser semantics unchanged while adding a zero-offset triple-backtick branch before the leading-whitespace scan. The canonical ` ```json\n ` fast path remains first; the new branch only handles generic fences that already begin at offset zero and decodes from the first newline after the fence marker.

## Verification Plan

1. Add a focused regression test proving the zero-offset generic fence path does not call `_skip_json_whitespace()`.
2. Run the registered focused test command for `event-extraction-response-json-fence-trim`.
3. Run the registered changed-scope coverage command for the same probe.
4. Run the registered probe locally on Linux before and after the change, comparing `generic_fence_elapsed_ms_mean` and guard metrics.

## Metrics

Expected direction: lower `generic_fence_elapsed_ms_mean` for zero-offset generic fenced responses. Canonical JSON-fence, direct-object, and leading-whitespace paths should remain behaviorally equivalent and are still included in the registered probe output.
