# Phase 8 LoRA Adapter Workflow

## Purpose

Prepare a local dataset package, train a Melix LoRA adapter, activate it into a derived text model, verify serving behavior, publish the adapter package, and inspect or remove local derived-model outputs.

## Preconditions

- the local Melix stack is available
- the source model is a text-capable Melix model summary
- the dataset exists either as a local `melix.training_dataset_package.v1` or as a supported Hugging Face dataset configuration
- the target model family is supported by the current LoRA config mapper

## Window UI And CLI Entry Points

The native operator window now exposes the full LoRA workflow from the diagnostics and tooling
surfaces:

- choose a base text model
- choose a local dataset package or a Hugging Face dataset source
- set LoRA hyperparameters, adapter name, target repo, and optional derived-model alias
- start training, inspect persisted adapter history, and activate an adapter into a derived model

The same workflow is available through the public `melix` CLI:

```bash
swift run melix lora list

swift run melix lora train \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --dataset-uri /absolute/path/to/dataset-package \
  --adapter-name melix-dev-adapter \
  --target-repo melix/adapters/melix-dev-adapter

swift run melix lora train \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --hf-dataset-path HuggingFaceH4/ultrachat_200k \
  --hf-train-split train_sft \
  --chat-feature messages \
  --adapter-name melix-ultrachat \
  --target-repo melix/adapters/melix-ultrachat
```

## Dataset Package Layout

Create a local package directory with:

- `manifest.json`
- `samples.jsonl`

Required `manifest.json` fields:

- `schema_version`
- `dataset_id`
- `format`
- `sample_count`
- `version`

Supported package formats:

- `chat_messages`
- `prompt_completion`
- `text_completion`

Example `manifest.json`:

```json
{
  "schema_version": "melix.training_dataset_package.v1",
  "dataset_id": "melix-dev-dataset",
  "format": "chat_messages",
  "sample_count": 2,
  "version": "1"
}
```

Example `samples.jsonl` for `chat_messages`:

```jsonl
{"messages":[{"role":"system","content":"You are helpful."},{"role":"user","content":"Say hi."},{"role":"assistant","content":"Hi there."}]}
{"messages":[{"role":"user","content":"Say bye."},{"role":"assistant","content":"Bye."}]}
```

## Train Adapter

Trigger a `RunModelOperation(train_lora)` request from the native desktop tools surface, the
public `melix` CLI, or an existing control-plane client.

Use the following `ext` keys as the stable operator-facing inputs:

```json
{
  "operation": "train_lora",
  "adapter_name": "melix-dev-adapter",
  "dataset_uri": "/absolute/path/to/dataset",
  "target_repo": "melix/adapters/melix-dev-adapter",
  "target_modules": "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
  "num_layers": "8",
  "rank": "16",
  "alpha": "32",
  "dropout": "0.1",
  "learning_rate": "1e-5",
  "batch_size": "4",
  "epochs": "1",
  "response_only": "true",
  "gradient_checkpointing": "false",
  "mask_prompt": "true",
  "max_seq_length": "2048"
}
```

Equivalent CLI examples:

```bash
swift run melix lora train \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --dataset-uri /absolute/path/to/dataset-package \
  --adapter-name melix-dev-adapter \
  --target-repo melix/adapters/melix-dev-adapter \
  --rank 16 \
  --alpha 32 \
  --dropout 0.1 \
  --batch-size 4 \
  --epochs 1 \
  --learning-rate 1e-5 \
  --max-seq-length 2048 \
  --response-only \
  --mask-prompt

swift run melix lora train \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --hf-dataset-path databricks/databricks-dolly-15k \
  --hf-train-split train \
  --prompt-feature instruction \
  --completion-feature response \
  --adapter-name melix-dolly \
  --target-repo melix/adapters/melix-dolly
```

Expected training behavior:

- dataset validation runs before backend execution
- Hugging Face dataset materialization is cached under `<jobs_root>/datasets/<cache-key>`
- Melix expands compact target modules into family-specific module paths
- Melix writes a normalized dataset snapshot under `<jobs_root>/train_lora/<job_id>/`
- Melix emits the stages `resolve_source`, `validate_dataset`, `normalize_config`, `prepare_training_data`, `apply_lora`, `train`, `write_adapter`, and `write_manifest`
- the completed artifact is `train_lora.adapter.json` with schema `melix.lora_adapter_package.v1`

