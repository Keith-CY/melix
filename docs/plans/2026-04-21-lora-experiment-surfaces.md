# LoRA Module 3 (Slice 3.3) — Experiment surfaces (issue #14)

## Context

Issue [#14](https://github.com/Keith-CY/melix/issues/14) tracks Module 3 from `docs/plans/2026-04-16-lora-capability-modules-and-commit-plan.md`: teach the operator surfaces to discover, compare, and resume LoRA experiment groups.

The backend halves already landed:

- **Slice 3.1 (PR #45)** — `TrainingMetrics` carries checkpoint + resume fields; the `melix.lora_adapter_package.v1` manifest persists them.
- **Slice 3.2** — `worker/productization/lora_experiment_store.py` writes per-run records and a per-root index that computes `best_known_adapter` by loss, a `resume_ready_run_ids` list, and `checkpoint_lineage` entries. `worker/model_ops/job_registry.py::_experiment_groups()` surfaces the index via the `registry_snapshot` RPC. The menubar already renders a summary card via `RuntimeLoraExperimentGroupState`.

This doc covers **Slice 3.3** — the operator-facing CLI and menubar surfaces that turn the index into something usable without opening the JSON by hand.

## Scope

**In (one PR, three commit slices):**

- **3.3A — CLI `lora experiments list` / `show`.** Two new subcommands that read `experiment_groups` out of the existing `registry_snapshot` payload. `list` renders a fixed-width `GROUP_ID / TITLE / RUNS / BEST_LOSS / RESUME_READY` table; `show --group-id ID` renders the per-group detail (runs list, resume-ready roster, best-known adapter block with the `melix lora resume` pointer). Both support `--json`.
- **3.3B — CLI `lora resume --group-id ID`.** Resolves `best_known_adapter.manifest_path` via the snapshot, reads that manifest off disk to pull dataset / adapter / preset defaults, applies operator overrides, and invokes `train_lora` with `resume_manifest_path` set. Unknown-group, no-best-adapter, and missing-manifest paths surface explicit errors.
- **3.3C — Menubar experiment group detail.** `RuntimeLoraExperimentGroupState` gains `bestRunID`, `resumeReadyRunIDs`, `checkpointLineage` fields (with a new `RuntimeLoraCheckpointLineageEntry`). `DesktopWorkspaceShellView`'s Experiment Groups card renders a checkpoint-lineage disclosure and a "Resume From Best" button that preloads `loraResumeFromManifestPath` + `loraExperimentGroupID` into the training form. A new `resume_manifest_path` key flows through `loraTrainingExt()` into the `train_lora` RPC.

**Out:**

- Backend changes — 3.1 and 3.2 already shipped. `lora resume` and `experiments show` render only the fields currently in the snapshot payload.
- Proto schema changes — `experiment_groups` is already a JSON dict in the snapshot RPC; no typed proto surface is needed for v1.
- Env-gated real-training experiment test — the Phase 8 acceptance bundle already exercises experiment index population end-to-end.

## Design notes

### CLI style: `--group-id` not positional

The existing CLI `ArgumentCursor` rejects non-`--flag` tokens, and all other lora subcommands use `--flag value` throughout. To stay consistent rather than thread a one-off positional path through the cursor, `experiments show` and `resume` take `--group-id ID`.

### Per-run detail in `experiments show`

The snapshot's `checkpoint_lineage` entries carry `{run_id, checkpoint_count, resume_ready}` — that's what the `Runs (N):` list renders. Per-run `loss` / `status` / `preset` are not in the current snapshot, and surfacing them would require enriching `_checkpoint_lineage_entry` in Python (a backend change explicitly out of scope). The best-known-adapter block still reports loss + manifest path, so the operator has the key comparison signal without a deeper backend dive.

### Dataset-uri inheritance on resume

`lora resume` pulls `dataset_uri` from the recommended run's manifest by default — i.e. "resume from where the best run left off." An operator who wants to swap datasets must pass `--dataset-uri` explicitly; this is documented in the subcommand help text and validated via `loraResumeAppliesCLIOverrides`.

### Registry priming

`.loraResume`, `.loraExperimentsList`, and `.loraExperimentsShow` all join the set of commands that get a registry-root rescan before the main call (same behavior as `.loraList`). Tests filter priming calls out via `ext["melix.registry_rescan"]`.

### Menubar wiring

The "Resume From Best" button only mutates `RuntimeViewModel` form state — it does not call out to the CLI `lora resume` logic. That keeps the two code paths independent: the CLI `resume` is a one-shot discovery + training operation, the menubar `Resume From Best` is form-preload. Concurrent invocation is safe because each resolves against its own snapshot read.

## Critical files

```
Sources/MelixCLICore/MelixCLI.swift                                         (+~260 lines)
Sources/MelixCLICore/MelixCLICommandCodec.swift                             (+~8 lines)
Tests/MelixCLITests/MelixCLIParserTests.swift                               (+~75 lines)
Tests/MelixCLITests/MelixCLIRunnerTests.swift                               (+~230 lines)
apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift            (+~45 lines)
apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift (+~30 lines)
apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift           (+~85 lines)
docs/plans/2026-04-21-lora-experiment-surfaces.md                           (this file)
```

## Verification

1. `make swift-test` — all lora parser + runner + menubar view-model tests pass, including the new `lora experiments list/show`, `lora resume`, `experimentGroupStateSurfacesResumeReadyAndLineage`, and `resumeFromManifestFlowsIntoTrainingExt` coverage.
2. `make py-test` — unchanged; no worker-side changes in this slice.
3. `make proto-check` — clean; no proto changes.
4. Manual smoke (optional, after `make swift-build`):
   - `melix lora experiments list --json`
   - `melix lora experiments show --group-id <id> --json`
   - `melix lora resume --group-id <id> --json`

## Risks

- **Unknown group handling.** `experiments show` / `resume` surface `missingRequired` errors listing the known group ids — avoids silent empty output. Covered by `loraExperimentsShowErrorsForUnknownGroup`.
- **Missing best-known adapter.** A group where every run reported infinite loss has `best_known_adapter.manifest_path == ""`. `resume` refuses cleanly with a pointer to `experiments show`. Covered by `loraResumeErrorsWhenGroupHasNoBestAdapter`.
- **Stale manifest path.** The manifest path in the snapshot could be deleted out-of-band. `resume` reads the file at invocation time; missing-file surfaces as a `runtime` error carrying the path. Covered by `loraResumeErrorsWhenManifestMissing`.
- **Dataset-uri drift on resume.** Documented in the subcommand help + design notes above; tested via `loraResumeAppliesCLIOverrides`.
