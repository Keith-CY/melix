# Benchmark And Evaluation Runtime Report Experience

## Goal

Make benchmark and evaluation runs easier to follow and easier to share without
changing their product semantics. The CLI and Desktop surfaces should present a
single technical dashboard story: setup, live execution, completion, failures,
artifacts, and final reports.

## Scope

- Preserve existing `bench`, `bench matrix`, `eval`, and `eval compare` command
  shapes.
- Treat `report.json` and run evidence as the source of truth; terminal,
  Markdown, CSV, and Desktop views are derived presentations.
- Add an operator-facing terminal dashboard report for local run records.
- Add an interactive live terminal panel while direct benchmark, matrix,
  evaluation, and evaluation-compare commands are running.
- Add Desktop runtime monitor state for benchmark, matrix, and evaluation
  actions using the same run/report fields already available to the app.
- Keep the UI aligned with the Melix design system: sparse, data-first, SF
  Symbols, no marketing hero, no decorative media.

## Implementation

- Extend run-record reports with a terminal renderer that shows pass/fail
  summary, selected runs, primary metrics, artifacts, and report-generation
  probes.
- Add `terminal` as a report format for `melix bench report` and
  `melix eval report`; keep `markdown` and `json` unchanged.
- Add TTY-only live rendering for `bench run`, `bench matrix run`, `eval run`,
  and `eval compare`. The panel shows target, suites, elapsed time, a percent
  progress bar, staged progress, primary metric, artifact path, and error
  detail.
- Keep JSON and non-TTY output stable. `--json` never receives progress text,
  non-interactive stdout remains script-friendly, and `--no-live` disables the
  panel explicitly.
- Add Desktop diagnostics run monitor state that flips to `running` at command
  dispatch, records the start time, refreshes elapsed time while the run is
  active, and summarizes the selected run's phase, metrics, artifacts, failure
  state, stage timeline, progress, and recent execution events.
- Map existing control-plane `request_progress` and `bench_progress` events
  into the Desktop Run Monitor when they are available, with local command
  phases as the stable fallback.
- Insert the monitor above the existing diagnostics report snapshot so the first
  visible surface shows current execution and then the latest completed result.

## Probes And Metrics

- CLI report generation continues to record `record_scan_ms` and
  `markdown_render_ms`; terminal rendering is measured through focused unit
  tests rather than a runtime probe in this slice.
- TTY live rendering is covered by injected terminal capabilities and writer
  tests; no real terminal session is required for automated verification.
- Desktop records existing operation durations (`menu.ops_bench_ms`,
  `menu.ops_bench_matrix_ms`, and `menu.ops_eval_ms`) and maps them into the
  monitor's elapsed time.
- Metrics report for this slice is focused on changed renderer and view-model
  tests; no long-running benchmark or evaluation workload is required.

## Acceptance

- `melix bench report --from <path> --format terminal` prints a compact
  dashboard instead of Markdown.
- `melix eval report --from <path> --format terminal` does the same for
  evaluation records.
- Desktop Diagnostics shows an active monitor while Benchmark, Matrix, or
  Evaluation is running, including a step timeline and recent progress events,
  then a completed or failed monitor afterward.
- `melix bench run`, `melix bench matrix run`, `melix eval run`, and
  `melix eval compare` show live progress in an interactive terminal unless
  `--json`, `--no-live`, or a non-TTY stdout disables it.
- Focused Swift tests cover CLI renderer output and Desktop monitor state.
