# Task Plan

## Goal

Close `M8.11` by defining a repository-owned packaging target matrix for Apple Silicon delivery
variants so Melix can differentiate `launch_agents`, `homebrew`, and `.app bundle` outputs without
splitting product identity, runtime semantics, or install and update evidence.

## Scope

- add a shared packaging-target profile layer for the supported local product delivery targets
- project stable target metadata into the `launch_agents`, `homebrew`, and macOS app-bundle
  packaging outputs
- add a deterministic smoke command plus focused regression coverage for the touched Python
  packaging paths
- update packaging, signing, launchd, and runbook documentation before marking `M8.11` and `M8`
  completed

## Phases

1. Packaging target profile truth
   - status: completed
   - evidence:
     - add a shared productization helper that defines the supported Melix packaging targets and
       their stable metadata
     - keep one logical Melix identity while making packaging kind, runtime layout, and update
       strategy explicit
2. Target projection into packaging outputs
   - status: completed
   - evidence:
     - enrich the launch-agent install manifest and environment script with packaging target
       metadata
     - enrich the Homebrew service manifest with the same target metadata
     - enrich the macOS app-bundle output with an embedded target manifest and version or update
       environment exports
3. Smoke coverage and focused tests
   - status: completed
   - evidence:
     - add a deterministic repository-owned smoke command that validates the shared packaging
       target matrix across all supported outputs
     - add or expand focused Python tests for the new helper and the touched packaging paths
4. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - rerun focused verification plus repository-default Python verification
     - record changed-line coverage at or above `95%`, update `progress.md`, and mark `M8.11`
       completed in the roadmap execution index

## Acceptance

- Melix has a repository-owned packaging target matrix for the supported Apple Silicon delivery
  variants
- `launch_agents`, `homebrew`, and `.app bundle` outputs all expose the same logical product
  identity while retaining explicit target metadata
- install and update evidence remains compatible across the supported targets
- a deterministic smoke command and focused tests cover the touched packaging target paths
- `M8.11` and the parent `M8` milestone can be closed with explicit verification and changed-line
  coverage evidence

## Risks

- target differentiation that only exists in docs would drift from the generated manifests and
  break operator or release guidance
- packaging-specific identifiers that diverge from the shared logical product identity would
  fragment install and update reasoning across delivery targets
- extending the packaging outputs without a shared metadata helper would create three incompatible
  state descriptions for the same local Melix product

## Outcome

- m8_11_platform_packaging_target_differentiation_completed
