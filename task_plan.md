# Task Plan

## Goal

Close the remaining M6 gaps on `main` so Quantization And Inference Acceleration is implementation-complete against the repository plans and backed by executable verification.

## Scope

- add missing executable benchmark evidence for `M6.7`
- add missing sparse-prefill benchmark and runbook coverage for `M6.8`
- tighten `M6.9` conflict locking semantics toward family or protected-scope behavior and cover it with tests
- refresh the M6 closing verification commands and metrics evidence

## Phases

1. Planning and baseline evidence
   - status: completed
2. M6.9 locking semantics via TDD
   - status: completed
3. M6.7 and M6.8 benchmark or runbook closure
   - status: completed
4. Verification and metrics report
   - status: completed

## Acceptance

- M6 child-plan acceptance criteria are satisfied or updated with explicit executable evidence.
- Remaining benchmark and runbook gaps for `M6.7` and `M6.8` are closed in-repo.
- Locking behavior for quantization conflicts is protected-scope aware and test-covered.
- Relevant Python verification commands pass.

## Risks

- Swift package verification may be blocked by local toolchain or `.build` cache drift.
- Existing Phase 2 metrics code may need careful extension to avoid regressing current probes.

## Outcome

- M6 closing gaps were addressed with code, tests, plan updates, and a new acceleration benchmark runbook.
- Live benchmark evidence was captured successfully by booting a fresh runtime with `scripts/dev_up.sh --prefer-built`.
