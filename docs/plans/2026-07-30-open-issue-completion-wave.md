# Open Issue Completion Wave

## Goal

Complete the current Melix open-issue queue through one isolated delivery track
per issue. Each track starts from the current `origin/main`, audits the issue's
full acceptance contract against merged behavior, implements the remaining
gap, and ends only after its pull request is reviewed, verified, and squash
merged.

This plan originally covered the 25 issues that were open on 2026-07-30. The
live queue was reconciled on 2026-08-03: three original issues are complete and
one new issue entered the queue, leaving 23 open issues. It does not treat a
recent watch note, an earlier merged slice, or a checked-off child issue as
proof that the parent issue is complete. Each issue needs a fresh completion
audit against its body, all comments, governing specifications, and current
code.

## Live Queue Reconciliation

The following original tracks reached the delivery contract and are no longer
active work:

- Issue #2605 closed through PR #2777 at squash commit
  `b1c9241da7a1976a6865520e527131d6eb854a5a`.
- Issue #2606 closed through PR #3154 at squash commit
  `adf38f4ee693ef99eb08750428c9f70724fc47a8`.
- Issue #2945 closed through PR #3179 at squash commit
  `ce87f9b365f6ae729401f3298a317b538eee6d27`.

Issue #3166 was opened after the original capture. It joins Wave B because its
artifact-backed embedding backend depends on issue #1258's trust boundary and
issue #2945's now-merged backend identity boundary.

## Delivery Contract

Every issue uses a dedicated implementation agent, branch, and worktree created
from a freshly fetched `origin/main`. An implementation agent is never reused
for another issue in this wave.

Each implementation track must:

1. Read the full issue and comments, then identify the governing specification
   or plan.
2. Derive an acceptance checklist that covers the original scope and all later
   clarifications that remain in scope.
3. Audit current `origin/main` and merged pull requests before writing code.
4. Define the affected performance path, probes, measurement points, and target
   metrics before implementation.
5. Implement the complete remaining issue scope in reviewable commits.
6. Update behavior documentation, generated artifacts, and lockfiles when the
   changed contract requires them.
7. Reach at least 95 percent measured automated coverage for the changed scope.
8. Run the relevant focused checks plus `make bootstrap`, `make proto`,
   `make swift-test`, `make py-test`, and `make integration-test` before the
   final commit. Any inapplicable command must be recorded with a concrete
   reason.
9. Produce a changed-scope metrics report and a scoped performance report with
   no unexplained regression.
10. Fill the repository pull-request template without changing its required
    headings.

Completion is reviewed on three independent axes:

- The primary agent reviews correctness, integration risk, evidence, and the
  full issue acceptance checklist.
- A Standards review agent checks repository rules and code quality against the
  merge-base diff.
- A Spec review agent checks the same diff against the issue and governing
  documents.

The implementation agent must address every blocking finding. The primary
agent then refreshes the branch from `origin/main`, reruns affected checks,
pushes the final evidence, replies to and resolves review threads, and monitors
GitHub until required CI and the performance report are terminal and
acceptable. Only then may the pull request be squash merged. After merge, the
issue state and `origin/main` ancestry are verified before the next dependent
track starts.

## Ordering Principles

- Finish in-flight work before starting overlapping implementations.
- Land fail-closed correctness and trust boundaries before accelerators that
  depend on them.
- Land shared runtime contracts before product surfaces that consume them.
- Land base behavior and evidence before promotion gates.
- Keep independent tracks parallel only when their ownership and generated
  artifacts do not overlap.
- Re-fetch and re-plan at every wave boundary because merged work can satisfy or
  reshape later issue requirements.

## Wave A: In-Flight And Fail-Closed Boundaries

### Issue #1258

Audit the previously merged artifact-integrity slices and close all remaining
install, upgrade, bootstrap, activation, and diagnostics gaps. The completion
track must also prove contained executable model-file resolution after trust is
granted. Metrics must measure verification and resume-preflight cost separately
from transfer time.

### Issue #1382

Audit the merged guardrail slices, then complete the remaining operator-facing
contract. Exactly-once tool execution, bounded approval parking, cancellation,
reload cleanup, final-answer transition, and diagnostics must share one
request-scoped ledger. Metrics must cover prompt growth, executor capacity, and
ledger overhead under concurrent waits.

### Issue #2601

Make Swift text cache capability claims match executed behavior. The track must
first eliminate synthetic byte-saving claims, then either implement real
block-owned KV reuse and compatible restore semantics or explicitly downgrade
the exposed capability wherever execution cannot prove it. Metrics must compare
actual allocated KV bytes, shared-prefix savings, restore parity, and warm-path
latency.

## Wave B: Serving, Embedding, And Cache Foundations

### Issue #3166

Replace the product-facing deterministic embedding projection with an explicit
artifact-backed MLX backend for the initial BERT and XLM-R families. Preserve
the deterministic backend only as a named fixture path; prove tokenizer and
weight identity, pooling, normalization, vector shape, dtype-safe masking,
one-forward batching, residency, and typed refusal of unsupported multi-vector
or media artifacts. Golden parity, finite outputs, and batch throughput are
acceptance gates.

### Issue #1384

Audit the conformance parent after all listed children have closed. Close any
remaining parity gap, including request-owned multi-token stop holdback where it
is not already covered, and regenerate machine-readable conformance evidence.
Metrics must bound holdback latency and per-request state under interleaved
streams.

### Issue #1396

