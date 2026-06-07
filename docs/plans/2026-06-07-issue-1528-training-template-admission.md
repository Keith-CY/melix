# Issue 1528 Training Template Admission Implementation Plan

## Goal

Add admission-time validation for custom SFT training templates so missing prompt,
completion, or assistant-generation markers fail with typed operator errors
before backend training starts.

## Architecture

The Python worker will treat custom local conversion templates as resolved
training controls. Template validation belongs in `training_config.py` because
`normalize_training_config` already owns typed 422-style admission failures and
is shared by CLI, API, and desktop requests through the model-operation surface.
The resulting receipt will be copied into the normalized dataset snapshot and
the final adapter manifest so accepted template paths are visible with the rest
of the resolved-control evidence.

## Scope Boundaries

- Include: `custom_training_template`, `training_template_receipt`,
  `template_path`, `template_source`, `required_placeholders`,
  `assistant_marker_policy`, and typed `invalid_training_template` failures.
- Include: `{INPUT}` and `{OUTPUT}` placeholder validation for custom prompt
  templates.
- Include: assistant marker validation for response-only SFT templates.
- Include: two-example custom templates requiring prompt, completion, and
  assistant marker paths.
- Exclude: replacing builtin `alpaca`, `sharegpt`, or chat template rendering.
- Exclude: multimodal processor template transformation owned by later #1531
  watch-log slices.

## Files

- Modify: `services/mlx-worker-python/worker/model_ops/training_config.py`
  - Add a compact receipt field to `LoRATrainingConfig`.
  - Validate custom template controls after response-only defaults resolve.
- Modify: `services/mlx-worker-python/worker/model_ops/training_receipts.py`
  - Add a helper that normalizes accepted template receipt fields and raises
    typed 422-style failures for invalid custom template inputs.
- Modify: `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
  - Copy the receipt into normalized dataset manifest overrides and adapter
    manifests.
- Add: `services/mlx-worker-python/tests/test_training_template_admission.py`
  - Add service-level tests for invalid template placeholders, response-only
    assistant markers, two-example separators, and accepted template receipts.
  - Add helper-level tests for builtin, requested-marker, inferred-marker, and
    marker-drift receipt behavior.
- Modify: `docs/runbooks/phase-8-lora-adapter-workflow.md`
  - Document the custom template ext keys and typed preflight behavior.

## Test Plan

1. Add failing service-level tests in `test_training_template_admission.py`.
2. Run the new tests and verify they fail for missing validation/receipt fields.
3. Implement the minimal receipt helper and config wiring.
4. Re-run the focused tests.
5. Run the broader focused LoRA receipt/admission tests.
6. Run `git diff --check`.

## Performance Probes And Metrics

The new check is string-only admission work over operator-provided template
fields and runs once per training request. The changed scope has no meaningful
runtime performance probe beyond the existing PR-scoped worker test selection.
Success metric: invalid templates fail before runner invocation, and accepted
templates add stable receipt fields without changing backend execution.
