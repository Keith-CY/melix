# Issue 365 Completion Audit

## Objective

Complete https://github.com/Keith-CY/melix/issues/365: make alignment
algorithms and quantization optimization a real end-to-end post-training
product path from base model, through adapter training and alignment, through
export/merge and PTQ/QAT quantization, into local inference, CLI evidence, and
Window UI evidence.

The GitHub issue is currently closed as a roadmap artifact, but the
implementation acceptance criteria are not complete. This audit is the current
source-of-truth checklist for what is finished, what is covered by open PRs,
and what remains before the roadmap can be treated as implemented.

## Audit Snapshot

- Date: 2026-05-06
- Base inspected: `origin/main` at `47d504931`
- Merged Issue 365 PRs inspected:
  - #368, `Add Issue 365 alignment and quantization contracts`
  - #369, `Implement Issue 365 offline preference trainer routing`
  - #386, `Record quantization runtime smoke evidence`
  - #394, `Add scored RL alignment runner`
  - #397, `Add MLX quantization convert backend`
  - #400, `Add CLI pipeline chain routing slice`
  - #412, `Add Issue 365 Window acceptance matrix`
- Related mainline support PRs inspected:
  - #393, `Add dataset management and selection` (useful dataset materialization
    support, but no desktop UI surface and not final Issue 365 acceptance)
- Open Issue 365 PRs inspected:
  - #439, `Refresh Issue 365 completion audit`
  - #442, `Route Issue 365 PTQ through MLX-LM conversion`
  - #446, `Add Issue 365 QAT-aware MLX export`
  - #451, `Issue 365: wire reward runtime scoring`
  - #457, `Bridge Window acceptance to Issue 365 runtime evidence`
- Issue comments inspected:
  - 2026-05-04 roadmap gap review comment. Its CPO, GRPO, RLHF,
    `melix.alignment_run.v1`, quantization release-gate, QAT, dataset-contract,
    and `melix alignment train` findings are either covered by the merged PRs
    above, covered by the open #442/#446/#451/#457 stack, or retained below as
    release/Window/#366 boundary gaps.

## Prompt-To-Artifact Checklist

