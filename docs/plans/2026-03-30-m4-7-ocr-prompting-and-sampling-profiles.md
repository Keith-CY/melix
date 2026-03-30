# M4.7 OCR Prompting And Sampling Profiles

## Goal

Add OCR-family-specific prompting, stop-token handling, and default sampling profiles so OCR behavior is model-aware rather than generic.

## Scope

- add OCR prompt templates and stop-token rules
- add default OCR sampling policy
- keep OCR overrides explicit and operator-visible

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/WorkerClient/`
- update `services/control-plane-swift/Sources/HTTPGateway/OpenAI/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- update `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- update `tests/integration/test_phase6_operator_workflows.py`

## Implementation Notes

- OCR defaults should be data-driven rather than hardcoded to one development model
- stop-token handling should remain compatible with stream assembly
- model settings should allow override without hiding the default effective profile

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_vision_runtime.py -q`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_phase6_operator_workflows.py -k 'ocr_chat_applies_default_and_overridden_stop_sequences' -q`
- `swift test --package-path services/control-plane-swift --filter 'chatCompletionsRequestEncodesStopAliases|ocrExecutionPolicyStaysDisabledWithoutModelDefaults|postChatCompletionsAppliesModelOCRDefaultsForOCRModels|startChatAppliesModelOCRDefaultsForOCRModels'`
- `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'phaseSixContractSeedModelsExposeMultimodalRoutesAndTasks|bootstrapWorkerPreparationCarriesOCRProfileMetadataIntoWorkerModelSpecs|ocrModelPoliciesShapeMultimodalRequestsWithDefaultSamplingAndStopSequences|ocrRequestOverridesWinOverModelSamplingDefaults|chatCompletionsRequestDecodesStopAliases|chatCompletionsRequestEncodesStopAliases|ocrExecutionPolicyStaysDisabledWithoutModelDefaults|postChatCompletionsAppliesModelOCRDefaultsForOCRModels|startChatAppliesModelOCRDefaultsForOCRModels'`
- `swift test --package-path apps/macos-menubar --filter 'fetchModelInfoSurfacesOCRProfileDefaultsFromActiveSnapshot|toolsTabRendersOCRProfileMetadata'`
- `swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'fetchModelInfoSurfacesOCRProfileDefaultsFromActiveSnapshot|toolsTabRendersOCRProfileMetadata'`

## Metrics Report

- Python changed-line coverage: `97.83% (90/92)`
- Swift control-plane changed-line coverage: `98.23% (500/509)`
- Swift menu bar changed-line coverage: `100.00% (87/87)`
- OCR stop-sequence override integration: `1/1`

## Acceptance

- OCR-capable models can resolve to model-aware prompt and sampling defaults
- default and overridden OCR behavior are test-covered