## Activate Adapter

Trigger `RunModelOperation(activate_adapter)` with the adapter manifest path returned by training:

```json
{
  "operation": "activate_adapter",
  "artifact_path": "/absolute/path/to/train_lora.adapter.json"
}
```

Equivalent CLI example:

```bash
swift run melix lora activate \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --adapter-path /absolute/path/to/train_lora.adapter.json \
  --alias melix-qwen35-acceptance
```

Expected activation behavior:

- Melix validates adapter compatibility against the base model
- v1 activation defaults to `fused_derived_model`
- the completed artifact is `activate_adapter.derived_model.json` with schema `melix.derived_text_model.v1` under `<jobs_root>/activate_adapter/<job_id>/`
- the result includes `derived_model_id`, `derived_model_path`, `activation_duration_ms`, and `adapter_set_hash`
- the activated model is registered into the control-plane catalog as a text model

## Verify Serving Behavior

Confirm the activation result before using the model for traffic:

1. inspect the activation manifest and confirm `schema_version == "melix.derived_text_model.v1"`
2. confirm `activation_mode == "fused_derived_model"`
3. confirm `melix.adapter_set_hash` is present and differs from incompatible adapters
4. load the derived model through the existing text runtime path
5. compare one controlled prompt against the base model and verify the derived model behavior changes in the expected direction

For operator state inspection, request a `registry_snapshot` and confirm:

- the adapter row shows `activation_status = "activated"` or `published_state = "published"` as appropriate
- the `derived_models` list contains the activated derived model entry

## Publish Adapter

Publish the adapter package, not the fused local serving directory.

Trigger `RunModelOperation(upload)` with adapter metadata:

```json
{
  "operation": "upload",
  "artifact_kind": "adapter",
  "artifact_path": "/absolute/path/to/train_lora.adapter.json",
  "adapter_name": "melix-dev-adapter",
  "target_repo": "melix/adapters/melix-dev-adapter"
}
```

Expected publish behavior:

- the upload operation records publish metadata against the adapter package
- the adapter row becomes `published`
- the local fused derived model remains a local serving artifact and is not uploaded as the adapter payload

## Hub Discovery Backend

Melix now exposes backend-owned Hugging Face discovery surfaces for operator tooling before any UI-specific parsing layer:

- `OpsCommand(search_hub_models)` accepts `query`, `page_size`, `cursor`, and `mlx_only`
- `OpsCommand(get_hub_model_card)` accepts `repo_id`

Search response normalization guarantees:

- every row includes `repo_id`, `author`, `model_name`, `pipeline_tag`, `tags`, `downloads`, `likes`, `library_name`, `sibling_files`, and `last_modified`
- `next_cursor` is preserved from the Hub `Link: rel="next"` header so paging remains deterministic
- `mlx_only = true` only returns rows marked `mlx_compatible = true`
- discovery metadata remains separate from local registry metadata; Hub rows are not registered as local Melix models until a later download or install flow completes

Model-card normalization guarantees:

- the card payload includes `repo_id`, `author`, `model_name`, `license`, `pipeline_tag`, `tags`, `downloads`, `likes`, `library_name`, `sibling_files`, `base_models`, and `last_modified`
- base-model metadata is normalized to a repeated string field even when the upstream Hub card stores a single scalar
- missing descriptive text is normalized to an empty string instead of leaking raw upstream payload structure into clients

## Inspect Or Remove Derived Local Models

Inspect:

- use `registry_snapshot` to read the adapter registry and `derived_models` list
- read the derived-model manifest under `derived_model_path`

Remove:

1. unload the derived model if it is currently resident
2. remove the local `derived_model_path` directory
3. refresh the control-plane model catalog or restart the local stack so the removed derived model is no longer discoverable

v1 note:

- Melix does not yet expose a dedicated `remove_derived_model` operation, so derived-model removal is local filesystem cleanup plus catalog refresh or restart

## Verification

```bash
make py-test
swift test --enable-code-coverage --filter MelixCLITests
swift test --package-path services/control-plane-swift --filter executeRegistersActivatedDerivedModelsIntoTheCatalog
swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests
swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests
```
