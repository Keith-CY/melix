# Run Metadata And Markdown Reports

## Goal

Persist operator-facing benchmark and evaluation run metadata and expose local
offline commands that turn completed runs into GitHub-ready evidence.

## Scope

- Write `run-record.json` beside benchmark, benchmark matrix, evaluation, and
  evaluation compare artifacts.
- Add offline CLI surfaces:
  - `melix runs list [--from PATH] [--json]`
  - `melix runs show <id> [--from PATH] [--json]`
  - `melix runs export <id> --format json|md [--from PATH] [--output PATH]`
  - `melix bench report --from PATH --format markdown|json`
  - `melix eval report --from PATH --format markdown|json`
- Redact sensitive command parameters and request metadata before persistence.
- Keep hosted telemetry, dashboards, and raw private dataset storage out of
  scope.

## Architecture

The Python worker remains the execution truth and writes run records at the
same point it writes benchmark/evaluation artifacts. The Swift CLI remains the
operator surface and reads `run-record.json` directly from `$MELIX_HOME/jobs`
or an explicit `--from` path, so `melix runs list --json` works without a
running Melix service.

`run-record.json` is an operator summary, not a replacement for
`run-evidence.json`. It points back to evidence, report, CSV, JSONL, telemetry,
and result artifacts while preserving the reproduction command, run identity,
target/input summary, metrics, resource summary, and known gaps.

Report commands derive Markdown and JSON from run records. Markdown output uses
the issue-ready sections from issue #640: Environment, Model/backend matrix,
Dataset/task matrix, Metrics table, Pass/fail summary, Reproduction commands,
Artifact links, and Known gaps.

## Probes And Metrics

- Worker run-record persistence records a `run_record_write` probe with elapsed
  milliseconds in each run record.
- CLI report generation records `record_scan_ms` and `markdown_render_ms` in
  JSON output and includes them in Markdown under Known gaps when the report is
  generated without persisted timing.
- Verification reports changed-line coverage for Swift CLI code and Python
  worker/report code. A probe smoke is included when relevant local probe tests
  are runnable.

## Acceptance

- Benchmark and evaluation stores write `run-record.json` for new completed
  runs.
- `melix runs list --json` reads local records from `$MELIX_HOME/jobs` without
  calling the control plane.
- `melix runs show` and `melix runs export` can render a single run as JSON or
  Markdown.
- `melix bench report --from ... --format markdown` and
  `melix eval report --from ... --format markdown` include reproduction
  commands, artifact paths, metrics, pass/fail summary, environment, and known
  gaps.
- Sensitive values are redacted in persisted metadata and rendered reports.
