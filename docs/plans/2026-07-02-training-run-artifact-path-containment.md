# Training Run Artifact Path Containment

## Goal

Close the remaining issue #1498 follow-up by making local training admission
derive managed run artifact directories from sanitized model identity and by
refusing operator-supplied training output directories that escape the managed
Melix model-ops root before worker launch.

## Non-Goals

- Do not redesign the durable local training queue schema.
- Do not move trainability guardrail ownership out of the Python worker.
- Do not change completed #1499/#1500 guardrail or queue semantics beyond the
  path-containment admission gap.
- Do not copy reference implementation code from M-Courtyard.

## Context

- Relevant specs:
  - `docs/reference-scans/m-courtyard-lessons.md`
  - `docs/plans/2026-05-24-m-courtyard-improvement-roadmap.md`
  - `docs/plans/2026-05-24-training-parameter-safety-and-queueing.md`
- Relevant code paths:
  - `Sources/MelixCLICore/LocalTrainingQueueStore.swift`
  - `Sources/MelixCLICore/MelixCLI.swift`
  - `tests/MelixCLITests/LoraTrainingJobStoreTests.swift`
  - `tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Current constraints:
  - The Swift control plane owns durable queue admission before worker launch.
  - Python worker trainability rules stay the source of truth for model and
    dataset execution safety.
  - `MELIX_HOME` may be worktree-local; generated training artifacts must stay
    under that configured home's model-ops jobs root unless a later spec
    explicitly introduces a trusted external artifact root.

## Assumptions

- `modelID` in `LocalTrainingQueueAdmissionRequest` is the source model
  reference for both Hugging Face repository IDs and local absolute paths.
- Local absolute model paths may point outside `MELIX_HOME`; that is allowed for
  source reads, but generated run directories must not inherit raw absolute path
  components.
- Existing CLI `--output-dir` values for `melix lora train` are operator-supplied
  generated artifact paths and therefore must be contained under the managed
  model-ops training root.

## Work Plan

1. Add red tests for a pure `defaultTrainingRunName(modelRef:)` helper covering
   repository IDs, external local paths, very long names, and traversal strings.
2. Add red queue-admission tests proving default run directories stay under the
   managed training root and explicit escaping output paths fail with typed
   `path_escape_detected` evidence before worker launch.
3. Implement the helper and route queue default run directory construction
   through it while preserving stable queue IDs.
4. Add path-containment validation for explicit training output directories,
   including the sanitized candidate name in the typed refusal.
5. Verify focused Swift tests, changed-scope coverage, full pre-commit gate, and
   the scoped performance probe before PR update.

## Verification

```bash
swift test --filter 'LoraTrainingJobStoreTests/localTrainingQueueDerivesContainedRunNamesFromModelReferences|LoraTrainingJobStoreTests/localTrainingQueueRejectsEscapingRunDirectoriesWithTypedEvidence|MelixCLIRunnerTests/loraTrainUsesContainedDefaultOutputDirForLocalModelPaths'
swift test --filter 'MelixCLIRunnerTests/loraTrainPersistsDurableQueueAdmissionBeforeWorkerLaunch|MelixCLIRunnerTests/loraTrainRejectsBusyDurableQueueBeforeWorkerLaunch'
make swift-test
make py-test
make integration-test
```

Expected evidence:

- Focused tests fail before implementation and pass after implementation.
- Existing queue and LoRA train behavior remains green.
- Full local gates pass before commit.
- PR scoped performance report has `Status: ok`, `Regressions: 0`, and
  `Verification failures: 0`.

## Acceptance Criteria

- A public pure helper derives safe, bounded default training run artifact names
  from repository IDs and local paths without preserving raw absolute path
  components.
- Default admitted training queue run directories remain under
  `MELIX_HOME/jobs/model-ops/train_lora`.
- Explicit training output directories that escape the managed root return a
  typed `path_escape_detected` refusal before queue persistence or worker
  launch.
- Refusal evidence includes `path_escape_detected=true` and the sanitized
  candidate run name.
- Unit and CLI runner tests cover repository IDs, local absolute paths, long
  model names, traversal strings, and worker no-launch behavior.

## Rollback or Safe Exit

- Revert the helper, queue validation, and tests together. The previous queue
  behavior uses queue IDs for default directories and accepts explicit output
  directories unchanged.
