# Task Plan

## Goal

Advance `M12.2` by adding metadata-driven text and MoE family adapters so larger text-model
families can be discovered, routed, and exercised through deterministic live-path verification.

## Scope

- add text-family adapter metadata for dense and MoE text families
- detect family identity from `config.json`, explicit metadata overrides, and path heuristics
- route larger text and MoE families through `python_text_compatibility` while preserving the
  default `swift_text` seed path for the base dev text model
- surface family-specific parser, attention, RoPE, and MoE declarations through registry snapshots,
  support-matrix output, and control-plane summaries
- add focused unit and integration coverage for scanned-model metadata, routing, and live endpoint
  exercise of the targeted family matrix

## Measurement Points

- discovered text models must carry stable adapter metadata including route kind, family ID,
  architecture, parser support, attention profile, RoPE profile, and MoE-specific declarations
- control-plane summaries must preserve text-family metadata and route advanced families through
  `python_text_compatibility`
- the family support matrix must distinguish contract-only from live-verified text and MoE rows
- live integration coverage must prove that targeted text-family overrides can be loaded and served
  through the HTTP text-generation path using repository-owned deterministic workers

## Phases

1. Text-family adapter contract and detection
   - status: completed
   - evidence:
     - add adapter descriptors for the targeted dense and MoE families
     - resolve family identity from explicit overrides, `config.json`, and path-based fallback
     - project capability metadata and family-specific declarations into worker model specs
2. Control-plane propagation and support-matrix expansion
   - status: completed
   - evidence:
     - preserve discovered text-family metadata through registry snapshot sync and worker
       preparation
     - expand the repository-owned family support matrix and runbook to include text and MoE rows
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - add focused Python, Swift, and integration coverage for routing and live-path family
       exercise
     - record changed-line coverage at or above `95%`, update `progress.md`, and close `M12.2`
       only after the family matrix and routing behavior are test-backed

## Acceptance

- expanded dense and MoE text families are scanned with adapter metadata instead of generic text
  fallback
- advanced families route through `python_text_compatibility` while the base dev text seed remains
  `swift_text`
- the support matrix, tests, and runbook evidence cover both contract and live-path status for the
  targeted family matrix

## Risks

- over-broad fallback heuristics could collapse distinct families into one generic text profile and
  hide parser or routing differences
- changing the default dev text route would break existing repository-wide phase-0 assumptions and
  unrelated integration tests
- support-matrix rows without live verification would overstate runtime compatibility for newly
  added families

## Outcome

- m12_2_text_and_moe_family_adapters_completed
