# M15.4 Desktop Polish Integration Evidence

## Goal

Close the desktop-polish milestone with integration evidence, navigation grounding, and product-shell validation.

## Scope

- add integration coverage for polished desktop signals
- verify placeholders remain grounded in real navigation and control-plane state
- record desktop-polish metrics and operator runbook notes

## Files

- update `tests/integration/`
- update `docs/runbooks/`
- update `docs/README.md`

## Implementation Notes

- Evidence should cover token smoothing, banners, and queue recovery together.
- Placeholder validation should confirm that future-facing tabs remain attached to real product-shell state.
- Metrics should remain lightweight but reproducible.

## Verification

- `make integration-test`
- desktop-polish smoke command for the touched scope

## Acceptance

- Desktop polish has live integration evidence and documented operator workflows.
- Navigation grounding and runtime-signal behavior remain explicit and test-covered.
