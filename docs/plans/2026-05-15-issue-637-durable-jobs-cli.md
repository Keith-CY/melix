# Durable Jobs CLI Surface

## Goal

Close issue #637 by making Melix long-running work discoverable through a
durable operator contract:

- `melix jobs list`
- `melix jobs show <id>`
- `melix jobs logs <id> --follow`
- `melix jobs artifacts <id>`
- `melix jobs cancel <id>`
- `melix monitor`

The first implementation slice formalizes the CLI surface on top of existing
run records and the already durable LoRA model-ops adapter manifests rather
than introducing a second execution engine.

## Scope

- Add a `jobs` CLI namespace that reads persisted `run-record.json` entries
  from `$MELIX_HOME/jobs` or an explicit `--from` path.
- Include completed LoRA training jobs by adapting
  `jobs/model-ops/train_lora/<job_id>/train_lora.adapter.json` into the same
  job status, logs, and artifact schema.
- Return machine-readable job status, phase, timestamps, error, logs, artifact
  paths, cancellation state, and record paths from `jobs show --json`.
- Make `jobs logs --follow` delegate to the existing redacted diagnostics log
  snapshot behavior.
- Add `jobs artifacts` so operators can discover all paths referenced by a job,
  including the artifact root, record path, logs, and explicit artifacts.
- Add `jobs cancel` as a durable local cancellation contract. For active jobs,
  always write a cancellation request file next to the run record so future
  workers can poll the same contract. Direct process signaling is intentionally
  disabled in this slice so stale or reused PID metadata cannot terminate an
  unrelated local process. Terminal jobs return a non-mutating status.
- Keep `runs` as the lower-level run-record export/report surface.

## Architecture

`run-record.json` remains the persisted source of truth for benchmark,
evaluation, failed, and currently observed long-running work. LoRA training
already persists adapter manifests under the model-ops jobs root, so the job
surface also adapts `train_lora.adapter.json` into `melix.job_status.v1`
without changing the worker protocol:

- `job_id` maps to `run_id`.
- `command` maps from the redacted reproduction command.
- `status` maps from the run record status.
- `phase` comes from `phase`, `stage`, or the latest probe/progress metadata
  when present, otherwise it falls back to `status`.
- `logs` and `artifacts` are resolved from the same local artifact paths used
  by diagnostics.
- `cancellation` is represented by `cancel-request.json` beside the record.
- For LoRA training manifests, `job_id`, `source_model`, `dataset_id`,
  `weights_path`, `adapter_config_path`, and related manifest paths are exposed
  through the same `jobs show` and `jobs artifacts` response shape.

This is intentionally compatible with future asynchronous worker execution:
workers can keep writing the same record shape and observe the same cancel
request file without changing the operator CLI.

## Probes And Metrics

- Observability mode: `minimal`. The slice exposes existing persisted state
  and does not add runtime telemetry collection.
- Success metrics:
  - `jobs show --json` includes status, phase, timestamps, error, logs, and
    artifact paths for benchmark/evaluation run-record fixtures and a LoRA
    training manifest fixture.
  - `jobs logs --follow --json` preserves existing follow/redaction semantics.
  - `jobs cancel --json` writes a cancellation request for active jobs,
    reports direct process signaling as disabled, and reports terminal jobs as
    not cancelable.
  - Focused Swift CLI tests cover the new parser and runner paths.
- Probe overhead: `N/A`; this is local metadata inspection and cancel request
  persistence, not a benchmark/evaluation evidence path.

## Verification

Focused local checks:

```bash
swift test --filter MelixCLIParserTests
swift test --filter MelixCLIRunnerTests
swift test --enable-code-coverage --filter MelixCLIRunnerTests
```

Repository gates before merge remain:

```bash
make swift-test
make py-test
make integration-test
```

## Acceptance

- Benchmark and evaluation runs that persist a run record are visible in
  `melix jobs list`.
- LoRA training runs that persist a `train_lora.adapter.json` model-ops
  manifest are visible in `melix jobs list`.
- `melix jobs show <id> --json` returns status, phase, timestamps, error,
  logs, artifact paths, and cancellation state.
- `melix jobs logs <id> --follow` streams or polls the current redacted log
  snapshot using the existing diagnostics behavior.
- `melix jobs cancel <id> --json` records a durable cancellation request and
  does not directly signal persisted PIDs.
- Failed jobs still expose preserved logs and artifacts through `jobs show`,
  `jobs logs`, and `jobs artifacts`.
