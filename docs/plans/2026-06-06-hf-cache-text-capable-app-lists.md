# Hugging Face Cache Text-Capable App Lists Implementation Plan

## Goal

Make Hugging Face cache-discovered MLX models that are capable of text generation, including VLM models, appear in the macOS App surfaces that operate on text-capable local models.

## Context

`docs/architecture-spec.md` defines the worker registry as the source of ordered multi-root model discovery. The registry scans user-configured roots first, then the default Hugging Face cache at `~/.cache/huggingface/hub`, and publishes cache-discovered snapshots with metadata such as `melix.source_kind=hf_cache_snapshot`.

The worker and `/v1/models` discovery path already exposes compatible Hugging Face cache snapshots. The remaining issue is App-side eligibility: some App lists read only `models` from the runtime snapshot or filter only `kind == "text"`, so a registry-only VLM model with `text` modality and `generate` task can be visible in Server/Evaluation but absent from Chat or LoRA surfaces.

## Scope

- Keep storage ownership unchanged. Do not copy Hugging Face cache models into `MELIX_MANAGED_MODEL_ROOT`.
- Keep worker registry scanning unchanged unless a test proves the App needs additional registry metadata.
- Update macOS App eligibility only for text-capable workflows.
- Preserve the model's original `kind` and source metadata. A VLM remains labeled as a VLM.
- Do not add image-only, audio-only, OCR-only, or ambiguous models to Chat or LoRA lists.

## Success Metrics

- A registry-only Hugging Face cache VLM model with `supported_modalities=text,image` and `supported_tasks=vlm,generate` is selectable for LoRA.
- Chat model resolution accepts the same registry-only model when selected.
- Server, Benchmark, and Evaluation behavior remains covered by existing tests.
- The change adds no filesystem scans and only evaluates eligibility over already-loaded App model rows.

## Performance Probes

- Unit-level probe: targeted Swift tests for the App view model.
- Runtime performance impact: N/A for this slice. The implementation only changes in-memory filtering over existing `RuntimeModelRow` arrays and does not touch registry scanning, worker load, or HTTP serving.
- Metrics report: N/A runtime metrics; covered by the test commands recorded in the handoff or PR evidence.

## Implementation Steps

### Step 1: Add Regression Tests

Files:

- Modify `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`

Tests:

- Add a LoRA picker regression test using `makeEvaluationRegistrySnapshotManifest()` and a model-ops refresh. Assert that `unsloth/gemma-4-E4B-it-MLX-8bit` appears in `loraCapableModels` and is resolved as the selected LoRA model.
- Add a Chat server-session regression test using the same registry snapshot. Create a local server from `unsloth/gemma-4-E4B-it-MLX-8bit`, bind Chat to that server, invoke a chat request, and assert that the fake client receives that model ID.
- Add a Chat capability-list regression test using the same registry snapshot. Assert that the VLM capability row appears after model-ops refresh.
- Preserve the image-only LoRA test so image-only catalog rows remain excluded.

Expected RED command:

```bash
swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests/(loraModelPickerIncludesTextCapableHFCacheVLMModels|chatSendsThroughServerCreatedFromTextCapableHFCacheVLMModel|chatCapabilityListIncludesTextCapableHFCacheVLMModels)'
```

Expected result before implementation:

- LoRA test fails because `loraCapableModels` filters only runtime `models` with `kind == "text"`.
- Chat capability-list test fails because model-ops refresh previously did not refresh Chat capabilities from registry catalog rows.

### Step 2: Centralize Text-Capable Eligibility

Files:

- Modify `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

Implementation:

- Add a private static helper that accepts a `RuntimeModelRow` when:
  - `kind == "text"`, or
  - `kind == "vlm"` and the row exposes a text/chat feature or text-generation/chat/generate task, or
  - explicit task and feature metadata identify text generation without relying on a kind-only check.
- Keep image, image-generation, OCR, audio, speech, transcription, and ambiguous rows out unless they explicitly expose text-generation/chat capability.

### Step 3: Apply Eligibility to Chat and LoRA

Files:

- Modify `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

Implementation:

- Change `loraCapableModels` to filter `catalogModelsIncludingRegistry` with the centralized helper.
- Change `resolvedChatModelID()` to accept the selected model from `catalogModelsIncludingRegistry` when the helper says it is text-capable.
- Change `refreshChatCapabilities()` fallback selection to use the same helper and merged catalog list.
- Refresh Chat capabilities after applying a model-ops registry snapshot so registry-only rows appear immediately after rescan.
- Keep existing server, benchmark, evaluation, and image list behavior intact.

### Step 4: Verify

Commands:

```bash
swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests/(loraModelPickerIncludesTextCapableHFCacheVLMModels|chatSendsThroughServerCreatedFromTextCapableHFCacheVLMModel|chatCapabilityListIncludesTextCapableHFCacheVLMModels)'
swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests/(loraModelSelectionFallsBackToFirstTextModel|serverModelOptionsHidePlaceholdersAndCreateFromReadyRegistryModels|evaluationModelPickerIncludesDownloadedRegistryGemma4Models|evaluationModelPickerIncludesTextCapableVLMCatalogModels|chatRouteReadinessReflectsMultimodalAvailability)'
```

Expected result:

- All targeted tests pass.
- No generated artifacts or lockfiles change.