Define and enforce the prompt-cache and compressed-KV compatibility matrix.
Persistence must not silently materialize unsafe cache states, and receipts must
name every skip or downgrade. Differential promotion evidence must bind quality
and memory results to a runtime fingerprint.

### Issue #1393

Complete the product-owned generation strategy router and rollback contract.
Requested and effective strategy, draft compatibility, cache state, and refusal
reasons must be transactional and observable before generation. Deterministic
output parity and rollback cleanliness are hard gates.

### Issue #2602

Generalize native multi-token prediction through the strategy and capability
contracts landed above. Cover artifact topology, family adapters, batch
reshaping, device policy, and explicit fallback receipts. Measure greedy
identity, acceptance rate, and net throughput for batch sizes 1, 2, and 4.

### Issue #1394

Implement explicit SSD expert streaming for supported mixture-of-experts
backends, including real byte-read metrics, memory admission, and recoverable
I/O failures. Placeholder metrics cannot satisfy this issue. At least one real
Apple Silicon evidence cell is required before a speed or memory claim.

## Wave C: Local-First Product Workflows

### Issue #2188

Complete the privacy policy and receipt boundary for proxy, ingestion, logs, and
published evidence. Strict outbound routing and repository-history hygiene must
fail closed without leaking sensitive path or host data. Metrics must record
detector cost, redaction counts, and route-policy overhead.

### Issue #1760

Complete read-only workspace source registration, extraction, retrieval, and
source receipts. All indexing lanes must share one top-down pruning policy and
normalization boundary. Keyword and vector paths must produce identical source
sets, never open excluded files, and continue safely past malformed findings.

### Issue #1758

Build the remaining research preset, citation, and evidence-bundle product
surface after workspace and privacy boundaries are available. Quick, balanced,
deep, local-only, and web-enabled modes must expose their budgets before a run
and preserve deterministic source-to-citation provenance afterward.

### Issue #1383

Finish session-level compaction beyond the already merged receipt path.
Grounding-preserving compaction, authoritative control-flow retention,
user-editable event lanes, and operator controls must agree across API, CLI,
and desktop surfaces. Metrics must show token reduction and retention quality on
a synthetic long session.

### Issue #58

Complete deterministic packaged-runtime verification and selection. Consumer
installation must prove a complete manifest and real backend boot without
developer tooling, survive interruption at declared phases, and repair
idempotently. The filesystem verification target remains below 250 ms on the
repository cold-start probe.

### Issue #1397

Complete the model catalog, fit-status, profiler, resumable download, and
benchmark linkage contracts. Memory estimation must follow the actual model and
cache topology. Estimates and measured resident deltas must meet the issue's
declared error bounds before recommendations change.

## Wave D: Training Contracts

### Issue #2609

Productize the remaining training families through one immutable support
descriptor and ordered hook contract. Unsupported families must refuse before
dataset materialization; supported families require target, freeze, activation,
and real-model acceptance evidence. Concurrency tests must prove request-local
descriptor state.

### Issue #366

Complete the reward-model and policy-optimization roadmap with real local
runtime evidence. Reward cardinality and score validity must fail closed before
policy mutation, and artifact lineage must connect the base model, reward head,
dataset, policy adapter, algorithm, and checkpoints.

### Issue #1531

Complete advanced training planning and receipts after the family registry is
stable. Effective precision, batching, memory class, profiler artifacts,
compiled-step policy, checkpointing, attention backend, metrics, and softcap
canaries must propagate unchanged through launch, resume, training, and
evaluation. Reward-specific promotion follows issue #366.

## Wave E: Multimodal Promotion

### Issue #42

Audit the multimodal parent against its original throughput, repeated-image
reuse, native quantized loading, and per-request metrics targets. Implement all
remaining base gaps before speculative promotion. Real supported-model evidence,
not registry presence or placeholder receipts, proves closure.

### Issue #1425

Complete multimodal speculative and adaptive acceleration only after issue #42
base evidence is current. Verification-only media-bearing probes, activation
policy, rollback, output parity, and supported-model speed targets must all pass.

### Issue #1437

Land matched baseline-versus-accelerated artifacts and Apple Silicon rollout
receipts after issue #1425. The gate must compare identical model, prompt, media,
generation, and runtime identities and must block absent or mismatched evidence.

### Issue #1473

Finish the promotion release and pull-request gates after issue #1437. Every
enabled family needs parity, fallback, speed, and served-output coherence
evidence, with deterministic separation between infrastructure and semantic
failures plus documented rollback guidance.

## Human-Gated Track

### Issue #1620

This issue requires repository-admin access, external distribution repositories,
and write-capable secrets. An implementation agent cannot invent or provision
those resources. The primary agent will re-verify the external state at each
wave boundary. Once an authorized human creates the targets and configures the
variables and secrets, a dedicated agent will run the release workflows, fix
any code-owned failures in an isolated pull request, and complete the same
review and merge gates as every other issue.

## Wave Exit Evidence

At the end of every wave, record:

- issues and pull requests completed;
- squash merge commits and `origin/main` ancestry checks;
- local command outcomes, coverage, and performance reports;
- remote checks and unresolved review-thread count;
- changes to later issue scope or ordering caused by the merged work;
- external blockers that remain, with live evidence rather than remembered
  status.

The overall wave is complete only when all 22 currently agent-actionable issues
are closed with verified merged behavior and issue #1620 has also completed
after its administrator prerequisites are provided. While those prerequisites
are absent, the overall wave remains active and the live external-state report
records the outstanding gate.
