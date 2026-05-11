# Evidence And Screenshots

This document records the command evidence used by the marketing copy. Captures
were run on 2026-05-07.

## CLI LoRA Smoke

Command:

```bash
python3 scripts/phase8_lora_cli_smoke.py --json
```

Result:

```text
ok: true
model_id: mlx-community/Qwen3.5-0.8B-OptiQ-4bit
positive.train.training_mode: qlora
positive.activate.activation_mode: adapter_backed_runtime
positive.compare.target_model_ids: melix-qwen35-acceptance
positive.export.output_path: /var/folders/.../eval-1-summary.csv
positive.export.row_count: 1
positive.remove_derived.derived_model_id: melix-qwen35-acceptance
negative.train_missing_adapter_name: --adapter-name is required for melix lora train.
negative.activate_missing_adapter_path: --adapter-path is required for melix lora activate.
negative.compare_missing_target: At least one --target-model-id or --target-adapter is required for melix eval compare.
negative.export_missing_job: No evaluation rows were found for job eval-missing.
negative.remove_missing_target: Either --derived-model-id or --manifest-path is required for melix lora remove-derived.
```

Marketing claims supported by this command:

- QLoRA is exercised by the CLI smoke.
- Adapter-backed runtime activation is exercised.
- Base-versus-derived evaluation compare is exercised.
- CSV export and negative validation paths are covered.

## Window UI LoRA Smoke

Command:

```bash
python3 scripts/phase8_lora_window_smoke.py --json
```

Result:

```text
ok: true
model_id: mlx-community/Qwen3.5-0.8B-OptiQ-4bit
positive.training_mode: qlora
positive.activation_mode: adapter_backed_runtime
positive.compare_target_model_ids: melix-qwen35-acceptance
positive.evaluation_export_format: summary.csv
positive.remove_derived_model_id: melix-qwen35-acceptance
negative.train_without_model_dispatch_count: 0
negative.activate_without_adapter_dispatch_count: 0
negative.compare_error: Select at least one compare target model before running Evaluation Compare.
negative.export_error: No evaluation summary rows are available for CSV export.
negative.remove_error: Select an activated adapter before removing its derived model.
```

Rendered Window UI controls included:

```text
Adapter Registry
Adapter-backed Runtime
Compare
Dataset & Mode
Evaluation
Fused Derived Model
Hugging Face Dataset
Local Package
QLoRA
Remove Derived Model
Run Comparison
Saved Jobs
Training History
Workflow Snapshot
```

Marketing claims supported by this command:

- The native App renders LoRA training controls.
- The App routes QLoRA training, adapter-backed activation, comparison,
  evaluation export, and derived-model removal through product actions.
- Guardrails prevent dispatching invalid training, activation, comparison,
  export, and removal actions.

## Native App Screenshot

Command:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python --extra mlx \
  pytest tests/integration/test_phase8_window_ui_acceptance.py::test_window_ui_acceptance_writes_bundle_and_screenshot \
  -q \
  --basetemp /private/tmp/melix-marketing-window-ui-acceptance
```

Result:

```text
1 passed in 52.50s
```

Generated screenshot:

```text
/private/tmp/melix-marketing-window-ui-acceptance/test_window_ui_acceptance_writ0/melix-home/acceptance/phase8/window-ui/2026-04-09T120000Z/window-ui.png
```

The `2026-04-09T120000Z` path segment is a fixture-controlled constant set by
the acceptance runner, not the date this command was executed.

Repository asset copied from that generated screenshot:

```text
docs/marketing/assets/window-ui-lora-workflow.png
```

Acceptance bundle fields:

```text
schema_version: melix.phase8.window_ui_acceptance.v1
surface: window_ui
model_id: melix-dev-qwen-local
derived_model_id: melix-dev-qwen-local-lora-c44d2b45
lora_train_job_id: model-ops-0042
lora_activate_job_id: model-ops-0046
bench_job_id: model-ops-0055
bench_matrix_job_id: model-ops-0060
evaluation_job_id: eval-0002
training_fixture: services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1
screenshot_path: /private/tmp/.../window-ui.png
ui_state.selected_surface: Server
ui_state.selected_server_lifecycle: Running
```

Marketing claims supported by this command:

- The screenshot is produced by the current native App renderer.
- The captured flow trains and activates a LoRA-derived model before rendering.
- The final App state shows a running local server with LoRA active.

## Asset Usage

Use `docs/marketing/assets/window-ui-lora-workflow.png` as the canonical App
screenshot for this copy set. It is suitable for README, docs, website drafts,
and launch material that discusses the local LoRA workflow.

If a future screenshot is needed, rerun the command above and replace the asset
only after confirming the new bundle includes `lora_train_job_id`,
`lora_activate_job_id`, `derived_model_id`, and `screenshot_path`.
