# Post-Closure Follow-up Child Implementation

## Goal

Implement the child issues created from the closed-issue post-closure audit so
that the actionable follow-up advice from #41 and #43 is represented in code,
tests, and durable receipts instead of remaining only in closed comment
threads.

## Source

- Parent audit plan:
  `docs/plans/2026-05-24-closed-issue-post-closure-followup-audit.md`
- Parent trackers: #1518 and #1519
- Child issues from #1518: #1522, #1523, #1524, #1525, #1526, and #1527
- Child issues from #1519: #1528, #1529, #1530, and #1531

## Implementation Slices

| Issue | Slice | Primary scope | Dependency |
| --- | --- | --- | --- |
| #1522 | Text compatibility policy receipts | OpenAI-compatible text request admission and worker/run evidence | None |
| #1523 | Prompt-budget typed errors | Text request admission before worker prefill/generation | None |
| #1524 | Parser format audit and selector parity | Parser registry, CLI/Desktop/API selector surfaces, fixtures | None |
| #1525 | Shared text finalization state | Stream/non-stream text response finalization and usage trailers | None |
| #1526 | Token-routed output assembly | Reasoning/tool/visible-text token routing and fallback receipts | #1522 |
| #1527 | Generation bounds receipts | Text request generation bounds, stop handling, passthrough evidence | None |
| #1528 | Training admission receipts | LoRA/training validation and resolved-control evidence | None |
| #1529 | LoRA artifact and drift canaries | LoRA checkpoint, resume, merge/export, callback drift, round-trip canaries | None |
| #1530 | Training runtime preflights | Dependency, platform, native-load, decoder, and cleanup guards | None |
| #1531 | Advanced training planner receipts | Planner, backend, profiler, numerical-policy, and generation safety evidence | #366 for reward-model smoke promotion only |

The implementation should keep each slice independently reviewable, but the
final pull request may integrate the slices into one feature branch when shared
receipt models, fixtures, or test helpers make a single coordinated change more
coherent.

## Performance Probes And Metrics

The changed paths span request admission, OpenAI-compatible text response
assembly, parser selection, and LoRA/training planning. The implementation must
collect or report the following metrics before pull request handoff:

- Text admission probes: prompt-token estimate, context-window bound,
  output-cap bound, admission phase, and whether worker prefill started.
- Text assembly probes: stream mode, finalizer path, finish reason, usage
  trailer emission, reasoning/tool finalization, malformed-channel recovery,
  and fallback raw-text parsing.
- Parser probes: parser id, parser kind, declared accepted wire formats,
  selector surface, selector source, request-context mode, and any explicit
  exemption reason.
- Generation-bound probes: requested/effective token caps, output-cap source,
  stop-string normalization, bounds rejection reason, and passthrough sampling
  controls.
- Training admission probes: validation errors, resolved bounds, capability
  gates, dataset-file resolution, grad-clip policy, eval batch size, and
  scheduler-argument omission.
- LoRA artifact probes: tokenizer EOS preservation, base config presence,
  processor resume mode, auxiliary module restore state, merge/export canary
  result, callback API drift result, completion loss, round-trip result, and
  grad-norm visibility.
- Runtime preflight probes: runtime gate, inspection-only import state, media
  decoder dependency state, native-load status, disabled decoder paths,
  fallback reader, unsupported reason, traceback cleanup result, and retained
  tensor bytes after failure where measurable.
- Advanced planner probes: batching strategy, cutoff length, micro batch size,
  effective token budget, packing mode, media counts, kernel policy, expected
  peak memory class, profile artifact path, compiled-step state, gradient
  checkpoint state, attention backend, metric-for-best-model resolution,
  generation mode, and final-logit softcapping.

Success is measured by paired stream/non-stream tests where applicable,
request-local receipts with stable schemas, typed validation failures for
invalid inputs, and coverage for the new receipt fields in focused unit or
integration tests.

## Integration Strategy

1. Implement each issue in an isolated worktree and branch based on current
   `origin/main`.
2. Merge independent slices into `feat/post-closure-followups` after focused
   verification passes.
3. Implement #1526 after the #1522 receipt model is available on the feature
   branch.
4. Resolve conflicts by preserving the shared receipt schema and adapting tests
   to the final integrated behavior.
5. Run the relevant Swift, Python, integration, coverage, and PR evidence
   commands before opening or updating the pull request.

## Acceptance Criteria

- #1522 through #1531 are either implemented or explicitly marked out of scope
  with issue-linked evidence in the pull request.
- Behavior-changing slices include focused tests and receipt assertions for the
  fields named in their issue bodies.
- Stream and non-stream OpenAI-compatible paths remain paired where the issue
  requires parity.
- Training admission and LoRA runtime paths produce typed validation or canary
  evidence without making inspection-only commands import execution-only
  dependencies.
- The pull request body preserves the repository template sections and links
  this plan.

## Verification

Targeted verification depends on the files changed by each slice. The final
handoff should include, at minimum:

```bash
git diff --check
make swift-test
make py-test
make integration-test
python scripts/validate_pr_evidence.py --body-file <pr-body-file>
```

If a scope-specific coverage or performance command is not yet measurable for a
slice, the pull request must include an explicit `N/A` metrics report with the
reason.
