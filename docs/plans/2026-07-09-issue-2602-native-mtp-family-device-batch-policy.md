# Issue 2602 Native MTP Family, Device, And Batch Policy

## Goal

Move native-MTP admission from a Qwen-only shape check to a declarative
capability policy that can recognize additional native-head families, records
device and batch-state decisions in the receipt, and fails closed when the
runtime patch for a recognized family is not yet available.

## Governing Issue

- GitHub issue: `#2602`
- Prior slices:
  - `docs/plans/2026-07-08-issue-2602-native-mtp-capability-registry.md`
  - `docs/plans/2026-07-08-issue-2602-native-mtp-capability-receipt-object.md`

## End-State Architecture

The Python worker should resolve native-MTP capability through registered family
records rather than inline Qwen predicates. Each record declares config fields,
weight prefixes, cache shape, patch support, batch-state policy, and hardware
policy inputs. The preload path then consumes one
`NativeMTPCapabilityDecision`: patchable Qwen native heads can activate as they
do today, while recognized DeepSeek-V3-style native heads produce a typed
receipt and refuse runtime activation until a matching model patch exists.

Device policy is evaluated before patch activation. The default policy is
conservative: existing Qwen behavior remains admitted on non-Apple unknown or
unclassified hardware, known lower-end M1/M2 classes are disabled when auto
policy is in force, Darwin/arm64 hardware that cannot be classified fails
closed, and operator metadata can force enable or disable with the override
recorded in the receipt.

Batch-state policy is explicit in the same receipt. This slice does not replace
the scheduler with full batched verify-forward execution. It records that the
current implementation can preserve a singleton timeline through `filter` when
the same uid remains, reconciles then drops state on `extend`, and refuses
multi-row decode as `multi_row_decode_unsupported` rather than silently treating
it as general batched MTP.

## Scope

- Replace the hard-coded Qwen compatibility predicate in
  `worker.runtime.native_mtp.capability` with registered capability specs.
- Add DeepSeek-V3-style detection for `num_nextn_predict_layers` plus
  `model.layers.*.shared_head.*` / `model.layers.*.eh_proj.*` native-head
  weights, producing `family=deepseek_v3_nextn`.
- Add typed refusal `patch_unsupported` for recognized families whose runtime
  patch is not implemented yet.
- Add hardware policy metadata and receipt fields:
  `hardware_gate`, `hardware_policy`, `hardware_policy_reason`,
  `hardware_policy_source`, and `operator_override`.
- Add a pure device-policy helper with deterministic tests for non-Apple unknown
  hardware, M1/M2 auto-disable, M3/M4 admission, Darwin/arm64 probe failure, and
  operator force-enable/force-disable metadata.
- Add batch-state metadata and receipt fields that distinguish
  `singleton_filter_preserved`, `reconcile_on_extend`, and
  `multi_row_decode_unsupported`.
- Keep the existing public metadata keys stable for Qwen native heads.

## Non-Goals

- No DeepSeek native-head model patch or live DeepSeek execution path in this
  slice.
- No full batched verify-forward implementation.
- No public HTTP, CLI, or protobuf schema change.
- No new assistant-sidecar serving surface.

## Performance Probes

Measurement points:

- registry resolution remains a preload-only operation;
- weight-map scans remain a single pass over the index keys;
- device policy must not invoke telemetry sampling during model load;
- Qwen patch calls remain skipped for refused DeepSeek and sidecar decisions.

Success metrics:

- focused native-MTP capability and backend tests pass;
- changed-scope coverage for touched Python files remains at or above
  95 percent;
- native-MTP loader performance probe reports status `ok` with regressions `0`;
- full local pre-commit gate passes before committing on this host.

## Implementation Plan

1. Write failing tests in
   `services/mlx-worker-python/tests/test_native_mtp_capability.py` for:
   - Qwen receipt now exposing the new hardware and batch-state fields while
     preserving existing flat keys;
   - DeepSeek-V3-style config plus native-head weights resolving to
     `family=deepseek_v3_nextn`, `compatible=true`,
     `resolution=refused`, `reason=patch_unsupported`, and no patch call;
   - missing DeepSeek native-head weights resolving to
     `missing_mtp_weights`;
   - operator `melix.native_mtp.device_policy=force_on` and `force_off`
     overriding the auto policy with receipt evidence;
   - injected hardware profiles for M2 and M3/M4 class devices producing the
     expected auto policy decision;
   - the production Darwin/arm64 hardware-detection fallback caching sysctl
     results and failing closed when the chip probe times out.