| Issue requirement | Current evidence | Status |
| --- | --- | --- |
| `lora`, `qlora`, and `dora` supervised adapter training remains supported. | Existing LoRA training pipeline and regression tests remain in `services/mlx-worker-python/tests/test_lora_model_ops.py` and CLI tests. | Covered as baseline regression scope, not reclassified as complete Issue 365 release evidence by itself. |
| `dpo`, `orpo`, and `cpo` accept `preference_pair` datasets. | #368 adds contracts; #369 adds offline preference trainer routing and preference metrics. | Implemented on `origin/main`. |
| `dpo`, `orpo`, and `cpo` run real trainer paths rather than manifest-only placeholders. | #369 routes preference training through worker-side preference trainer logic and records preference metrics. | Implemented on `origin/main`, with targeted unit and worker evidence in the PR body. |
| `grpo` accepts prompt/candidate datasets and records candidate/reward traces. | #368 adds `prompt_candidate` validation. #394 adds a scored-trace runner plus opt-in `runtime_generate` policy-runtime candidate generation and explicit reward-runtime scoring. #451 adds runtime reward scoring and the full real CLI bundle `.runtime/issue365/full-real-runtime-bundle-r2/bundle.json` records `lora_grpo_export_inference` as `succeeded` and `release_ready=true`. | Covered on the open #442/#446/#451 stack; not merged to `origin/main` at this snapshot. |
| `rlhf` consumes reward-model lineage from #366 and records reward-model lineage. | #368 validates readable reward manifests. #394 records reward-scored traces and an opt-in reward-runtime response scoring interface. #451 records runtime reward-model manifest consumption and the full real CLI bundle records `lora_rlhf_export_inference` as `succeeded` and `release_ready=true`. | Covered for #365 runtime lineage on the open #451 stack. Reward-model training and PPO/reward-guided policy optimization remain #366 scope and must not be claimed here. |
| Every preference/RL run emits `melix.alignment_run.v1`. | #368 adds alignment run manifests and adapter backlinks; tests assert `melix.alignment_run.v1`. #394 expands scored-trace, runtime-generated GRPO, and reward-runtime scoring metrics. #451 records release-ready GRPO/RLHF real CLI evidence. | Implemented for contract and current worker paths; final status is pending merge of #451. |
| Adapter manifests backlink to alignment manifests through `alignment_run_manifest_path`. | #368 implementation evidence and worker tests cover adapter backlinking. | Implemented on `origin/main`. |
| Quantized bundle manifests record `quantization_mode`, `source_artifact_kind`, and release-gate evidence. | #368 and #386 extend quantization manifests and typed local smoke evidence. | Implemented on `origin/main`. |
| PTQ can quantize exported or merged artifacts. | Current `origin/main` has manifest/runtime evidence. #442 routes PTQ through MLX-LM conversion, normalizes quantize CLI inputs, and the #451 full real CLI bundle records `lora_preference_ptq_quantized_inference` as `succeeded` and `release_ready=true`. | Covered on the open #442/#446/#451 stack; not merged to `origin/main` at this snapshot. |
| QAT runs before final quantized export and records quantization-aware settings. | #446 adds QAT-aware MLX export on top of #442. The #451 full real CLI bundle records `qat_quantized_inference` as `succeeded` and `release_ready=true`, including a quantized artifact with safetensors/config/tokenizer files. | Covered on the open #446/#451 stack as QAT-aware export evidence; not merged to `origin/main` at this snapshot. |
| QLoRA records quantized-base behavior and rejects unsafe targets. | Existing LoRA/QLoRA contract tests cover mode validation. #400 adds selected `qlora_export_inference` real-local-runtime evidence. The #451 full real CLI bundle records `qlora_export_inference` as `succeeded` and `release_ready=true`. | Covered on the open #442/#446/#451 stack; final status is pending merge. |
| CLI exposes `melix alignment train` separately from `melix lora train`. | #368 adds parser/runner/codec support and tests. | Implemented on `origin/main`. |
| CLI supports a full chained workflow across training, alignment, publish/export, quantize, local inference, and eval/bench evidence. | #400 adds `melix pipeline run` routing for post-training steps plus an Issue 365 acceptance bundle harness. The open #442/#446/#451 stack now records a full real-local-runtime bundle at `.runtime/issue365/full-real-runtime-bundle-r2/bundle.json` with `release_ready=true`, `succeeded_count=10`, `failed_count=0`, `blocked_count=0`, and `known_gaps=[]`. | Covered on the open #442/#446/#451 stack; not merged to `origin/main` at this snapshot. |
| Required CLI chain tests exist for every listed business line. | Existing tests cover focused slices. #400 writes all 10 required chain cases into a machine-readable plan/dry-run matrix and supports `--case-id` subset execution for real-mode runs. The full #451 bundle executed all 10 required cases in `execution_mode=real`. | Covered on the open #442/#446/#451 stack; final status is pending merge and release-evidence publication. |
| Window UI exposes every CLI business line. | Existing Window routing code and tests expose alignment mode state and forwarding paths. #412 adds a Window PTQ/QAT mode selector and a 10-case Window business-line routing matrix. | Covered on `origin/main` for route-level exposure. |
| Window UI acceptance proves every business line is visible, selectable, runnable, and inspectable. | #412 extends the Phase 8 Window UI acceptance bundle with all 10 Issue 365 business lines and records route-level visible/selectable/runnable/inspectable state. #457 consumes the #451 CLI bundle and maps each Window business line to the corresponding real CLI case before marking it release-ready. | Covered on the open #457 stack as route-level Window evidence chained to real CLI runtime evidence; not merged to `origin/main`, and not independent Window click-through execution. |
| Release evidence separates deterministic/unit/scored-trace results from real local runtime results. | PR bodies and plans label deterministic/scored-trace limitations. #400 adds a bundle schema that marks plan/dry-run evidence as not release-ready and marks missing real-mode prerequisites as blocked rather than successful. The #451 full CLI bundle is explicitly `execution_mode=real`, and #457 marks Window release readiness only when the mapped CLI real-runtime case is release-ready. | Covered for CLI and Window-to-CLI readiness on the open #442/#446/#451/#457 stack. A final consolidated release-evidence package remains missing. |
| No business line is marked complete when only deterministic evidence exists. | Plans explicitly state remaining gaps, #400's bundle keeps plan/dry-run evidence `release_ready=false`, and #457 keeps Window cases non-release-ready unless the mapped CLI bundle is real, top-level release-ready, and the mapped case succeeded and is release-ready. | Covered on the open #442/#446/#451/#457 stack; final status is pending merge and release-evidence publication. |

## Verified Covered Work

### Contract Foundation

Implemented by #368 on `origin/main`:

- alignment modes: `dpo`, `orpo`, `cpo`, `grpo`, `rlhf`
- dataset contracts: `preference_pair`, `prompt_candidate`, `reward_scored`,
  and `calibration`
- `melix.alignment_run.v1` output and adapter backlinks
- quantization manifest fields and release-gate evidence
- `melix alignment train` parser and runner surface

### Offline Preference Trainers

