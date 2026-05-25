# Issue 1528 Training Admission Receipts

## Goal

Harden LoRA training admission so invalid training controls fail before runner
launch with typed operator details, while accepted runs persist the resolved
controls that affected backend execution.

## Scope

This slice is limited to worker-owned LoRA training request validation and the
adapter manifest receipt emitted by `train_lora`. It intentionally avoids
artifact resume canaries and runtime dependency gates, which are tracked by
separate follow-up issues.

## Design

- Keep `normalize_training_config` as the single admission normalization point
  for CLI, API, and Desktop requests.
- Preserve legal sentinel behavior for `max_steps=0` by validating only explicit
  positive run caps.
- Add typed validation details for numeric admission failures: field, reason,
  received value, and allowed bounds.
- Reject non-finite floating-point hyperparameters such as `nan` and `inf`
  before they can reach backend runner arguments.
- Classify `-inf` as a bounds violation (`below_minimum`) rather than only a
  non-finite value, so range-handling consumers do not miss the failure mode.
- Record resolved defaults and capability gates in the adapter manifest before
  backend-dependent metrics are interpreted.
- Record dataset file resolution from the resolved package and normalized
  snapshot, including validation file presence.
- Record backend control receipts for gradient clipping, eval batch size, and
  omitted scheduler kwargs using deterministic policy objects.

## Acceptance Mapping

- Invalid hyperparameters return typed 422-style details through existing
  `ModelOperationError.details`, including non-finite float controls.
- Legal sentinels remain accepted and are reflected in `resolved_bounds`.
- Capability-gated defaults are recorded in `capability_gate`.
- Dataset file resolution, grad clipping, eval batch size, and scheduler
  omission receipts are recorded on `train_lora.adapter.json`.
- CLI/API/Desktop surfaces share the same worker admission result for focused
  fixtures because they converge on `normalize_training_config` before runner
  launch. This issue does not change Swift request shaping or Desktop UI
  rendering. Evidence for dedicated UI rendering is N/A for this worker-only
  slice; follow-up surface-specific work should assert presentation of the same
  `ModelOperationError.details` payload rather than duplicating validators.

## Verification

Focused verification:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_lora_model_ops_unit.py -q -k "training_admission"
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_lora_model_ops.py -q -k "training_config_validates_direct_error_paths or training_config_helper_resolution_paths_and_limits"
git diff --check
```

No runtime performance probe is applicable because this slice changes admission
validation and manifest receipt fields before training execution. Metrics report:
N/A for performance; focused correctness is covered by unit tests above.