2. Write failing batch-policy tests in
   `services/mlx-worker-python/tests/test_native_mtp_capability.py` for the
   pure helpers that report singleton-filter preservation and multi-row decode
   refusal.
3. Implement capability specs and a deterministic hardware-policy helper in
   `worker.runtime.native_mtp.capability`.
4. Extend `NativeMTPCapabilityReceipt` and flat metadata projection with the new
   device and batch-state fields.
5. Update preload decision logic so `patch_applied` is attempted only when the
   family spec is patchable and the device policy admits activation.
6. Update `batch_generator` helper names and ineligibility reasons to match the
   explicit batch-state policy without changing token-generation semantics.
7. Run focused tests and changed-scope coverage.
8. Run the native-MTP loader performance probe and full local gate.

## Verification Plan

Focused tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_native_mtp_capability.py \
  services/mlx-worker-python/tests/test_mlx_backend.py -k 'native_mtp'
```

Changed-scope coverage:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_native_mtp_capability.py \
  services/mlx-worker-python/tests/test_mlx_backend.py -k 'native_mtp' && \
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json && \
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/runtime/native_mtp/capability.py \
  services/mlx-worker-python/worker/runtime/native_mtp/preload.py \
  services/mlx-worker-python/worker/runtime/native_mtp/batch_generator.py \
  services/mlx-worker-python/tests/test_native_mtp_capability.py \
  services/mlx-worker-python/tests/test_mlx_backend.py
```

Performance probe:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 MELIX_NATIVE_MTP_LOADER_REPO_ROOT="$PWD" \
  uv run --project services/mlx-worker-python --extra mlx bash -c 'python3 scripts/native_mtp_loader_safetensor_scandir_probe.py'
```

Full gate:

```bash
make swift-test
make py-test
make integration-test
.githooks/pre-commit
```

## Verification Results

- Red tests were added before implementation. The first focused run failed as
  expected on the missing DeepSeek registry entry, new hardware-policy receipt
  fields, preload refusal behavior, and batch-state receipt helper.
- Focused native-MTP tests passed:
  `39 passed, 58 deselected, 2 warnings in 4.50s`.
- Adjacent VLM native-MTP preload tests passed:
  `2 passed in 0.38s`.
- `git diff --check` passed.
- Changed-scope coverage passed with aggregate changed-scope coverage at
  97 percent.
- Native-MTP loader safetensor scandir probe passed with speedup metrics:
  `speedup=1.0083192988453773`,
  `extra_speedup=7.147455764233157`,
  `model_listing_speedup=2.259606022679985`, and
  `weight_load_speedup=1.2590202577768717`.
- `make swift-test` passed. The final macOS menubar stage reported
  `834 tests in 25 suites passed`.
- `make py-test` passed:
  `4841 passed, 14 skipped, 2 warnings in 184.09s`.
- `make integration-test` passed:
  `123 passed, 1 skipped in 728.07s`.
- Review follow-up tests were added for production Darwin/arm64 hardware
  detection, module-level hardware-profile caching, Darwin/arm64 probe-timeout
  fail-closed behavior, and the M3/M4 auto-admit branch. The first focused run
  failed as expected because `_CACHED_HARDWARE_PROFILE` did not exist yet.
- Review follow-up focused native-MTP and adjacent VLM tests passed:
  `59 passed, 172 deselected, 2 warnings in 1.01s`.
- Review follow-up changed-scope coverage passed with aggregate changed-scope
  coverage at 99 percent.

## Metrics Report

Changed-scope coverage after review follow-up:

- `services/mlx-worker-python/worker/runtime/native_mtp/capability.py`:
  100.00 percent.
- `services/mlx-worker-python/worker/runtime/native_mtp/preload.py`:
  100.00 percent.
- `services/mlx-worker-python/worker/runtime/native_mtp/batch_generator.py`:
  100.00 percent.
- `services/mlx-worker-python/tests/test_native_mtp_capability.py`:
  98.61 percent.
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`:
  100.00 percent.
- Changed test lines:
  98.61 percent.
- Aggregate changed scope:
  99 percent.

Pre-commit performance report:

- `.githooks/pre-commit` passed on the final staged code snapshot.
- Report status: `ok`.
- Selected probes: `0`.
- Report path:
  `.runtime/pre-commit-performance/20260709-014710-519f6176/report/report.md`.
