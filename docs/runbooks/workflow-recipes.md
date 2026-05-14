# Workflow Recipes And URI Inspection

Melix workflow recipes are versioned templates for common local runtime tasks.
They do not introduce a second execution engine. A recipe resolves operator
inputs, emits a concrete `melix.pipeline.v1` plan, and applies that plan through
the existing pipeline runner.

## URI Inspection

Use URI inspection when an operator has a source but not yet a full Melix
command:

```bash
melix uri inspect hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit --json
melix uri inspect hf://dataset/Jax-dan/HundredCV-Chat --json
melix uri inspect /path/to/local-model --json
```

Inspection is read-only. It returns candidate kinds, confidence, normalized
locators, warnings, recommended Melix arguments, and ambiguity metrics.
Ambiguous bare `org/repo` inputs return both model and dataset candidates so
operators can choose an explicit `hf://model/...` or `hf://dataset/...` URI.

`melix uri import` is the mutating companion. Use `--dry-run` first to inspect
the command that would run:

```bash
melix uri import hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit --dry-run --json
```

## Built-In Recipes

The initial built-in catalog includes:

| Recipe | Tasks |
|---|---|
| `import.hf-mlx-model` | `model_import` |
| `import.local-mlx-model` | `model_import` |
| `dataset.hf-eval` | `dataset_import`, `eval` |
| `train.lora.local-dataset` | `train_lora` |
| `benchmark.eval.smoke` | `benchmark`, `eval` |
| `adapter.compare.evidence` | `eval_compare` |

List and inspect recipes:

```bash
melix recipes list --json
melix recipes list --task model_import --json
melix recipes show import.hf-mlx-model --json
melix recipes validate import.hf-mlx-model --json
```

## Planning

Planning renders a concrete pipeline without executing it:

```bash
melix recipes plan import.hf-mlx-model \
  --set repo_id=mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --set revision=main \
  --output .runtime/import-qwen.pipeline.json \
  --json
```

The emitted pipeline uses existing command IDs only, such as
`estimate.import`, `model.hub.download`, `model.roots.rescan`, `lora.train`,
`bench.run`, and `eval.run`.

## Applying

Recipe application writes a generated pipeline and routes through
`melix pipeline run`, preserving dry-run, resume, from-step behavior, and normal
pipeline receipts:

```bash
melix recipes apply import.hf-mlx-model \
  --set repo_id=mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --dry-run \
  --json
```

Generated pipeline files and receipts live under `MELIX_HOME/workflow-recipes/`
unless `MELIX_HOME` points at a worktree-local runtime home. Melix stores each
recipe application in a UUID-named run directory under the recipe ID and keeps
the newest 20 run directories for that recipe. Older UUID run directories are
removed before a new apply executes, while non-UUID files or operator-managed
notes in the recipe directory are left untouched.

## Provenance

Planned pipelines include:

- `source_recipe_id`
- `source_recipe_version`
- `source_recipe_digest`
- `source_uri_digest` when a URI-like input is present

Pipeline step receipts also preserve the resolved step metadata already written
by the pipeline runner. Deeper propagation into every downstream manifest should
continue to follow the durable job and artifact model as it matures.
