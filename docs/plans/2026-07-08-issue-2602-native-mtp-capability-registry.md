# Issue 2602 Native MTP Capability Registry

## Goal

Generalize Melix native MTP admission from the current embedded Qwen3.5/Qwen3.6
checks into a declarative capability-registry boundary that can later support
additional native heads, batched MTP, and hardware-aware activation without
exposing assistant sidecar checkpoints as runnable serving targets.

## Governing Issue

- GitHub issue: `#2602`
- First implementation slice: add the registry and receipt adapter, then route
  the existing Qwen3.5/Qwen3.6 native-head path through that registry.

## End-State Architecture

The Python worker owns model-local acceleration truth. Native MTP activation
should be decided by a pure, testable registry before MLX or mlx-vlm loading:

- config parsing resolves a registered native-MTP family and head source
- weight-map inspection records whether native-head tensors are present
- assistant-sidecar or draft-only checkpoints fail closed before patching
- runtime patching consumes only the registry decision
- load receipts expose the same acceleration contract shape used by speculative
  draft-model paths, even when the first implementation still runs only the
  singleton Qwen native-head route

Future slices should add batch-shape expansion and device-aware gating behind
this decision object rather than adding more hard-coded checks in text or VLM
runtime loaders.

## Scope

- Add a native MTP capability registry module under
  `worker.runtime.native_mtp`.
- Preserve the current Qwen3.5/Qwen3.6 native-head behavior as the first
  registered capability.
- Add stable receipt fields that describe method, source, family, head count,
  batch shape, hardware gate state, resolution, and refusal reason.
- Refuse assistant-sidecar-shaped MTP configs without applying native MTP
  patches.
- Route both text and VLM preload patch functions through the registry.
- Keep the existing legacy `melix.native_mtp.*` fields for compatibility.

## Non-Goals

- No new public HTTP API or protobuf schema.
- No broad model-family expansion beyond the existing Qwen native-head shape.
- No batched MTP implementation in this slice; batch support remains reported
  as `singleton_only`.
- No Apple Silicon hardware policy enforcement in this slice; hardware gating
  is reported as `not_evaluated`.
- No assistant-sidecar speculative decode execution changes.

## Performance Probes

Measurement points:

- preload decision latency for parsing `config.json` and the safetensors index
- registry allocation shape on unsupported models and disabled legacy paths
- native MTP patch calls only after registry acceptance
- PR-scoped native-MTP loader probe remains the performance merge gate for
  native-MTP loader-adjacent changes

Success metrics:

- Existing Qwen native-head fixtures still activate with
  `melix.native_mtp.active=true`.
- Sidecar-shaped assistant configs return a refused receipt and never call
  `apply_native_mtp_patches()`.
- Disabled legacy requests remain inactive with `melix.native_mtp.reason=disabled`.
- Focused tests and changed-scope coverage are at or above 95 percent for the
  changed Python scope.
- Local and CI PR-scoped performance reports finish with status `ok`,
  regressions `0`, and verification failures `0`.

## Implementation Plan

1. Add failing tests for a pure registry decision covering the Qwen native-head
   fixture, an assistant-sidecar-shaped config, and the disabled legacy path.
2. Add failing preload integration tests proving text and VLM loaders expose
   the receipt fields and only apply native MTP patches for accepted native
   heads.
3. Implement the registry decision object and receipt adapter under
   `worker.runtime.native_mtp`.
4. Replace duplicate text and VLM config/weight helper logic with the registry.
5. Run focused tests, changed-scope coverage, the native-MTP scoped performance
   probe, and the repository pre-commit gate before opening the PR.

## Verification Plan

Focused tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_native_mtp_capability.py \
  services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights
```

Changed-scope coverage:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_native_mtp_capability.py \
  services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights && \
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json && \
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/runtime/native_mtp/capability.py \
  services/mlx-worker-python/worker/runtime/mlx_text_runtime.py \
  services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py \
  services/mlx-worker-python/tests/test_native_mtp_capability.py \
  services/mlx-worker-python/tests/test_mlx_vlm_runtime.py
```

Metrics and gates:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 MELIX_NATIVE_MTP_LOADER_REPO_ROOT="$PWD" \
  uv run --project services/mlx-worker-python --extra mlx bash -c 'python3 scripts/native_mtp_loader_safetensor_scandir_probe.py'
make swift-test
make py-test
make integration-test
.githooks/pre-commit
```

## Verification Results

- Red test:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_native_mtp_capability.py`
  failed as expected before implementation with
  `ModuleNotFoundError: No module named 'worker.runtime.native_mtp.capability'`.
- Focused tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_native_mtp_capability.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_native_mtp_preload_patch_detects_qwen36_mtp_weights`
  passed with 14 tests.
- Native MTP regression tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q ...`
  passed with 22 tests across the new registry coverage, VLM preload fixture,
  and existing native-MTP backend tests.
- Changed-scope coverage:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q ... && coverage json ... && python3 scripts/changed_scope_coverage.py ...`
  passed before commit staging with changed-scope aggregate coverage above the
  required 95 percent. Follow-up module-scoped coverage for the extracted
  native-MTP helpers passed with `capability.py` at 99 percent and `preload.py`
  at 100 percent.
- Native MTP loader performance probe:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 MELIX_NATIVE_MTP_LOADER_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python --extra mlx bash -c 'python3 scripts/native_mtp_loader_safetensor_scandir_probe.py'`
  passed with direct-probe speedups `speedup=1.0144`,
  `extra_speedup=6.9534`, `model_listing_speedup=2.2633`, and
  `weight_load_speedup=1.2343`.
- `make py-test` passed with `4769 passed, 14 skipped, 2 warnings in 172.18s`.
- `make swift-test` passed; the macOS menubar stage completed with
  `rc=0` and `834 tests` passing in that stage.
- `make integration-test` passed with `123 passed, 1 skipped in 699.04s`.
- `.githooks/pre-commit` must run after staging the exact commit content so the
  hook can select the PR-scoped performance probes from staged files; record
  the resulting report path in the pull request evidence.
