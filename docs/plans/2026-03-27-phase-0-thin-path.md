# Melix Phase 0 + Thin Path Status Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans when implementing the remaining tasks in this plan.

**Goal:** Finish the first executable Melix slice: a local control plane, a Python worker, one streamed chat path, and a minimal operator-facing menu bar shell.

**Architecture:** The phase-0 slice is intentionally narrow. The Swift control plane owns HTTP, SSE, XPC, request translation, admission, and model state. The Python worker owns runtime execution, token streaming, and cancellation. Deterministic execution remains the stable integration path, while `auto` mode is now the real MLX path.

**Tech Stack:** Swift Package Manager, Swift Concurrency, Swift Protobuf-generated types, Python 3.12+, `uv`, `grpcio`, `protobuf`, `mlx`, `mlx-lm`, Unix Domain Sockets, XCTest, `pytest`.

---

## Summary

This document is the current phase-0 source of truth, not a speculative implementation outline.

Current status:

- `Task 1` through `Task 6` are complete in local `main`.
- The thin path now supports generated protocol artifacts, a Swift control plane, a Python worker, SSE chat streaming, abort bridging, a live worker transport, real MLX token streaming in worker `auto` mode, a menu bar operator shell, and a reproducible local operator workflow.
- Phase 0 is closed. Follow-on work now belongs to the next implementation phase rather than this plan.

Detailed historical execution notes remain in:

- `docs/plans/2026-03-27-task-4-http-gateway.md`
- `docs/plans/2026-03-27-task-4b-live-worker-transport.md`
- `docs/plans/2026-03-27-task-4c-mlx-streaming.md`

## Completed Milestones

### Task 1: Repository bootstrap and protocol generation baseline

Completed outcome:

- root workspace bootstrap exists
- `make bootstrap`, `make proto`, `make swift-test`, `make py-test`, and `make integration-test` are defined
- protocol schemas generate versioned Swift and Python artifacts

Key caveat:

- protocol schemas remain the editable source of truth; generated outputs must still be regenerated on schema changes

### Task 2: Control plane XPC and in-memory state skeleton

Completed outcome:

- the control plane exposes `handshake`, `execute`, `subscribe`, and `unsubscribe`
- server snapshots, model list/load/unload, metrics placeholders, and typed event fanout exist
- model state and subscription sequencing are test-covered

Key caveat:

- this XPC surface is still phase-0 scoped and intentionally limited to operator workflows, not rich settings or history flows

### Task 3: Worker runtime slice

Completed outcome:

- the Python worker exposes `RuntimeService` and `InferenceService`
- `Generate` and `Abort` are functional
- unsupported RPC surfaces return explicit structured `unimplemented` responses

Key caveat:

- `Prefill`, `Decode`, cache mutation, maintenance workflows, and multimodal execution remain out of scope for phase 0

### Task 4: HTTP gateway, SSE streaming, and abort bridge

Completed outcome:

- `POST /v1/chat/completions` and `GET /v1/models` exist
- chat requests are translated into worker generation requests
- SSE emits deltas, usage, completion, and done markers
- cancel requests bridge to worker `Abort`

Key caveat:

- phase 0 still exposes only the thin HTTP surface; `responses`, `messages`, embeddings, rerank, image, and audio endpoints remain deferred

### Task 4B: Live worker transport

Completed outcome:

- the control plane no longer depends on the null worker path for live requests
- a Python bridge helper carries real worker protobuf traffic over UDS
- the control plane can preload the development text model when the worker is reachable

Key caveat:

- the bridge transport is a phase-0 implementation detail and not the final permanent transport decision

### Task 4C: Real MLX token streaming

Completed outcome:

- worker `auto` backend mode uses real `mlx_lm.load(...)` and `mlx_lm.stream_generate(...)`
- prompt rendering uses tokenizer chat templates when available
- runtime metadata now drives finish reason and usage reporting
- deterministic mode remains the stable integration fallback

Key caveat:

- true MLX smoke verification requires `MELIX_DEV_TEXT_MODEL_PATH`; if the model source is missing or invalid, `auto` mode must fail explicitly

### Task 5: Minimal menu bar shell

Completed outcome:

- the menu bar target is now a real operator shell instead of a placeholder executable
- launch performs handshake hydration and subscribes to control-plane state changes
- the shell renders server state and development-model state and exposes load/unload actions
- menu bar tests now cover launcher wiring, state hydration, model actions, selector routing, and renderer behavior

Key caveat:

- the shell remains intentionally read-mostly and phase-0 focused; settings, cache inspection, and request history stay out of scope

### Task 6: Integration and developer workflow completion

Completed outcome:

- `make integration-test` now covers streamed chat, abort behavior, and `/v1/models` as separate cases
- `scripts/dev_up.sh` and `scripts/dev_down.sh` provide a reproducible local operator loop
- README documents the deterministic default path and the optional real-MLX smoke path gated by `MELIX_DEV_TEXT_MODEL_PATH`
- operator smoke has been verified with `dev_up`, `curl /v1/models`, and `dev_down`

Key caveat:

- the optional real-MLX smoke path still depends on an explicitly configured model source and does not yet produce benchmark-grade latency reporting

## Acceptance Criteria

Phase-0 status as of this plan:

- `make proto` succeeds from a clean checkout: complete
- the Swift daemon and Python worker build and test in isolation: complete
- one configured model can be loaded through the control plane: complete
- `POST /v1/chat/completions` streams content through SSE: complete
- `Abort` stops an active generation and produces terminal state: complete
- `GET /v1/models` reflects current model state: complete
- unsupported worker RPC surfaces return explicit `unimplemented` responses: complete
- real MLX generation support exists in worker `auto` mode: complete
- the menu bar shell shows runtime state through XPC: complete
- the integration/developer workflow is broader than a single smoke path: complete

Phase 0 is complete.

## Verification Baseline

Current baseline verification commands:

```bash
make swift-test
make py-test
make integration-test
make coverage
```

Current measured baseline:

- Swift control plane coverage: `95.50%`
- Python worker coverage: `97%`
- macOS menu bar coverage: `97.93%`
- deterministic live integration suite: `3` passing tests
- local operator smoke via `dev_up` / `curl /v1/models` / `dev_down`: passing
- MLX runtime latency and throughput metrics: `N/A` until a real `MELIX_DEV_TEXT_MODEL_PATH` is configured for smoke verification

## Defaults and Assumptions

- This phase targets macOS on Apple Silicon only.
- `deterministic` remains the default integration and repeatability path.
- `auto` is the real MLX runtime path and must fail explicitly if MLX or the configured model source is unavailable.
- `MELIX_DEV_TEXT_MODEL_PATH` overrides the development text model source for real MLX runs.
- No additional public HTTP endpoints are in scope for phase 0.
- Real `Prefill` and `Decode`, queue upgrades, session graph state, L2 cache persistence, snapshots, embeddings, rerank, and multimodal execution remain deferred beyond phase 0.