Implemented by #369 on `origin/main`:

- DPO, ORPO, and CPO worker-side preference trainer routing
- preference-pair loading and validation
- preference metrics in alignment manifests:
  - `preference_loss_final`
  - `chosen_logprob_mean`
  - `rejected_logprob_mean`
  - `chosen_rejected_margin`
  - `win_rate_proxy`

### Quantization Runtime Smoke Evidence

Implemented by #386 on `origin/main`:

- typed `local_inference_smoke` manifest evidence
- `release_gate.local_inference_smoke_result` derived from structured evidence
- opt-in `runtime_generate` smoke mode
- structured failure evidence for missing or failed smoke paths

## Recent Merged Work With Remaining Limits

### PR #394: Scored RL Alignment Runner

#394 adds a deterministic scored-trace runner for GRPO and RLHF
datasets. It also adds opt-in GRPO `candidate_generation_mode=runtime_generate`
support that loads the policy runtime once per job, generates candidates, scores
them with a seed-overlap proxy, and records generated-candidate evidence in
policy-update traces plus `melix.alignment_run.v1` metrics. It now also adds
explicit `candidate_scoring_mode=reward_model`, loads an injected reward runtime
once per job, and records reward-scoring backend/id evidence for GRPO candidates
or RLHF responses. It is useful implementation progress, but it does not
satisfy final GRPO/RLHF acceptance by itself because the release-ready
real-local-runtime evidence now lives in the open #451 follow-up stack, while
reward-model training artifacts and PPO/reward-guided policy optimization
remain #366 scope and Window UI acceptance remains separate.

### PR #397: MLX Quantization Convert Backend

#397 adds opt-in real PTQ weight conversion through MLX-LM conversion.
It also tightens QAT-aware export evidence by requiring existing
adapter-derived source artifacts and recording fake-quant, source, optional QAT
training-manifest, and calibration lineage in the quantized bundle. It now also
runs a deterministic Melix fake-quant optimizer for QAT requests and records the
generated QAT training trace, training manifest, fake-quant artifact, source
digest, and quant-error proxy metrics. It is useful PTQ/QAT-evidence progress,
but its release-ready PTQ/QAT real-local-runtime evidence now lives in the open
#442/#446/#451 stack, and Window UI acceptance remains separate.

### PR #400: CLI Pipeline Chain Routing

#400 adds pipeline routing for `alignment.train`, `lora.publish`,
`quantize`, `convert`, and `upload` in both the supported-command registry and
the command builder. It also adds an Issue 365 acceptance bundle harness that
writes the full 10-case CLI matrix and explicitly separates planning,
deterministic dry-run, and real-local-runtime evidence. The harness records
per-case real-mode preflight evidence, blocks missing local prerequisites with
machine-readable blocker codes, and supports `--case-id` subset execution so
operators can run a real local runtime slice without requiring unused RLHF or
quantization inputs. The PR now also fixes MLX-LM preference batch comm-group
sharding and records successful selected real-local-runtime bundles for LoRA,
QLoRA, DoRA, DPO, ORPO, and CPO chains. It also exposes quantize
`--local-inference-smoke-mode` and `--local-inference-smoke-prompt` through CLI
and pipeline routing, then tightens PTQ/QAT acceptance around the quantized
bundle manifest's typed `runtime_generate` smoke evidence instead of treating
quantized artifact directories as generic `chat.run` targets. The latest
`lora_preference_ptq_quantized_inference` real probe fails with
`local_inference_smoke.status=failed`,
`local_inference_smoke.evidence_kind=local_runtime_generate`,
`local_inference_smoke.smoke_mode=runtime_generate`, and
`release_gate.local_inference_smoke_result=failed` because the produced
quantized artifact has no safetensors. This was useful non-completion evidence
at the time; the open #442/#446/#451 stack supersedes it with a passing full
10-case real CLI bundle, but that evidence is not yet merged to `origin/main`.

### PR #412: Window Acceptance Matrix

#412 adds a Window UI PTQ/QAT quantization mode state, exposes the mode
selector beside the existing quantization profile selector, and forwards
explicit `quantization_mode`, `source_artifact_kind`, and QAT source-artifact
hints through Window model-operation requests. It also extends the Phase 8
Window UI acceptance bundle with all 10 Issue 365 business lines and records
visible/selectable/runnable/inspectable route state for each case. The merged
#412 evidence is useful Window routing and inspectability evidence, but it does
not independently prove real local runtime readiness.

## Open Stacked Work With New CLI Evidence

### PR #442: PTQ Through MLX-LM Conversion

