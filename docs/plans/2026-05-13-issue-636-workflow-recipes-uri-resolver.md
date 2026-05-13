# Issue 636 Workflow Recipes And URI Resolver

## Goal

Implement the first Melix-native workflow recipe catalog and URI resolver for
GitHub issue #636. The feature must compose existing Melix command surfaces
instead of introducing a second execution engine.

Recipes should make common local Apple Silicon workflows discoverable,
inspectable, preflightable, and reproducible by emitting concrete
`melix.pipeline.v1` plans backed by existing command IDs.

## Scope

- Add typed CLI commands for:
  - `melix uri inspect URI [--json]`
  - `melix uri import URI [--model-id MODEL_ID] [--revision REV] [--dry-run] [--json]`
  - `melix recipes list [--task TASK] [--json]`
  - `melix recipes show RECIPE_ID [--version VERSION] [--json]`
  - `melix recipes validate PATH_OR_ID [--json]`
  - `melix recipes plan RECIPE_ID --set KEY=VALUE ... [--output PATH] [--json]`
  - `melix recipes apply RECIPE_ID --set KEY=VALUE ... [--dry-run] [--resume] [--from-step STEP_ID] [--json]`
  - `melix recipes init --from URI --task TASK [--output PATH] [--json]`
- Add a built-in recipe catalog with initial recipes that map to existing
  `model`, `dataset`, `lora`, `bench`, `eval`, `runs`, and `pipeline` commands.
- Add no-mutation URI inspection for Hugging Face model and dataset locators,
  local MLX model directories, LoRA adapter manifests, and local dataset files
  or directories.
- Add recipe planning that writes or returns a valid `melix.pipeline.v1`
  document.
- Route recipe application through the existing pipeline runner and preserve its
  dry-run, resume, from-step, receipt, and JSON v1 behavior.

## Non-Goals

- Do not copy external gallery schemas or code.
- Do not introduce arbitrary shell execution inside recipes.
- Do not replace existing model, dataset, LoRA, benchmark, evaluation, run, or
  pipeline commands.
- Do not implement the full durable job/log/cancel API tracked by #637.
- Do not build a UI-first marketplace.
- Do not add new runtime execution paths for unsupported formats such as GGUF.

## Architecture

The Swift CLI remains the user-facing recipe authority for this slice.

Recipe planning is intentionally a command-to-pipeline projection:

1. Load a built-in or file-backed recipe.
2. Validate schema and required inputs.
3. Resolve `--set` values into typed recipe inputs.
4. Run URI inspection for URI-backed inputs when needed.
5. Render a `melix.pipeline.v1` object containing only existing command IDs.
6. Optionally write the rendered pipeline to disk.
7. For `recipes apply`, execute the rendered pipeline through the existing
   `runPipeline` path.

The first slice keeps provenance in recipe planning output and the pipeline
inputs. Deeper propagation into every downstream run record or model manifest
can follow after the command path is stable and after #637 decides the durable
job envelope.

## Built-In Seed Recipes

- `import.hf-mlx-model`: estimate fit, download a Hugging Face model, rescan
  registry roots, and inspect the model.
- `import.local-mlx-model`: import a local MLX directory, rescan roots, and
  inspect the imported model.
- `dataset.hf-eval`: download a Hugging Face dataset for later evaluation use.
- `train.lora.local-dataset`: train LoRA from a local dataset package.
- `benchmark.eval.smoke`: run one benchmark and one evaluation against the same
  target.
- `adapter.compare.evidence`: run adapter comparison and export evidence without
  claiming #724 release-gate verdict enforcement.

## Performance Probes And Success Metrics

Record deterministic CLI-side metrics in JSON outputs where practical:

- `uri.inspect_ms`
- `uri.candidate_count`
- `uri.ambiguity_count`
- `recipe.lookup_ms`
- `recipe.schema_validate_ms`
- `recipe.plan_ms`
- `recipe.apply_start_ms`

The first implementation does not require a live runtime. Runtime-heavy probes
such as memory-fit timing are covered by existing command paths and should be
reported as `N/A` for docs-only or dry-run-only verification.

## Implementation Slices

### Slice 1: Plan

- Add this plan.
- Commit as documentation-only.
- Metrics: `N/A` because no runtime or executable path changes.
- Coverage: `N/A` because this slice is documentation-only.

### Slice 2: CLI Surface And Types

- Add typed command options and enum cases.
- Extend usage text, parser, command codec, and command-ID tests.
- Keep command execution stubbed or minimal only where required for compiler
  completeness.
- Verify focused parser and codec tests.
- Merge current `origin/main` after the commit.

### Slice 3: Resolver, Catalog, Planner, And Apply

- Add resolver and recipe-catalog implementation in `MelixCLICore`.
- Add built-in recipe definitions and validation.
- Add recipe planning to concrete `melix.pipeline.v1` JSON.
- Add `recipes apply` execution through the existing pipeline runner.
- Add focused runner tests for URI inspection, ambiguity, built-in listing,
  validation errors, planning, output writing, and dry-run apply.
- Add docs/runbook coverage for recipe authoring and operator workflow.
- Merge current `origin/main` after the commit.

## Verification Plan

Focused commands:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --filter MelixCLIParserTests

HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --filter MelixCLIRunnerTests
```

Changed-scope coverage should be measured before the final PR handoff. If local
Swift coverage is blocked by host toolchain limits, record the exact blocker and
let CI provide the broader gate.

PR evidence must keep the required headings from `.github/pull_request_template.md`
and validate with `scripts/validate_pr_evidence.py`.

## Acceptance

- Built-in recipes can be listed, shown as JSON, validated, planned, and dry-run.
- Planning emits a valid `melix.pipeline.v1` with existing command IDs only.
- URI inspection returns structured candidates and does not mutate local state.
- Ambiguous URI inspection returns multiple candidates.
- Recipe application reuses pipeline receipts and dry-run behavior.
- Sensitive values are redacted in public arguments and outputs.
- The final PR links issue #636 and reports coverage, metrics, local commands,
  known gaps, CI state, and performance-report state.
