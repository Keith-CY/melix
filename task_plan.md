# Task Plan

## 2026-04-14 Semantic Evaluation Controls

### Goal

Make `few_shot`, `seed`, `scoring_mode`, and `code_exec_policy` affect real Melix evaluation
behavior, and move `humaneval` plus `mbpp` from text-match placeholders to executable
evidence-bearing scoring.

### Scope

- apply seeded dataset planning before both few-shot selection and scored sample slicing
- make few-shot examples part of the rendered prompt while excluding them from scored samples
- thread effective seeds into worker sampling requests
- route `scoring_mode` into real scorer dispatch instead of metadata-only persistence
- reject unsupported scorer and code-execution-policy combinations explicitly
- remove default offline synthetic success from evidence-bearing evaluation paths
- add a code runner for `pass_at_1` suites and persist execution diagnostics in sample exports
- enforce the shipped `sandboxed` policy with a real macOS sandbox boundary, temporary-directory
  write confinement, bounded stdout plus stderr, and fail-fast worker capability checks
- keep export, store, release-gate evidence, and maintenance RPC behavior aligned with the new
  runtime semantics

### Status

- completed

### Verification Targets

- `make py-test`
- `git diff --check`
- targeted coverage over the changed evaluation and release-gate Python scope with changed-line
  coverage at or above `95%`
- targeted code-exec hardening regression tests over the runner and evaluation-core paths

## Goal

Close the Phase 1 benchmark, benchmark-matrix, and evaluation acceptance slice for the designated
text baseline so the CLI remains the single behavior source of truth, the Window UI diagnostics
surfaces execute through the CLI seam, and the phase metrics command is reproducible with
`mlx-community/Qwen3.5-0.8B-OptiQ-4bit`.

## Scope

- finish the approved Phase 1 spec and runbook boundary for the CLI-first, mixed-mode Window UI
- keep the Window UI benchmark and evaluation flows subprocess-backed in production and runner-seam
  backed in tests
- restore Swift worker direct-path compatibility for the designated baseline model
- make `scripts/dev_up.py` provide the runtime support needed by the Swift worker live path and the
  isolated Phase 1 metrics workflow
- capture phase-scoped verification, coverage, and progress evidence
- leave the post-phase squash merge to local `main` and refresh/rebase flow pending until the
  current branch is ready to commit

## Measurement Points

- the accepted baseline model is recorded and used for the Phase 1 metrics flow:
  `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- production Window UI benchmark and evaluation actions route through the public `melix` CLI
  subprocess path
- shared-seam Window UI tests exercise the same CLI contract used by production
- the Swift worker direct path no longer fails the designated baseline with
  `Unsupported model type: qwen3_5`
- `make phase1-metrics PHASE1_METRICS_ARGS='--json'` completes against an isolated live runtime
- aggregate measurable changed-line coverage for the touched Phase 1 slice remains at least `95%`

## Phases

1. Boundary and design lock
   - status: completed
   - success criteria:
     - approved spec, master plan, and phase plan exist for the Phase 1 closure
     - the designated baseline model and mixed execution model are frozen in the docs
2. CLI-owned Window UI seam closure
   - status: completed
   - success criteria:
     - the Window UI benchmark and evaluation actions use the subprocess-backed CLI runner in
       production
     - shared runner-seam tests cover positive and negative diagnostics workflows
3. Swift worker and runtime support closure
   - status: completed
   - success criteria:
     - Swift MLX dependency and linkage updates restore the designated baseline model path
     - `dev_up.py` provides the metallib launch context and runtime isolation needed by the live
       Swift worker path without dropping persisted gateway settings
4. Verification and metrics capture
   - status: completed
   - success criteria:
     - focused Swift, Python, and Window UI verification commands pass
     - the exact `make phase1-metrics PHASE1_METRICS_ARGS='--json'` command passes against an
       isolated runtime
     - phase-scoped coverage and progress evidence are recorded
     - CLI acceptance, Window UI acceptance, and the positive/negative UT and E2E results are
       explicitly recorded
5. Phase integration
   - status: pending
   - success criteria:
     - stage and commit the current phase
     - squash merge the phase branch to local `main`
     - refresh local `main` and rebase or recreate the next phase branch from that refreshed base

## Acceptance

- Phase 1 benchmark, matrix, and evaluation acceptance is executable from the CLI and viewable from
  the existing Window UI diagnostics surfaces without a second behavior layer
- the designated text baseline runs through the Swift direct path, the Python compatibility path,
  and the control-plane HTTP path during the canonical Phase 1 metrics workflow
- the recorded verification evidence and measurable changed-line coverage satisfy the repository
  handoff bar for this phase
- CLI positive UT passed in the fresh Phase 1 closure rerun
- CLI negative UT passed in the fresh Phase 1 closure rerun
- CLI positive E2E passed in the fresh Phase 1 closure rerun
- CLI negative E2E passed in the fresh Phase 1 closure rerun, including live worker failure
  surfacing after the workers stop
- Window UI positive UT passed in the fresh Phase 1 closure rerun
- Window UI negative UT passed in the fresh Phase 1 closure rerun
- Window UI positive E2E passed in the fresh Phase 1 closure rerun
- Window UI negative E2E passed in the fresh Phase 1 closure rerun
- CLI acceptance passed against `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- Window UI acceptance passed through the existing `Tools -> Diagnostics -> Benchmark`,
  `Benchmark Matrix`, and `Evaluation` workflows, including visible failure states and production
  subprocess proof
- Window UI follow-up changed-line coverage for
  `AppMain.swift`, `MelixCLISubprocessRunner.swift`, `AppMainBootstrapTests.swift`, and
  `MelixCLISubprocessRunnerTests.swift`: `100.00%` (`181/181`)
- Phase 1 CLI E2E changed-line coverage for `tests/integration/test_phase1_benchmark_eval_cli.py`:
  `100.00%` (`13/13`)
- Aggregate measurable changed-line coverage across the final Phase 1 follow-up delta:
  `100.00%` (`194/194`)
- `make phase1-metrics PHASE1_METRICS_ARGS='--json'` passed against
  `/Users/ChenYu/.codex/worktrees/8265/melix/.runtime/phase1-metrics-isolated-d`, and the emitted
  JSON report recorded successful `swift_worker_direct`, `python_worker_direct`, and
  `control_plane_http` paths for the designated baseline

## Risks

- if later work changes the Swift MLX dependency graph again, the `qwen3_5` registration and
  trampoline linkage could regress without the focused worker tests failing
- if a future bootstrap path bypasses the shared CLI seam, the Window UI and CLI behaviors could
  drift again
- if the repository-wide `make swift-test` hang in `services/control-plane-swift` is not resolved,
  broad default verification remains infrastructure-limited even when the touched Phase 1 scope is
  green
