# Model-Load Trust Policy

## Goal

Make local model-load remote-code trust explicit, model-scoped, route-aware, reload-aware, and
operator-visible. Melix must default local custom loader execution to off, allow it only through a
per-model opt-in, and expose receipts that explain why a load was allowed, refused, or waiting for a
reload.

## Governing Issue

- GitHub issue: #74

## Current Foundation

Melix already has the control points needed for this policy:

- `ModelSpec` carries typed capability class, worker route class, settings, `ext`, features, and
  `runtime_mode`.
- `ModelSummary` exposes per-model settings, route metadata, residency, supported modalities, and
  supported tasks.
- `SetModelPolicy` updates model-scoped settings through the control plane.
- `OnDemandModelLoader` resolves the model, route, and worker `LoadModelRequest` before dispatch.
- The Python `WorkerModelRegistry` is the common load gate before route-specific runtime loaders.

## Contract

### Safe Default

Remote/custom model code execution is disabled unless the target model has an explicit model-scoped
trust opt-in.

### Per-Model Scope

Trust belongs to the concrete model entry selected for load. It must not be inherited from profiles,
templates, server-session defaults, benchmark or evaluation templates, or global unsafe toggles.

### Route Parity

The control plane resolves the requested policy before dispatch. The worker records the effective
policy for every load attempt:

- Swift text route reports `not_applicable` unless a future Swift path can invoke custom code.
- Python text compatibility routes enforce the policy before trust-sensitive MLX loader calls.
- VLM/multimodal routes enforce the same default-off policy before `mlx-vlm` loader calls.
- Embedding, rerank, deterministic, audio, image, and other non-custom-code routes still emit a
  receipt with `not_applicable` when appropriate.
- Model-operation smoke loads reuse the same worker registry policy.

### Reload Awareness

Changing the stored trust setting on an already-loaded model does not mutate the active engine in
place. Melix records whether the active runtime policy differs from the requested model setting and
whether unload/reload is required.

## Protocol Shape

Use typed protocol fields for the stable contract:

- `ModelLoadTrustMode`
  - `MODEL_LOAD_TRUST_MODE_UNSPECIFIED`
  - `MODEL_LOAD_TRUST_DEFAULT_SAFE`
  - `MODEL_LOAD_TRUST_TRUST_REMOTE_CODE`
  - `MODEL_LOAD_TRUST_NOT_APPLICABLE`
- `ModelLoadTrustPolicy`
  - `requested_mode`
  - `effective_mode`
  - `policy_source`
  - `custom_loader_required`
  - `custom_loader_detection_source`
  - `block_reason`
  - `requires_reload_for_trust_change`
  - `route_class`
  - `loader_family`
- `ModelSettings.load_trust_mode`
- `LoadModelRequest.load_trust`
- `LoadModelResponse.load_trust`
- `ModelSummary.load_trust`

Keep `ext` only for transition, compatibility, and low-level diagnostics. Stable operator surfaces
should read typed fields.

## Implementation Slices

### Slice 1 - Protocol and Control Plane

- Add typed trust policy messages to worker and control-plane protobuf schemas.
- Regenerate Swift and Python protocol artifacts.
- Parse `trust_remote_code`, `load_trust_mode`, and `model_load_trust_mode` in `SetModelPolicy`.
- Resolve default-safe policy in `OnDemandModelLoader` before worker dispatch.
- Record load trust receipts and reload-required state in `ModelSummary`.
- Add focused Swift tests for default safe policy, explicit opt-in, clear/default behavior, and
  settings changes on loaded models.

### Slice 2 - Worker Enforcement

- Add a worker-side trust policy helper shared by runtime load paths.
- Detect obvious custom-loader metadata from model `config.json`, including `auto_map`, before
  trust-sensitive Python loader calls.
- Refuse custom-loader loads by default with typed `ErrorStatus` details.
- Pass trust-sensitive kwargs only when the effective policy explicitly allows remote code.
- Emit `not_applicable` receipts for routes that cannot execute custom code.
- Publish worker trust-policy resolution latency and blocked-load count through `RuntimeStats`
  and the control-plane metrics store.
- Add focused Python tests for blocked text/VLM custom loaders, explicit opt-in, and
  non-applicable deterministic routes.

### Slice 3 - Operator Surfaces and Evidence

- Surface trust receipts in model list/detail JSON and concise text output.
- Document the operator workflow to enable trust for one model and reload it intentionally.
- Include trust fields in diagnostics or run evidence where the existing artifact path already
  records model load state.
- Add profile/template/server-default regression coverage proving trust does not propagate
  implicitly.

## Metrics and Performance Probes

This policy is not intended to change inference throughput. The changed path is model-load
resolution and metadata inspection.

Metrics:

- `control_plane.model_load_trust_resolution_ms`
- `worker.model_load_trust_policy_resolution_ms`
- `worker.model_load_trust_blocked_count`

Performance target:

- Trust policy resolution must stay below 1 ms p95 in deterministic unit/probe fixtures.
- Config metadata inspection must avoid loading model weights and must read only existing
  lightweight metadata files.

If a slice only adds protocol or deterministic policy plumbing, runtime throughput metrics may be
reported as `N/A` with this plan as the reason.

## Verification

Focused commands for the complete implementation:

```bash
make proto
swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|OnDemandModelLoaderTests|ModelCatalogTests'
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py -q
```

Coverage commands must include the changed Swift and Python files and report at least 95 percent
for the touched scope before the implementation PR merges.

## Acceptance

- Local model loads do not execute custom loader code unless the selected model has an explicit
  model-scoped opt-in.
- Blocked custom-loader loads include requested mode, effective mode, route, detection source, and
  typed block reason.
- Every supported route emits a trust receipt or explicit `not_applicable`.
- Changing trust on a loaded model records `requires_reload_for_trust_change`.
- Profiles, templates, server sessions, benchmark/evaluation configs, and derived models do not
  silently propagate trust.
- PR evidence includes coverage and metrics, or explicit `N/A` with this plan as the reason.
