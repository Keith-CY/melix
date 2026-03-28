# P5-M5 Control-Plane Endpoints and Workflows

**Goal:** Expose the first non-text control-plane API surfaces for embeddings and rerank, wire route selection through the capability-aware worker registry, surface operator-ready health and cache endpoints, and bridge the first model-operations worker RPCs into the control plane without disturbing the text hot path.

**Non-goals:**

- No native desktop `Models` or `Tools` UI in this milestone.
- No mixed-load scheduling policy changes beyond preserving route separation.
- No new training, image, audio, or multimodal behavior.
- No silent fallback from typed embedding or rerank routes into the Swift text worker.

## Context

- Phase plan: `docs/plans/2026-03-27-phase-5-embeddings-rerank.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Relevant code paths:
  - `services/control-plane-swift/Sources/HTTPGateway`
  - `services/control-plane-swift/Sources/WorkerClient`
  - `services/control-plane-swift/Sources/Bootstrap`
  - `services/control-plane-swift/Sources/Snapshots`
  - `services/mlx-worker-python/worker/control_plane_bridge.py`
  - `tests/integration`

## Assumptions

- Embedding, rerank, and model-operations requests continue to execute in the Python worker plane.
- The control plane remains responsible for route selection, HTTP translation, health projection, and cache or metrics read models.
- `GET /v1/cache/stats` should be backed by the already-hydrated control-plane cache snapshot rather than by ad-hoc direct worker calls from the handler.
- `GET /health` should report route readiness and model visibility, not deep benchmark or doctor output.

## Performance Probes

- `embeddings.request_latency_ms`
- `embeddings.items_per_second`
- `rerank.request_latency_ms`
- `rerank.documents_per_second`
- `operator.health_latency_ms`
- `operator.cache_stats_latency_ms`

## Work Plan

### Task 1: Add control-plane bridge support for non-text worker RPCs

- Extend the Python bridge command vocabulary for `embed`, `rerank`, `get-model-info`, and `convert-model`.
- Add Swift worker-client protocols for non-text inference and model-operations bridges.
- Keep typed error translation aligned with the existing bridge behavior.

### Task 2: Add HTTP endpoint translation and route selection

- Add `POST /v1/embeddings` and `POST /v1/rerank` to the control-plane HTTP handler.
- Route requests by model capability class through `WorkerRegistry`.
- Return stable JSON payloads and coherent HTTP error mapping for unavailable models, invalid routes, and worker-side structured failures.

### Task 3: Add operator surfaces backed by control-plane state

- Add `GET /health`.
- Add `GET /v1/cache/stats`.
- Populate both from existing control-plane state, metrics, and route readiness rather than from new side channels.

### Task 4: Make the live stack usable by default

- Seed the control-plane bootstrap with Phase 5 model entries.
- Preload development embedding, rerank, and model-operations handles through the Python worker.
- Preserve the existing text bootstrap path.

### Task 5: Add verification and metrics evidence

- Add Swift tests for endpoint translation, route usage, health payloads, and cache payloads.
- Add bridge tests for the new Python helper commands.
- Add integration coverage for `/v1/embeddings` and `/v1/rerank`.
- Add a small Phase 5 metrics script for endpoint latency and throughput.

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
```

Metrics command:

```bash
make phase5-metrics
```

## Acceptance

- `POST /v1/embeddings` returns stable JSON and uses the embedding route.
- `POST /v1/rerank` returns stable JSON and uses the rerank route.
- `GET /health` and `GET /v1/cache/stats` are backed by real control-plane state.
- Phase 5 development models are preloaded in the live stack.
- Touched scope verification passes and the metrics report contains non-`N/A` endpoint timings.

## Rollback

If the new endpoints or bridge commands are unstable, revert the handler and bridge additions as one slice while keeping the Phase 5 worker runtimes intact.
