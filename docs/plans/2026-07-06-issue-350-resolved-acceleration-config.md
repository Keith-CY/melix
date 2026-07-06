# Issue 350 Resolved Acceleration Config Receipt Plan

## Goal

Normalize low-level serving acceleration knobs into one typed diagnostics-only
`ResolvedAccelerationConfig` receipt before changing runtime acceleration
behavior.

## Scope

This slice implements the next executable #350 step from the July 6 watch
update: add a control-plane fixture that normalizes existing low-level
acceleration fields into a single resolved config receipt, then wire that
receipt into diagnostics metadata.

In scope:

- Define a control-plane `ResolvedAccelerationConfig` value derived from the
  already-resolved worker acceleration policy, capability receipt, and profile
  admission receipt.
- Emit `melix.serving.acceleration_config.*` metadata from the existing request
  acceleration resolution path.
- Materialize a top-level `serving_acceleration_config` receipt in Python
  serving diagnostics when upstream metadata is complete.
- Cover baseline, admitted speculative, forced-off speculative, unsupported
  mode, invalid draft, and unverified-profile rows in tests.
- Document the receipt shape and passive diagnostics contract.

Out of scope:

- New protobuf fields or generated artifacts.
- New acceleration algorithms, scheduler behavior, controller state, or output
  hashing behavior.
- Model discovery, optional dependency probing, health polling, prefetch, or
  route admission during bundle writing.
- Changing existing fallback/refusal semantics.

## End-State Architecture

The best Melix end state is one acceleration contract shared by parser,
profile, admission, runtime launch, diagnostics, and benchmark evidence. Low
level fields such as `accelerationMode`, `draftModelID`, `numDraftTokens`,
profile id, and route policy should be parsed once into a typed resolved config
with explicit method, sidecar model, token count, conflicts, controller scope,
and disabled reason. Runtime controllers can later consume the same contract
without guessing from legacy flags.

This slice only builds the observable receipt boundary. The existing
`RequestCoordinator` still owns runtime dispatch, and
`ModelCapabilityReceipts` remains the model/profile admission source of truth.
The diagnostics writer stays passive and records only metadata supplied by
upstream control-plane code.

## Receipt Mapping

The control plane should emit:

- `melix.serving.acceleration_config.schema_version`:
  `melix.resolved_acceleration_config.v1`
- `melix.serving.acceleration_config.method`: effective method such as
  `baseline`, `speculative_decode`, `accelerated_prefill`,
  `active_kv_quantized`, or `sparse_prefill`.
- `melix.serving.acceleration_config.requested_method`: operator/model
  requested method after parser normalization.
- `melix.serving.acceleration_config.sidecar_model`: draft/sidecar model id, or
  an empty string.
- `melix.serving.acceleration_config.num_speculative_tokens`: resolved draft
  token count as a decimal string.
- `melix.serving.acceleration_config.profile`: resolved or requested serving
  acceleration profile.
- `melix.serving.acceleration_config.conflicting_flags`: comma-separated flags
  ignored or rejected during resolution.
- `melix.serving.acceleration_config.controller_scope`: `none` for baseline and
  `request` for speculative requests in this slice.
- `melix.serving.acceleration_config.disabled_reason`: typed reason for a
  disabled or refused acceleration path, or `none`.

Python diagnostics materializes the same fields under
`serving_acceleration_config`, converting `conflicting_flags` to a list and
`num_speculative_tokens` to an integer.

## Test Plan

Follow TDD:

1. Add Swift RED tests in `ModelCatalogTests` proving
   `ResolvedAccelerationConfig` normalizes baseline, admitted speculative,
   forced-off speculative, invalid draft, unsupported mode, and unverified
   profile rows.
2. Add a Swift RED request-coordinator test proving dispatched worker metadata
   contains the `melix.serving.acceleration_config.*` receipt for an admitted
   speculative request.
3. Add a Python RED diagnostics test proving complete metadata materializes as
   `serving_acceleration_config`, with list and integer normalization.
4. Implement the minimal Swift helper and RequestCoordinator wire-up.
5. Implement the passive Python diagnostics materializer.
6. Update `docs/runbooks/serving-diagnostics-evidence.md`.

Focused verification commands:

```bash
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter ModelCatalogTests/resolvedAccelerationConfigReceiptNormalizesLowLevelAccelerationFields
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter RequestCoordinatorTests/gatewaySpeculativeDefaultsPopulateWorkerAccelerationWhenModelDefaultsAreUnspecified
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py
```

Before commit, run `git diff --check` and `.githooks/pre-commit` for the full
local gate and scoped performance report on this host.

## Performance And Metrics

Performance probe points:

- Metadata construction happens once per request during existing acceleration
  resolution.
- Python bundle materialization performs one additional metadata scan over the
  same existing metadata sources.

Success metrics:

- Focused Swift and Python tests pass.
- Full pre-commit local gate passes.
- Scoped performance report status is `ok` with 0 regressions before commit and
  on the PR.
