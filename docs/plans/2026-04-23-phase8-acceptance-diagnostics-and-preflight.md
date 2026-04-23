# Phase 8 Acceptance Diagnostics And Real-Model Preflight

## Context

The Phase 8 acceptance bundle is used as the end-to-end evidence path for real local model, LoRA training, adapter activation, benchmark, and evaluation flows. During the April 23 overnight walk-through, the manual real Qwen path passed, but one `scripts/phase8_acceptance_bundle.py` run exited with return code `-1` and no stderr before model import. The current script only writes final receipts after each CLI command succeeds, so abrupt command termination or outer process termination can leave too little evidence to identify the last started step.

The same walk-through also showed that reports can mix real text model evidence with deterministic development endpoints for unsupported modalities. Evidence should explicitly distinguish real local weights, Hub-required execution, deterministic Melix development models, and missing local real weights.

## Goals

- Persist a progressive acceptance event log before each CLI subcommand starts and after it completes or fails.
- Make CLI command failures with negative return codes and empty stderr/stdout self-explanatory.
- Add a shared model-source preflight projection that identifies real local model weights versus deterministic development models.
- Include preflight results in Phase 8 bundle model metadata so UI/reports do not imply deterministic endpoints are real-model evidence.
- Add a stable shell entry point for the acceptance bundle so login-shell `PATH` pollution cannot resolve `python3` to an unsupported interpreter.

## Non-Goals

- No backend protocol changes.
- No changes to model execution behavior.
- No network-dependent acceptance run as part of the focused fix.

## Implementation Plan

1. Add focused tests for no-output negative CLI failures and event log persistence.
2. Add a real-model preflight helper in `scripts/real_model_support.py`.
3. Wire the preflight helper into `scripts/phase8_acceptance_bundle.py` bundle metadata.
4. Keep existing receipts and bundle schema additive-only for compatibility.
5. Add `scripts/run_phase8_acceptance_bundle.sh` and route `make phase8-acceptance` through it. The wrapper prefers an explicit `MELIX_PHASE8_ACCEPTANCE_PYTHON`, then `uv run ... python`, and only then validated Python 3.12+ absolute interpreter paths.

## Metrics And Verification

- Functional tests:
  - `tests/test_phase8_acceptance_bundle.py`
  - `tests/test_real_model_support.py`
  - `tests/test_phase8_acceptance_wrapper.py`
- Success metrics:
  - A failed bundle leaves `events.jsonl` with the last started CLI command.
  - Negative return codes are described as signal termination when appropriate.
  - Bundle model metadata includes `preflight.runtime_model_class`.
  - The wrapper succeeds with an explicit Python 3.12+ interpreter even when `PATH` starts with an unusable `python3`.
- Runtime performance metrics: `N/A` for this fix because it changes evidence/reporting behavior, not model runtime execution.
