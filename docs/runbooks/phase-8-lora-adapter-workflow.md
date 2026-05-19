# Phase 8 LoRA Adapter Workflow

## Purpose

Prepare a local dataset package, train a Melix LoRA adapter, activate it into a derived text model, verify serving behavior, publish the adapter package, and inspect or remove local derived-model outputs.

## Preconditions

- the local Melix stack is available
- the source model is a text model or a model summary with an explicit
  training-ready component LoRA surface
- the dataset exists either as a local `melix.training_dataset_package.v1` or as a supported Hugging Face dataset configuration
- the target model family is supported by the current LoRA config mapper
- operators understand whether the chosen family is stable, experimental, or currently blocked for LoRA training

## Window UI And CLI Entry Points

The native operator window now exposes the full LoRA workflow from the diagnostics and tooling
surfaces:

- choose a base text model
- choose a local dataset package or a Hugging Face dataset source
- choose `LoRA`, `QLoRA`, `DoRA`, preference, or continual-pretraining training mode
- set LoRA hyperparameters, adapter name, target repo, optional validation split, and optional derived-model alias
- choose `fused_derived_model` or `adapter_backed_runtime` activation mode
- start training, inspect persisted adapter history, activate an adapter into a derived model, publish the adapter package, and remove an activated derived model

The same workflow is available through the public `melix` CLI:

```bash
swift run melix lora list

swift run melix lora run \
  --model-id unsloth/gemma-4-E4B-it-MLX-8bit \
  --dataset-uri /absolute/path/to/dialogue-training-package \
  --adapter-name dialogue-extraction-quality \
  --training-mode auto \
  --activation-mode adapter_backed_runtime \
  --eval-suite event_extraction \
  --eval-dataset-id top200.event-extraction.top20.v1 \
  --eval-dataset-root /absolute/path/to/evaluation \
  --scoring-mode event_extraction_weighted_f1 \
  --output-dir /absolute/path/to/lora-run \
  --json

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

`melix lora run` is the recommended operator path for quality training and
acceptance. It trains the adapter, activates it, evaluates base versus the
fresh adapter manifest, and writes compare summary/sample artifacts under the
run output directory. `--training-mode auto` resolves quantized model ids such
as 4-bit and 8-bit MLX repos to QLoRA; non-quantized targets resolve to LoRA.

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
- `preference_pair`
- `agentic_tool_trace`

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

Example `samples.jsonl` for `preference_pair`:

```jsonl
{"prompt":"Choose the more helpful answer.","chosen":"Give a direct answer with the relevant command.","rejected":"Add unrelated background before answering."}
{"prompt":"Pick the safer response.","chosen":"Explain the limitation and offer a supported path.","rejected":"Pretend an unsupported feature exists."}
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
  "target_modules": "attention_mlp",
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

Supported `training_mode` values:

- `lora`: supervised fine-tuning with LoRA adapters
- `qlora`: supervised fine-tuning against a quantized base model
- `dora`: supervised fine-tuning contract with DoRA adapter metadata
- `dpo`: preference-mode contract requiring `preference_pair` samples
- `orpo`: preference-mode contract requiring `preference_pair` samples
- `cpt`: continual-pretraining contract requiring `text_completion` samples

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
- `agentic_tool_trace` packages are accepted by SFT modes and projected into a
  trainer-facing `chat_messages` snapshot while preserving the original
  normalized trace rows in sibling `agentic-traces.*.jsonl` evidence files
- agentic SFT projection splits a source trace into one trainer row per
  trainable assistant tool-call span plus one final-answer row; each row records
  `response_only_boundary` metadata and defaults to `response_only=true` with
  `mask_prompt=true` so user, system, and tool-observation context does not
  receive loss
- agentic trace SFT keeps the operator-facing SFT `training_mode` (`lora`,
  `qlora`, or `dora`) but adapter receipts and runner configs record
  `training_objective=agentic_sft` and
  `dataset_contract=agentic_tool_trace`; incompatible explicit
  `training_objective` overrides fail before backend execution
