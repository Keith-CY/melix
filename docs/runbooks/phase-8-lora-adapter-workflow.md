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
- choose `LoRA` or `QLoRA` training mode
- set LoRA hyperparameters, adapter name, target repo, optional validation split, and optional derived-model alias
- choose `fused_derived_model` or `adapter_backed_runtime` activation mode
- start training, inspect persisted adapter history, activate an adapter into a derived model, publish the adapter package, and remove an activated derived model

The same workflow is available through the public `melix` CLI:

```bash
swift run melix lora list

swift run melix lora train \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --dataset-uri /absolute/path/to/dataset-package \
  --adapter-name melix-dev-adapter \
  --target-repo melix/adapters/melix-dev-adapter \
  --training-mode qlora

swift run melix lora train \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --hf-dataset-path HuggingFaceH4/ultrachat_200k \
  --hf-train-split train_sft \
  --hf-valid-split test_sft \
  --chat-feature messages \
  --adapter-name melix-ultrachat \
  --target-repo melix/adapters/melix-ultrachat \
  --training-mode qlora

swift run melix lora activate \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --adapter-path /absolute/path/to/train_lora.adapter.json \
  --activation-mode adapter_backed_runtime \
  --alias melix-qwen35-acceptance

swift run melix lora remove-derived \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --derived-model-id melix-qwen35-acceptance
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
  "training_mode": "qlora",
  "target_repo": "melix/adapters/melix-dev-adapter",
  "target_modules": "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
  "num_layers": "8",
  "rank": "16",
  "alpha": "32",
  "dropout": "0.1",
  "learning_rate": "1e-5",
  "batch_size": "4",
  "epochs": "1",
  "hf_valid_split": "test_sft",
  "derived_model_alias": "melix-qwen35-acceptance",
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
  --training-mode qlora \
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
  --hf-valid-split validation \
  --prompt-feature instruction \
  --completion-feature response \
  --adapter-name melix-dolly \
  --target-repo melix/adapters/melix-dolly \
  --training-mode lora
```

Expected training behavior:

- dataset validation runs before backend execution
- Hugging Face dataset materialization is cached under `<jobs_root>/datasets/<cache-key>`
- Melix supports both `lora` and `qlora` through the same `train_lora` surface
- if `hf_valid_split` is provided, the normalized dataset snapshot persists the explicit validation source
- Melix expands compact target modules into family-specific module paths
- Melix writes a normalized dataset snapshot under `<jobs_root>/train_lora/<job_id>/`
- Melix emits the stages `resolve_source`, `validate_dataset`, `normalize_config`, `prepare_training_data`, `apply_lora`, `train`, `write_adapter`, and `write_manifest`
- the completed artifact is `train_lora.adapter.json` with schema `melix.lora_adapter_package.v1`

## Activate Adapter

Trigger `RunModelOperation(activate_adapter)` with the adapter manifest path returned by training:

```json
{
  "operation": "activate_adapter",
  "artifact_path": "/absolute/path/to/train_lora.adapter.json",
  "activation_mode": "adapter_backed_runtime",
  "derived_model_alias": "melix-qwen35-acceptance"
}
```

Equivalent CLI example:

```bash
swift run melix lora activate \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --adapter-path /absolute/path/to/train_lora.adapter.json \
  --activation-mode adapter_backed_runtime \
  --alias melix-qwen35-acceptance
```

Expected activation behavior:

- Melix validates adapter compatibility against the base model
- `fused_derived_model` remains the default when `--activation-mode` is omitted
- `adapter_backed_runtime` is a supported first-class activation mode for keeping adapter artifacts attached to the runtime instead of materializing a fused local model
- the completed artifact is `activate_adapter.derived_model.json` with schema `melix.derived_text_model.v1` under `<jobs_root>/activate_adapter/<job_id>/`
- the result includes `derived_model_id`, `derived_model_path`, `activation_duration_ms`, and `adapter_set_hash`
- the activated model is registered into the control-plane catalog as a text model

## Verify Serving Behavior

Confirm the activation result before using the model for traffic:

1. inspect the activation manifest and confirm `schema_version == "melix.derived_text_model.v1"`
2. confirm `activation_mode` matches the requested mode, either `fused_derived_model` or `adapter_backed_runtime`
3. confirm `melix.adapter_set_hash` is present and differs from incompatible adapters
4. load the derived model through the existing text runtime path
5. compare one controlled prompt against the base model and verify the derived model behavior changes in the expected direction

For operator state inspection, request a `registry_snapshot` and confirm:

- the adapter row shows `activation_status = "activated"` or `published_state = "published"` as appropriate
- the `derived_models` list contains the activated derived model entry

## Publish Adapter Or Merged Artifact

Melix now treats adapter-only export and merged-model export as separate distribution contracts.
Use adapter export when you want a reusable LoRA package for downstream activation. Use merged export
only when you intentionally want to distribute a fused derived model directory.

Adapter publish request:

```json
{
  "operation": "upload",
  "artifact_kind": "adapter_export",
  "artifact_path": "/absolute/path/to/train_lora.adapter.json",
  "adapter_name": "melix-dev-adapter",
  "target_repo": "melix/adapters/melix-dev-adapter"
}
```

Equivalent CLI example:

```bash
swift run melix lora publish \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --target-repo melix/adapters/melix-dev-adapter \
  --adapter-path /absolute/path/to/train_lora.adapter.json
```

Merged publish request from a fused activation manifest:

```json
{
  "operation": "upload",
  "artifact_kind": "merged_export",
  "artifact_path": "/absolute/path/to/activate_adapter/<job-id>/<alias>/manifest.json",
  "artifact_manifest_path": "/absolute/path/to/activate_adapter/<job-id>/<alias>/manifest.json",
  "target_repo": "melix/models/melix-dev-fused"
}
```

Equivalent CLI example:

```bash
swift run melix lora publish \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --target-repo melix/models/melix-dev-fused \
  --manifest-path /absolute/path/to/activate_adapter/<job-id>/<alias>/manifest.json
```

Expected publish behavior:

- adapter export uploads a staged adapter bundle containing the adapter manifest plus adapter weights and config
- merged export uploads the fused derived-model directory and rejects `adapter_backed_runtime` manifests
- upload receipts record `export_artifact_kind`, `published_repo`, publish backend, and `parent_lineage`
- registry snapshots show adapter and merged publish lineage so operators can confirm which local artifact produced each remote repo
- `swift run melix lora list` now includes published repo and publish artifact kind in the operator-readable table

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

```bash
swift run melix lora remove-derived \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --derived-model-id melix-qwen35-acceptance
```

Equivalent manifest-targeted removal:

```bash
swift run melix lora remove-derived \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --manifest-path /absolute/path/to/activate_adapter.derived_model.json
```

Expected removal behavior:

- Melix unloads the derived model if it is still resident
- Melix removes product-owned derived-model artifacts
- Melix refreshes registry state and prunes the removed derived model from the local catalog
- invalid remove requests fail with typed guard rails instead of falling back to manual filesystem cleanup

## Verification

```bash
make py-test
swift test --enable-code-coverage --filter MelixCLITests
swift test --package-path services/control-plane-swift --filter executeRegistersActivatedDerivedModelsIntoTheCatalog
swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests
swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_lora_cli_smoke.py --json
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_lora_window_smoke.py --json
```
