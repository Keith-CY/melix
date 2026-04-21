# LoRA Module 1 — Real adapter-backed runtime (issue #12)

## Context

Issue [#12](https://github.com/Keith-CY/melix/issues/12) implements Module 1 from `docs/plans/2026-04-16-lora-capability-modules-and-commit-plan.md`: make `adapter_backed_runtime` a real serving path rather than a metadata-only activation shape.

The mechanics already work end-to-end today — `AutoMLXBackend.load_model()` passes `adapter_path` to `mlx_lm.load()` when the ModelSpec carries `ext["melix.activation_mode"]="adapter_backed_runtime"`, and the Phase 8 real-small-model acceptance bundle (`test_phase8_acceptance_bundle_real_small_model_profile_closes_real_lora_chain`) already runs the full chain through an adapter-backed derived model. What's missing:

1. **Typed contract.** The activation mode is stringly typed — `ext["melix.activation_mode"]` parsed in every consumer. No proto-level signal for "this model serves as base + adapter."
2. **Runtime visibility.** `ModelSummary` has no field distinguishing fused from adapter-backed. CLI `models list` and `models show` render them identically.
3. **Focused regression coverage.** No unit/integration test isolates "load adapter-backed derived model → generate tokens" outside the heavyweight acceptance-bundle flow.

Module 1 closes all three gaps across one PR with three commit slices, per the LoRA capability plan's convention ("one PR per module or tightly related pair of commit slices").

## Scope

**In:**

- **Slice 1.1** — Proto-level `RuntimeMode` enum on `ModelSpec` + typed `AdapterBackedLoadContract` dataclass in the runtime backend. Proto enum is the authoritative signal; `ext["melix.activation_mode"]` stays readable for backward compat. `melix.derived_text_model.v1` manifest schema is unchanged.
- **Slice 1.2** — Maintenance core sets `runtime_mode` on registered specs for adapter-backed derived models; new env-gated integration test `test_adapter_backed_runtime_integration.py` that trains a tiny adapter, activates adapter-backed, loads, generates tokens, and asserts the output differs from a base-only load.
- **Slice 1.3** — `RuntimeMode runtime_mode` field on `ModelSummary` (control plane proto); `job_registry` snapshot exposes it; `ControlPlaneService` populates it; CLI `models list` adds a runtime column, `models show` gains a runtime-mode detail section. Tests in Python, Swift control plane, and Swift CLI.

**Out:**

- DoRA / preference tuning / CPT (Module 4).
- Evaluation compare adapter targets (Module 2).
- Any change to the fused derived model load path.
- `upload_receipt_pipeline` / publish (Module 5).

## Design

### Proto additions

```proto
// packages/protocol/schema/worker/v1/common.proto
enum RuntimeMode {
  RUNTIME_MODE_UNSPECIFIED = 0;
  RUNTIME_MODE_FUSED_DERIVED_MODEL = 1;
  RUNTIME_MODE_ADAPTER_BACKED = 2;
}

message ModelSpec {
  // ... existing fields 1..14 ...
  RuntimeMode runtime_mode = 15;
}

// packages/protocol/schema/controlplane/v1/control_plane.proto
message ModelSummary {
  // ... existing fields 1..16 ...
  worker.v1.RuntimeMode runtime_mode = 17;
}
```

Both additive; enum 0 = UNSPECIFIED; existing payloads default to it and the backend falls back to ext-string parsing when the proto enum is unspecified.

### Typed load contract

```python
# services/mlx-worker-python/worker/runtime/mlx_text_runtime.py
@dataclass(frozen=True)
class AdapterBackedLoadContract:
    base_model_path: str
    adapter_manifest_path: str
    adapter_weights_path: str
    adapter_dir: str
    adapter_set_hash: str
    derived_from_model_id: str
```

`_resolve_adapter_backed_metadata()` returns an `AdapterBackedLoadContract | None`. Prefers the new proto enum; falls back to `ext["melix.activation_mode"]` only when `runtime_mode == RUNTIME_MODE_UNSPECIFIED`.

### Integration seam

- `adapter_activation_pipeline.py` sets `runtime_mode = RUNTIME_MODE_ADAPTER_BACKED` (or `RUNTIME_MODE_FUSED_DERIVED_MODEL`) on the registered ModelSpec.
- `maintenance_core.py` preserves `runtime_mode` through the catalog registration path.
- `AutoMLXBackend.load_model()` branches on `runtime_mode` first; only uses ext-string as a compatibility fallback.

### Integration test (env-gated)

`services/mlx-worker-python/tests/test_adapter_backed_runtime_integration.py`:

- Gates: `MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1` + `MELIX_PHASE8_REAL_SMALL_MODEL_PATH=<snapshot>`.
- Skips by default; CI never runs.
- Steps: train tiny LoRA (rank=4, 2 samples, 2 steps) → activate adapter-backed → load derived model → `generate_tokens()` on short prompt → assert non-empty stream, `runtime_mode == RUNTIME_MODE_ADAPTER_BACKED`, and tokens differ from base-only load for the same prompt.

## Critical files

```
packages/protocol/schema/worker/v1/common.proto                                  (+enum + field)
packages/protocol/schema/controlplane/v1/control_plane.proto                     (+field)
services/mlx-worker-python/worker/runtime/mlx_text_runtime.py                    (~60 lines)
services/mlx-worker-python/worker/model_ops/adapter_activation_pipeline.py       (~10 lines)
services/mlx-worker-python/worker/engine/maintenance_core.py                     (~10 lines)
services/mlx-worker-python/worker/model_ops/job_registry.py                      (~10 lines)
services/mlx-worker-python/tests/test_mlx_backend.py                             (~80 lines)
services/mlx-worker-python/tests/test_lora_model_ops_unit.py                     (~50 lines)
services/mlx-worker-python/tests/test_lora_model_ops.py                          (~30 lines)
services/mlx-worker-python/tests/test_adapter_backed_runtime_integration.py      (new, ~180 lines)
services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift        (~15 lines)
services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift (~40 lines)
Sources/MelixCLICore/MelixCLI.swift                                              (~40 lines)
Tests/MelixCLITests/MelixCLIRunnerTests.swift                                    (~60 lines)
```

Regenerated via `make proto`: `packages/protocol/python/**`, `packages/protocol/swift/**`, `packages/protocol/descriptors/**`.

## Verification

1. `make proto` + `make proto-check` — regenerated artifacts committed; no drift.
2. `make py-test` — all existing tests stay green; new hermetic unit tests pass; env-gated integration test skips by default.
3. Locally: `MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1 MELIX_PHASE8_REAL_SMALL_MODEL_PATH=<snapshot> pytest services/mlx-worker-python/tests/test_adapter_backed_runtime_integration.py -v` — passes.
4. `make swift-test` — green; new ControlPlane + CLI tests pass.
5. `MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1 … make phase8-real-e2e` — unchanged; Module 1 is additive.

## Risks

- **Proto wire compat** — additive only. Enum 0 default + ext-string fallback keeps every legacy caller working.
- **Backward compat on ext string** — readers prefer the proto enum when non-zero; ext string wins when the enum is unspecified. Existing tests that set `ext["melix.activation_mode"]` keep passing.
- **Maintenance core drift** — the catalog registration path builds ModelSpec from manifest fields. If it misses `runtime_mode`, downstream consumers see `UNSPECIFIED`. Integration test + a targeted unit test pin this.
- **CLI column width** — `models list` is already wide. If adding a runtime column causes wrap, collapse kind+runtime (e.g. `text/adapter`). Validated in the list-output test.