- adapter receipts keep the source trace count in `dataset_sample_count` and
  record expanded trainer rows in `trainer_dataset_sample_count`
- Hugging Face dataset materialization is cached under `<jobs_root>/datasets/<cache-key>`
- Melix supports `lora`, `qlora`, `dora`, `dpo`, `orpo`, and `cpt` through the same `train_lora` surface
- `dora` records `adapter_algorithm=dora` and `dora_enabled=true` in the adapter manifest
- `dpo` and `orpo` require `preference_pair` datasets and record `training_objective=preference`
- `cpt` requires `text_completion` datasets and records `training_objective=continual_pretraining`
- this slice defines worker-owned mode and dataset contracts; DPO, ORPO, and CPT optimizer-loop breadth remains bounded by the active local runner implementation
- if `hf_valid_split` is provided, the normalized dataset snapshot persists the explicit validation source
- Melix expands compact target modules or preset groups into family-specific module paths
- Gemma 4 VLM snapshots that expose `text_config.model_type == "gemma4_text"` are accepted through the
  component-scoped `text_backbone` LoRA surface; the source model remains a VLM entry, and adapter
  artifacts record `adapter_scope=text_backbone`, `training_surface=text_backbone`,
  `component_model_type=gemma4_text`, and `component_family=gemma`
- supported preset groups currently include `attention`, `mlp`, `attention_mlp`, and `full`; `qwen` plus `kimi` also accept `qkv`, `gemma` also accepts `gated_mlp`, experimental `mixtral` accepts `experts`, and experimental `qwen3moe` accepts `qkv`, `experts`, and `attention_experts` (`full` is an alias for `attention_experts`)
- dense-family defaults stay on the family-owned `attention_mlp` baseline, while experimental MoE families default to `attention` unless the operator explicitly opts into expert modules
- quantized LoRA and QLoRA reject embedding, LM head, and output-projection target modules; keep quantized runs on attention or expert projection targets
- Melix writes a normalized dataset snapshot under `<jobs_root>/train_lora/<job_id>/`
- Melix emits the stages `resolve_source`, `validate_dataset`, `normalize_config`, `prepare_training_data`, `apply_lora`, `train`, `write_adapter`, and `write_manifest`
- component-scoped multimodal adapter receipts include `multimodal_lora_nan_guard_triggered`,
  `unexpected_frozen_param_count`, `adapter_checkpoint_bytes`, and `adapter_freeze_audit`; any
  serialized vision, audio, embedding, projector, or full base tensor outside the intended
  LoRA/DoRA target surface fails export before the adapter manifest is written
- the completed artifact is `train_lora.adapter.json` with schema `melix.lora_adapter_package.v1`

## Family Support Boundaries

Stable LoRA training families:

- `llama`
- `qwen`
- `gemma`
- `kimi`

Stable component-scoped LoRA surfaces:

- Gemma 4 VLM `text_backbone` when local model discovery records
  `melix.lora.adapter_scope=text_backbone`, `melix.lora.training_surface=text_backbone`,
  `melix.lora.component_model_type=gemma4_text`, and `melix.lora.training_ready=true`

Experimental LoRA training families:

- `mixtral` is exposed through separate MoE hooks and currently defaults to `attention` targets only; expert-module presets are available but should be treated as an operator-tuned path
- `qwen3moe` is exposed through experimental MoE hooks, defaults to `attention`, and supports `qkv`, `experts`, `attention_experts`, and `full`; `full` is an alias for `attention_experts`; expert-module presets expand through `mlp.experts.N.{gate,up,down}_proj`, require `melix.text.moe.expert_count` confirmed from live local model config, and require repeatable operator evidence before wider promotion

Explicitly unsupported or not-yet-productized LoRA families:

- `deepseek-mla`
- `mistral4`
- `nemotron-h`
- embedding-family models and other non-text capability classes
- Gemma 4 `vision_encoder`, `multimodal_projector`, and audio components; these require separate
  adapter contracts and are intentionally not marked training-ready by the registry

Operator guidance:

