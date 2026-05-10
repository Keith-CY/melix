# Sparrow And LocalAI Reference Scan

## Purpose

This reference scan records product and architecture lessons from Sparrow and
LocalAI that are relevant to Melix. It is the durable repository record for
GitHub issue [#643](https://github.com/Keith-CY/melix/issues/643).

The scan has already been converted into follow-up Melix issues. Closing this
scan does not close those follow-up issues; it records the source rationale,
priority order, and adoption guardrails for future plans.

## Sources

| Source | Reference Scope |
|---|---|
| [Sparrow](https://github.com/katanaml/sparrow) | Structured local document intelligence, schema-shaped task requests, validation, hints, backend comparison evidence |
| [LocalAI website](https://localai.io/) | Operator-facing model gallery, runtime settings, backend discovery, monitoring and diagnostics patterns |
| [LocalAI repository](https://github.com/mudler/LocalAI) | Gallery implementation, importers, async gallery operations, runtime settings, backend capability surfaces |

Issue #643 captured the concrete source paths used during the scan. Treat those
paths as evidence pointers, not implementation dependencies.

Sparrow evidence pointers:

- `README.MD`
- `sparrow-ml/llm/api.py`
- `sparrow-ml/llm/engine.py`
- `sparrow-ml/llm/pipelines/sparrow_parse/sparrow_parse.py`
- `sparrow-ml/llm/pipelines/sparrow_parse/sparrow_validator.py`
- `sparrow-ml/llm/ollama_vs_mlx_test_results.md`
- `sparrow-ml/llm/sparrow_hints_test_results.md`

LocalAI evidence pointers:

- `docs/content/features/model-gallery.md`
- `docs/content/features/backends.md`
- `docs/content/features/runtime-settings.md`
- `docs/content/features/backend-monitor.md`
- `docs/content/features/api-discovery.md`
- `core/gallery/*`
- `core/gallery/importers/*`
- `core/services/galleryop/*`
- `core/config/runtime_settings*.go`
- `core/config/backend_capabilities.go`
- `core/http/routes/localai.go`
- `pkg/model/watchdog.go`

## Findings From Sparrow

Sparrow is useful to Melix as a reference for structured local task interfaces
and evidence-friendly evaluation workflows.

Relevant lessons:

- Keep task requests schema-shaped so operators can run reproducible document
  and evaluation jobs without relying on hidden prompt conventions.
- Separate task hints from base prompts so domain guidance can be inspected,
  versioned, and compared.
- Preserve validation results next to task outputs so failures are visible as
  product evidence, not just logs.
- Keep backend comparison notes simple and portable enough to paste into issue
  and pull request evidence.
- Use runtime/debug examples that an operator can copy without learning the
  internals first.

Melix follow-ups derived from these lessons:

- [#639](https://github.com/Keith-CY/melix/issues/639): add schema and hints
  support for reproducible evaluation tasks.
- [#640](https://github.com/Keith-CY/melix/issues/640): persist run metadata
  and generate Markdown comparison reports.
- [#641](https://github.com/Keith-CY/melix/issues/641): add runtime settings
  and machine-readable discovery surfaces.

## Findings From LocalAI

LocalAI is useful to Melix as a reference for operator UX and local runtime
productization.

Relevant lessons:

- Model setup should support recipe/gallery style flows and URI importers, not
  only manual path entry.
- Long-running local operations need durable job state, logs, cancellation, and
  artifact discovery.
- Runtime settings should be persisted to disk and exposed through predictable
  machine-readable surfaces.
- Backend capabilities and discovery should be inspectable by CLI, app, and
  automation clients.
- Resource estimates, monitoring, logs, traces, and debug bundles should be
  operator-facing features, not ad hoc support scripts.

Melix follow-ups derived from these lessons:

- [#636](https://github.com/Keith-CY/melix/issues/636): add recipe/gallery
  registry and URI importers for local workflows.
- [#637](https://github.com/Keith-CY/melix/issues/637): add durable async jobs
  with logs, cancellation, and artifact discovery.
- [#638](https://github.com/Keith-CY/melix/issues/638): add Apple Silicon
  unified-memory estimates and fit checks.
- [#641](https://github.com/Keith-CY/melix/issues/641): add runtime settings
  and machine-readable discovery surfaces.
- [#642](https://github.com/Keith-CY/melix/issues/642): add operator
  diagnostics: doctor, monitor, logs, and debug bundles.

## Follow-Up Issues

| Issue | Workstream | Primary Reference |
|---|---|---|
| [#636](https://github.com/Keith-CY/melix/issues/636) | Recipe/gallery registry and URI importers | LocalAI gallery and importers |
| [#637](https://github.com/Keith-CY/melix/issues/637) | Durable async jobs with logs, cancellation, and artifacts | LocalAI gallery operations |
| [#638](https://github.com/Keith-CY/melix/issues/638) | Apple Silicon unified-memory estimates and fit checks | LocalAI operator safety patterns |
| [#639](https://github.com/Keith-CY/melix/issues/639) | Schema and hints support for reproducible evaluation tasks | Sparrow schema and hints workflow |
| [#640](https://github.com/Keith-CY/melix/issues/640) | Run metadata and Markdown comparison reports | Sparrow comparison evidence |
| [#641](https://github.com/Keith-CY/melix/issues/641) | Runtime settings and machine-readable discovery surfaces | LocalAI runtime settings and discovery |
| [#642](https://github.com/Keith-CY/melix/issues/642) | Operator diagnostics: doctor, monitor, logs, and debug bundles | LocalAI monitoring and diagnostics |

## Priority Order

Use this order when turning the scan into implementation work:

1. [#638](https://github.com/Keith-CY/melix/issues/638) unified-memory
   estimates and fit checks.
2. [#637](https://github.com/Keith-CY/melix/issues/637) durable async jobs,
   logs, cancellation, and artifacts.
3. [#640](https://github.com/Keith-CY/melix/issues/640) run metadata and
   Markdown comparison reports.
4. [#636](https://github.com/Keith-CY/melix/issues/636) recipe/gallery registry
   and URI importers.
5. [#641](https://github.com/Keith-CY/melix/issues/641) runtime settings and
   discovery.
6. [#642](https://github.com/Keith-CY/melix/issues/642) operator diagnostics
   and debug bundles.
7. [#639](https://github.com/Keith-CY/melix/issues/639) schema and hints
   support for reproducible evaluation tasks.

The priority favors Apple Silicon operator safety first, then durable execution
and reusable evidence, then setup ergonomics and broader task structure.

## Adoption Guardrails

- Use Sparrow and LocalAI as product and architecture references only.
- Do not copy GPL-licensed Sparrow code into Melix.
- Do not expand Melix into LocalAI's broad multi-modal server scope by default.
- Keep Melix scoped to the local-first Apple Silicon runtime experience.
- Keep existing acceleration capability receipt work in
  [#350](https://github.com/Keith-CY/melix/issues/350) and
  [#352](https://github.com/Keith-CY/melix/issues/352); do not duplicate it
  inside the settings, discovery, or diagnostics follow-ups.

## Probe And Metrics Expectations

This scan is documentation-only and does not introduce a runtime probe. Each
follow-up implementation plan must define its own performance probes,
measurement points, and success metrics before broad implementation.

Expected probe coverage by follow-up:

| Follow-Up | Required Measurement Direction |
|---|---|
| #638 | model memory estimate latency, fit-check latency, estimate accuracy evidence, unsupported-model diagnostics |
| #637 | job creation latency, state restore latency, log/artifact listing latency, cancellation latency |
| #640 | run metadata write latency, report generation latency, report artifact size, comparison row count |
| #636 | recipe lookup latency, importer latency, registry parse cost, invalid URI diagnostics |
| #641 | settings read/write latency, discovery payload size, capability listing latency |
| #642 | doctor runtime, monitor sampling cost, debug bundle size, log collection latency |
| #639 | schema validation latency, hints load latency, invalid task diagnostics |

## Completion Criteria

Issue #643 is complete when this scan is committed, linked from the documentation
index, and the pull request records the docs-only verification. The follow-up
issues remain open until their own plans, probes, implementations, and evidence
land.
