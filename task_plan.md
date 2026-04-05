# Task Plan

## Goal

Advance `M12.4` by finishing conversion and packaging tooling now that typed model inspection and
health checking are stable operator workflows tied to model identity.

## Scope

- extend protocol-owned model inspection and doctor health payloads with stable typed fields
- project model identity, backend, family, source, and supported-task metadata through worker and
  control-plane inspect flows
- expose structured health summaries and actionable findings alongside the existing operator report
- surface explicit convert, quantize, and packaging result state through model-ops workflows and
  operator-visible UI state
- add focused coverage for typed inspect payloads, health severity mapping, and model-operation
  result summaries

## Measurement Points

- typed model inspection must expose stable identity fields including model kind, family or backend
  metadata, supported parsers, supported modalities, supported tasks, and source provenance
- health-check output must distinguish `healthy`, `warning`, `degraded`, and `failed` states
  without relying on markdown parsing
- conversion and quantized packaging results must remain tied to stable artifact metadata,
  manifest paths, smoke evidence, and source-model identity
- Window UI model tools must project structured inspect and health state without dropping the
  existing markdown report path

## Phases

1. Typed inspect and health contract
   - status: completed
   - evidence:
     - extend model-info and doctor payloads with stable typed identity and health fields
     - teach the worker to derive actionable health findings instead of markdown-only output
     - verify typed inspect and health paths with focused Python, control-plane, and menu-bar
       coverage at `100.00%` (`406/406` aggregate changed-line coverage)
2. Control-plane projection and operator inspect state
   - status: completed
   - evidence:
     - preserve typed inspect and health data through control-plane replies and XPC client helpers
     - project structured inspect and health state into the Window UI alongside the markdown report
3. Conversion and packaging workflow completion
   - status: in_progress
   - evidence:
     - expose explicit convert and packaging entrypoints through model-ops workflows
     - keep model-operation results tied to stable artifact and manifest metadata
4. Verification and milestone bookkeeping
   - status: pending
   - evidence:
     - add focused Python, Swift, and menu-bar regression coverage for typed inspect and health
       state plus model-operation result summaries
     - record changed-line coverage at or above `95%`, update `progress.md`, and close `M12.4`
       only after inspect, health, and conversion tooling are test-backed

## Acceptance

- inspect, health, and conversion tooling are operator-visible with stable typed result payloads
- health severity and findings remain actionable without requiring markdown parsing
- conversion and packaging results remain tied to stable model identity, artifact metadata, and
  verification evidence

## Risks

- inspect payload expansion could drift across worker and control plane if stable identity fields
  are duplicated instead of mapped from one source of truth
- doctor findings could over-report degraded state if thresholds are inferred from missing runtime
  evidence rather than explicit conditions
- conversion and packaging UX could collapse distinct artifact states into one generic model-op row
  if result metadata is not projected cleanly into the operator shell

## Outcome

- m12_4_conversion_packaging_in_progress