#442 routes the Issue 365 PTQ path through MLX-LM conversion and adopts review
feedback around case-insensitive CLI normalization plus integer validation for
MLX-LM quantization arguments. Its latest local evidence includes targeted
Swift CLI/parser tests, changed-line coverage at `100.00% (108/108)`, and
passing PR evidence validation.

### PR #446: QAT-Aware MLX Export

#446 builds on #442 and adds the QAT-aware MLX export path needed by the final
Issue 365 quantization lane. It is still draft and based on
`codex/issue365-ptq-runtime`.

### PR #451: Reward Runtime Scoring And Full Real CLI Bundle

#451 builds on #446 and wires the production reward runtime path for GRPO/RLHF.
After rebasing onto the latest #446 head, the stacked branch produced the first
full real-local-runtime CLI acceptance bundle:

- Bundle path:
  `.runtime/issue365/full-real-runtime-bundle-r2/bundle.json`
- Runtime instance:
  `i365fr3` on `http://127.0.0.1:12480`, with short `/tmp/mx365-fr3-*.sock`
  worker sockets because the worktree-local socket path exceeded macOS Unix
  socket limits and sandboxed startup could not bind sockets.
- Inputs:
  `melix-dev-dataset.v1`, `preference_pair`, `prompt_candidate`,
  `reward_scored`, `calibration`, and a local reward-model manifest.
- Result:
  `release_ready=true`, `succeeded_count=10`, `failed_count=0`,
  `blocked_count=0`, and `known_gaps=[]`.
- Succeeded real cases:
  `lora_export_inference`, `qlora_export_inference`, `dora_export_inference`,
  `lora_dpo_export_inference`, `lora_orpo_export_inference`,
  `lora_cpo_export_inference`, `lora_grpo_export_inference`,
  `lora_rlhf_export_inference`,
  `lora_preference_ptq_quantized_inference`, and
  `qat_quantized_inference`.

This changes the audit posture: the CLI matrix now has passing real local
runtime evidence on the open stack, but Issue 365 still should not be marked
implemented until that stack lands, Window readiness is tied to the same real
evidence, and the final release-evidence package is published.

### PR #457: Window Real CLI Evidence Bridge

#457 builds on #451 and maps every Phase 8 Window UI business-line case to the
corresponding Issue 365 CLI real-runtime case. A Window case is marked
release-ready only when the consumed CLI bundle has `execution_mode=real`, the
top-level CLI bundle is `release_ready=true`, and the mapped CLI case is
`status=succeeded` with `release_ready=true`.

This is useful Window evidence because it keeps route visibility,
selectability, runnability, and inspectability coupled to the same full real
CLI bundle instead of treating route evidence as release proof. It still does
not prove independent Window click-through execution for every business line,
and it is still open-stack evidence until #457 lands.

## Missing Completion Items

The objective is not achieved until all of these are implemented and verified:

1. Land the open #442/#446/#451/#457 stack, with green CI and PR evidence kept
   in sync, so the passing full real CLI bundle and Window bridge are part of
   the repository history rather than only local stacked-branch evidence.
2. Decide whether #365 requires independent Window click-through execution for
   every CLI-supported business line. #457 proves Window route evidence chained
   to real CLI readiness, but not full independent Window execution.
3. A final populated release evidence bundle that distinguishes:
   - unit tests
   - deterministic fixture tests
   - scored-trace evidence
   - real local runtime evidence
   - Window route evidence
   - Window-to-real-CLI readiness evidence
4. A final #366 boundary statement. #365 can consume a reward-model manifest
   for RLHF lineage, but reward-model training and PPO/reward-guided policy
   optimization remain #366 scope unless the issue owner explicitly expands
   #365.

## Recommended Next Implementation Order

1. Watch and fix CI for #442, #446, #451, and #457; once green, move the stack
   out of draft and merge in order.
2. After the stack lands, rerun the full real CLI acceptance bundle and the
   Window bridge from the merged tree rather than relying on stacked-branch
   evidence.
3. Publish a final release evidence package that points to the merged unit,
   deterministic, scored-trace, full real CLI, and Window evidence.
4. Keep #366 reward-model training and PPO/reward-guided policy optimization
   out of the #365 completion claim unless the issue owner explicitly changes
   the dependency boundary.

## Audit Conclusion

Issue #365 is not complete. The current open stack now has the first passing
full 10-case real-local-runtime CLI acceptance bundle plus a Window-to-real-CLI
readiness bridge, but that evidence is not merged and the final release package
does not exist yet. This audit must not be used to mark the objective complete
until the stack lands, merged-tree evidence is rerun, final release evidence is
published, and the #366 boundary is stated without claiming reward-model
training or PPO work as complete.
