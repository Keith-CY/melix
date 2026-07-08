# Issue 2602 Native MTP Capability Receipt Object

## Goal

Add a structured native-MTP capability receipt object for the current Qwen
native-head path so future model families, batch-shape changes, and hardware
policy checks extend one typed contract instead of adding more flat metadata
fields.

## Governing Issue

- GitHub issue: `#2602`
- Prior slice: `docs/plans/2026-07-08-issue-2602-native-mtp-capability-registry.md`
- This slice: stabilize the receipt object around the existing Qwen native-head
  registry decision and keep the current execution path unchanged.

## End-State Architecture

The Python worker should resolve native-MTP admission through a pure
`NativeMTPCapabilityDecision`, then derive two receipt surfaces from the same
structured object:

- a machine-readable JSON receipt for downstream evidence and future unified
  speculative configuration receipts;
- the existing flat `melix.native_mtp.receipt.*` metadata for compatibility
  with current operator surfaces and tests.

The receipt object must prove the current Qwen native-head path has a declared
source, depth, weights state, cache-shape contract, batch-state policy,
hardware gate state, and request/admission result. Unsupported, disabled,
missing-weight, patch-failed, and assistant-sidecar cases should use the same
object with precise refusal or fallback reasons.

## Scope

- Add a typed native-MTP capability receipt dataclass under
  `worker.runtime.native_mtp.capability`.
- Add a stable JSON metadata field, `melix.native_mtp.receipt_json`, emitted by
  both text and VLM preload paths through the existing shared preload helper.
- Derive existing flat receipt metadata from the object so the two surfaces
  cannot drift.
- Add Qwen-family fixture coverage for the JSON receipt object and a refusal
  fixture for assistant-sidecar-shaped configs.
- Keep `NativeMTPCapabilityDecision` and existing flat metadata fields backward
  compatible.

## Non-Goals

- No new public CLI, HTTP, or protobuf surface.
- No second model-family admission.
- No batched MTP execution.
- No Apple Silicon hardware-policy enforcement; the receipt continues to report
  `hardware_gate=not_evaluated`.
- No changed behavior for native-MTP patching, generation, or cache rollback.

## Performance Probes

Measurement points:

- receipt construction allocation and JSON serialization happen once at preload,
  not per token;
- native-MTP patch calls remain gated by the same registry decision;
- the existing native-MTP loader PR-scoped probe remains the merge gate for
  this loader-adjacent path.

Success metrics:

- focused native-MTP capability tests pass;
- changed-scope coverage for `capability.py`, `preload.py`, and the dedicated
  test file remains at or above 95 percent;
- PR-scoped performance report finishes with status `ok`, regressions `0`, and
  verification failures `0`;
- full local pre-commit gate passes before commit on this host.

## Implementation Plan

1. Write failing tests in `services/mlx-worker-python/tests/test_native_mtp_capability.py`
   that assert:
   - accepted Qwen native-head metadata includes `melix.native_mtp.receipt_json`;
   - the JSON receipt includes schema, status, requested/resolved method, source,
     family, weights, effective depth, cache shape, batch shape, batch-state
     policy, hardware gate, request gate, patch state, and fallback reason;
   - assistant-sidecar refusal emits the same JSON object with
     `status=refused` and `fallback_reason=assistant_sidecar`;
   - the existing flat receipt fields match the JSON object.
2. Run the new tests and verify they fail because `receipt_json` and the extra
   receipt fields are absent.
3. Add the receipt dataclass and conversion helpers in
   `worker.runtime.native_mtp.capability`.
4. Update `NativeMTPCapabilityDecision.to_metadata()` to build the object once,
   serialize it as compact sorted JSON, and project the existing flat fields
   from it.
5. Run focused tests and changed-scope coverage.
6. Run the native-MTP loader performance probe and the repository pre-commit
   hook before opening the PR.

## Verification Plan

Focused tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_native_mtp_capability.py
```

Changed-scope coverage:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_native_mtp_capability.py && \
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json && \
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/runtime/native_mtp/capability.py \
  services/mlx-worker-python/worker/runtime/native_mtp/preload.py \
  services/mlx-worker-python/tests/test_native_mtp_capability.py
```

Performance probe:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 MELIX_NATIVE_MTP_LOADER_REPO_ROOT="$PWD" \
  uv run --project services/mlx-worker-python --extra mlx bash -c 'python3 scripts/native_mtp_loader_safetensor_scandir_probe.py'
```

Full gate before commit:

```bash
.githooks/pre-commit
```

## Verification Results

- Red test:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_native_mtp_capability.py`
  failed as expected before implementation with two `KeyError:
  'melix.native_mtp.receipt_json'` failures.
- Focused capability tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_native_mtp_capability.py`
  passed with `14 passed`.
- Adjacent native-MTP regression tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_native_mtp_capability.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_applies_native_mtp_preload_patch_before_load services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights services/mlx-worker-python/tests/test_mlx_backend.py::test_auto_backend_uses_batch_generator_for_native_mtp_text_models services/mlx-worker-python/tests/test_mlx_backend.py::test_native_mtp_text_patch_adds_qwen35_methods`
  passed with `18 passed, 2 warnings`.
- Changed-scope coverage:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q ... && coverage json ... && python3 scripts/changed_scope_coverage.py ...`
  passed with `TOTAL 69 0 100%`.
- Native MTP loader performance probe:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 MELIX_NATIVE_MTP_LOADER_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python --extra mlx bash -c 'python3 scripts/native_mtp_loader_safetensor_scandir_probe.py'`
  passed with `speedup=1.0127`, `extra_speedup=7.2736`,
  `model_listing_speedup=2.2957`, and `weight_load_speedup=1.2735`.
