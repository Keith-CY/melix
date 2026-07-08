# Issue 350 Serving Profile Preflight Receipt Plan

## Goal

Emit the serving capability receipt metadata from the control-plane profile
preflight path so diagnostics bundles can record the resolved serving capability
and acceleration admission contract for every locally dispatched model start.

## Scope

This slice covers the next executable issue #350 step: add a profile preflight
test matrix and wire the resulting receipt into diagnostics before adding any
new serving fast path.

In scope:

- Add `melix.serving.capability.*` metadata in the existing model acceleration
  admission path.
- Derive the metadata from already-resolved control-plane facts:
  `ModelSummary.supportedTasks`, `ModelSummary.supportedModalities`, the
  acceleration capability receipt, and the serving profile admission receipt.
- Cover the four preflight matrix rows named in the issue:
  text-only mixed-family checkpoint, media-capable checkpoint, unsupported
  acceleration flags, and known target/draft admission.
- Prove the metadata can still be consumed by the Python diagnostics writer to
  materialize `serving_capability` in `effective-config.json`.

Out of scope:

- New routing behavior, new media fast paths, or optional dependency probing.
- New protobuf fields.
- Model prefetch, model discovery, health polling, or package imports during
  diagnostics bundle writing.
- Changing existing unsupported acceleration refusal semantics.

## Architecture

`RequestCoordinator` already validates acceleration/profile admission through
`ModelCapabilityReceipts.validateAcceleration(...)` and merges
`ModelCapabilityReceipts.accelerationAuditMetadata(...)` into worker request
metadata before dispatch. This slice extends that metadata helper so the
control plane also emits the diagnostics-facing `melix.serving.capability.*`
contract from the same validated receipt.

The Python diagnostics writer already synthesizes the top-level
`serving_capability` receipt when all required namespaced fields are present.
The writer remains passive: it records metadata supplied by upstream serving
code and does not inspect models or dependencies.

## Receipt Mapping

The control plane should emit:

- `melix.serving.capability.schema_version`:
  `melix.serving_capability_receipt.v1`
- `melix.serving.capability.capabilities`: canonical request capabilities
  derived from supported tasks and modalities, such as `generate_text` and
  `generate_multimodal`.
- `melix.serving.capability.input_modalities`: stable comma-separated
  modalities admitted by the resolved model contract.
- `melix.serving.capability.output_modalities`: `text` for text and
  multimodal generation routes, and `image` for image generation or editing
  routes in this slice.
- `melix.serving.capability.acceleration_profile`: the effective admitted
  profile when available, otherwise the requested profile.
- `melix.serving.capability.requested_mode`: requested acceleration mode from
  the acceleration receipt.
- `melix.serving.capability.resolved_mode`: resolved acceleration mode from the
  acceleration receipt.
- `melix.serving.capability.optional_dependency_source`: `not_required` for
  this metadata-only slice.
- `melix.serving.capability.unsupported_reason`: the typed acceleration refusal
  reason, or `none`.
- `melix.serving.capability.ignored_flags`: unsupported or ignored flags. This
  slice records `draft_model_id` when a rejected speculative request supplied an
  invalid draft model.
- `melix.serving.capability.fallback_policy`: `fail_closed` when admission is
  rejected, otherwise `observable_fallback`.

## Verification Plan

1. Add Swift RED tests in `ModelCatalogTests` for:
   - text-only request on a VLM/mixed-family checkpoint emits `generate_text`
     and `text` capability metadata without requiring media dependencies;
   - media-capable VLM request emits `generate_text,generate_multimodal` with
     `text,image,video` input modalities;
   - image-generation style model metadata emits `image_generate,image_edit`
     with `text,image` input modalities and `image` output modality;
   - unsupported draft-model request is refused before dispatch and the
     metadata helper records `draft_model_not_allowed`, `fail_closed`, and
     `ignored_flags=draft_model_id`;
   - known target/draft admission emits `requested_mode=speculative_decode`,
     `resolved_mode=speculative_decode`, and the admitted profile.
2. Extend `RequestCoordinatorTests` to prove admitted request dispatch includes
   the namespaced `melix.serving.capability.*` metadata for worker diagnostics.
3. Add a Python RED diagnostics test that uses the exact Swift metadata shape
   for an admitted target/draft profile and asserts top-level
   `serving_capability` materializes in `effective-config.json`.
4. Implement the minimal metadata helper extension in
   `ModelCapabilityReceipts.swift`.
5. Update `docs/runbooks/serving-diagnostics-evidence.md` to identify the
   control-plane profile preflight path as a metadata source.
6. Run focused Swift and Python tests:

```bash
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter ModelCatalogTests/servingCapabilityAuditMetadataCoversTheProfilePreflightMatrix
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter RequestCoordinatorTests/gatewaySpeculativeDefaultsPopulateWorkerAccelerationWhenModelDefaultsAreUnspecified
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py
```

7. Run changed-scope coverage for the Python diagnostics test scope and the
   versioned pre-commit hook before committing.

## Performance And Observability

Observability mode: debug diagnostics. Runtime overhead is bounded to additional
string metadata construction before the existing request dispatch or refusal
boundary. No token-path instrumentation, model loading, optional dependency
imports, or worker probes are introduced.

Success metrics:

- Focused Swift model-catalog and request-coordinator tests pass.
- Focused Python serving diagnostics tests pass.
- Changed-scope Python coverage for touched diagnostics code remains at least
  95% when the changed Python scope is measurable.
- PR-scoped performance report status is `ok` with 0 regressions.