- prefer the family default unless you have repeatable evaluation evidence for a narrower preset
- use `attention` or `qkv` first when validating a new dense family rollout
- treat MoE expert targeting as experimental and record compare evidence before promoting an adapter for wider use
- if the registry marks `melix.lora.training_ready = false`, do not expect `train_lora` to accept that family yet
- for component-scoped models, inspect `melix.lora.adapter_scope` and `melix.model.components` before
  training; do not infer vision or projector support from the presence of a multimodal model card

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
- component-scoped non-text adapters, including Gemma 4 `text_backbone` adapters, must use
  `adapter_backed_runtime`; fused activation is rejected until Melix has a fused multimodal component
  adapter contract
- the completed artifact is `activate_adapter.derived_model.json` with schema `melix.derived_text_model.v1` under `<jobs_root>/activate_adapter/<job_id>/`
- the result includes `derived_model_id`, `derived_model_path`, `activation_duration_ms`,
  `adapter_set_hash`, and adapter scope metadata when present
- the activated model is registered into the control-plane catalog with the source model kind preserved

## Verify Serving Behavior

Confirm the activation result before using the model for traffic:

1. inspect the activation manifest and confirm `schema_version == "melix.derived_text_model.v1"`
2. confirm `activation_mode` matches the requested mode, either `fused_derived_model` or `adapter_backed_runtime`
3. confirm `melix.adapter_set_hash` is present and differs from incompatible adapters
4. for component-scoped adapters, confirm `adapter_scope` and `training_surface` match the source model metadata
5. load the derived model through the expected runtime path
6. compare one controlled prompt against the base model and verify the derived model behavior changes in the expected direction

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

When `--manifest-path` is used, Melix reads the manifest and infers the export kind from its
`schema_version` / `artifact_kind` / `activation_mode` fields:

- `melix.lora_adapter_package.v1` or `artifact_kind=adapter` → adapter export
- `melix.derived_text_model.v1` or `activation_mode=fused_derived_model` → merged export
- `converted_model_bundle` / `quantized_model_bundle` → merged export

For ambiguous manifests or when you want to be explicit, pass `--export-kind (adapter|merged)`.
The flag also catches operator mistakes — `--export-kind merged` combined with `--adapter-path`
is rejected with a clear usage error instead of being silently coerced.

Expected publish behavior:

- adapter export uploads a staged adapter bundle containing the adapter manifest plus adapter weights and config
- merged export uploads the fused derived-model directory and rejects `adapter_backed_runtime` manifests
- upload receipts record `export_artifact_kind`, `published_repo`, publish backend, and `parent_lineage`
- registry snapshots show adapter and merged publish lineage so operators can confirm which local artifact produced each remote repo
- `swift run melix lora list` now includes published repo and publish artifact kind in the operator-readable table

Melix sets `distribution_contract` in the upload receipt to distinguish three artifact categories:

- `adapter_only` — adapter package (weights + config, no base model)
- `merged_model` — fused text-only derived model directory
- `merged_multimodal` — fused multimodal derived model directory containing processor config files (`processor_config.json`, `preprocessor_config.json`, or `image_processor.json`); `processor_config_files` lists the detected configs so the bundle can be reloaded without missing preprocess metadata

When publishing a fused multimodal model, Melix detects processor config files on disk and records them in the receipt automatically — no operator flag is needed. Use `melix lora publishes show --job-id JOB_ID` to confirm `distribution_contract` and `processor_config_files` after a publish.

### Inspect Publish History

Every completed upload is surfaced as a `publishes` entry in the registry snapshot, parallel to
`adapters` / `derived_models` / `experiment_groups`. CLI operators can browse publish lineage
directly:

```bash
swift run melix lora publishes list

swift run melix lora publishes show \
  --job-id model-ops-0100
```

`publishes list` emits a fixed-width `JOB_ID / KIND / TARGET_REPO / SOURCE_JOB / ADAPTER/DERIVED`
table. `publishes show` renders the full lineage (export kind, distribution contract, target
URL / ref, source artifact path, source manifest path, adapter or derived-model identity,
activation mode, published files, upload receipt path). Both accept `--json` for pipeline use.

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
