# Event Extraction Actor Field Cache Performance Slice

## Scope

This Python-only slice targets semantic event-extraction actor field expansion in
`services/mlx-worker-python/worker/productization/event_extraction.py`.

The behavior remains unchanged: actor fields are still validated as nullable
string arrays, trimmed, deduplicated, and expanded so group aliases such as
`我们`, `双方`, and normalized variants resolve to `speaker_1` and `speaker_2`.

## Registered probe

The affected path is already covered by PR-scoped probe
`event-extraction-group-actor-alias-cache` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries covering:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `scripts/event_extraction_actor_alias_probe.py`

The probe repeatedly calls `_semantic_field_values("actor", event)` on a stable
synthetic actor list and reports `elapsed_ms_mean`, `normalize_calls_mean`,
`peak_bytes_mean`, and workload-size guardrails.

## Plan

1. Keep the existing group-alias expansion and normalization semantics.
2. Add a small raw actor-field tuple cache so repeated semantic scoring of the
   same actor list reuses normalized/expanded actor values.
3. Keep non-actor field handling on the direct normalization path.
4. Clear the new cache in focused tests and the probe so monkeypatched
   normalization counters remain deterministic.
5. Verify with focused pytest, changed-scope coverage, and the registered local
   probe on Linux before PR creation.

## Success criteria

- Focused event-extraction tests pass.
- Changed-scope coverage for the modified Python/probe/test files is at least
  95 percent.
- Local registered probe shows lower `elapsed_ms_mean` versus the `origin/main`
  baseline without behavior changes.
- PR-scoped performance CI selects and completes the registered probe.
