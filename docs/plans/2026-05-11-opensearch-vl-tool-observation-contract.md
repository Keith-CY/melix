# OpenSearch-VL Tool Observation Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the next unified tool runtime contract slice for the OpenSearch-VL alignment track: a deterministic Python worker observation contract for sanitized tool outputs shared by training replay, rollout, benchmark, and evaluation paths.

**Architecture:** The Python worker runtime owns observation normalization because tool execution outputs enter the system before they are persisted into agentic traces, benchmark artifacts, or evaluation evidence. This slice defines the contract boundary only: redaction, UTF-8 byte limits, timeout status metadata, deterministic replay fingerprints, and metrics. It does not implement concrete tool adapters or route existing evaluation jobs through those tools.

**Tech Stack:** Python 3.12, dataclasses, hashlib, deterministic JSON encoding, `pytest`.

---

## Scope

- Covers GitHub issue #677 under direction #674 / milestone #675.
- Defines a worker runtime helper for converting raw tool observation payloads into sanitized records.
- Applies configured exact redaction terms across nested observation strings.
- Enforces UTF-8 byte limits without producing invalid text.
- Normalizes explicit status values for completed, timeout, and failed observations.
- Emits deterministic replay metadata and a stable fingerprint over the sanitized payload and call identity.
- Updates the architecture spec with the observation contract boundary.
- Does not implement concrete adapters, network search, browser visits, Python execution, or evaluation routing.

## Files

- Create: `services/mlx-worker-python/worker/runtime/tool_observation.py`
- Create: `services/mlx-worker-python/tests/test_tool_observation.py`
- Modify: `docs/architecture-spec.md`
- Create: `docs/plans/2026-05-11-opensearch-vl-tool-observation-contract.md`

## Metrics And Probes

- `tool_observation.record_count`: number of normalized observation records emitted.
- `tool_observation.redacted_value_count`: number of configured term replacements applied.
- `tool_observation.truncated_count`: number of records where a text field exceeded the byte limit.
- `tool_observation.timeout_count`: number of records normalized with timeout status.
- `tool_observation.emitted_bytes`: UTF-8 bytes emitted after redaction and truncation.
- Success metric: focused observation tests pass with changed-line coverage at or above 95 percent for the touched Python module.

## Implementation Tasks

### Task 1: Plan And Red Tests

- [x] Add this plan under `docs/plans/`.
- [x] Add focused tests for nested exact redaction without leaking configured terms.
- [x] Add tests that byte limits truncate UTF-8 safely and record emitted/original bytes.
- [x] Add tests that timeout status records explicit timeout metadata.
- [x] Add tests that replay fingerprints are stable for identical sanitized records and change when payloads differ.
- [x] Add tests that invalid policies and statuses are rejected.
- [x] Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_tool_observation.py
```

Expected: fail until `worker.runtime.tool_observation` exists.

### Task 2: Observation Contract Implementation

- [x] Add frozen dataclasses for observation policy, record metrics, replay metadata, and normalized records.
- [x] Validate non-empty tool name, tool call id, observation kind, schema version, and supported statuses.
- [x] Recursively sanitize dictionary, list, tuple, scalar, and text observation payloads.
- [x] Apply exact redaction terms before byte limiting so leaked values never influence emitted text.
- [x] Enforce per-string UTF-8 byte limits without splitting multi-byte characters.
- [x] Emit deterministic replay metadata with schema version, policy hash, payload hash, and fingerprint.
- [x] Expose a compact agentic-trace observation payload helper for downstream persistence.

### Task 3: Documentation And Verification

- [x] Update `docs/architecture-spec.md` with the worker-owned observation contract boundary.
- [x] Run the focused pytest command from Task 1 and confirm it passes.
- [x] Run changed-line coverage for `worker/runtime/tool_observation.py`.
- [x] Run `git diff --check`.
- [x] Record metrics and verification output in PR evidence.

## Success Criteria

- The Python worker can normalize a raw tool observation into a deterministic sanitized record.
- Configured redaction terms do not appear in emitted nested observation text.
- UTF-8 byte limits preserve valid text and expose truncation metrics.
- Timeout status is explicit and includes timeout metadata.
- Replay fingerprints are stable across identical sanitized observations and change with sanitized payload changes.
- Focused tests pass.
- Changed-line coverage for `tool_observation.py` is at least 95 percent.
- `git diff --check` passes.
