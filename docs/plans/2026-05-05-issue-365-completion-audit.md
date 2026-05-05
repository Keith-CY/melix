# Issue 365 Completion Audit

## Objective

Complete https://github.com/Keith-CY/melix/issues/365: make alignment
algorithms and quantization optimization a real end-to-end post-training
product path from base model, through adapter training and alignment, through
export/merge and PTQ/QAT quantization, into local inference, CLI evidence, and
Window UI evidence.

The GitHub issue is currently closed as a roadmap artifact, but the
implementation acceptance criteria are not complete. This audit is the current
source-of-truth checklist for what is finished, what is covered by open draft
PRs, and what remains before the roadmap can be treated as implemented.

## Audit Snapshot

- Date: 2026-05-05
- Base inspected: `origin/main` at `87e5ea054`
- Merged Issue 365 PRs inspected:
  - #368, `Add Issue 365 alignment and quantization contracts`
  - #369, `Implement Issue 365 offline preference trainer routing`
  - #386, `Record quantization runtime smoke evidence`
- Open Issue 365 draft PRs inspected:
  - #394, `Add scored RL alignment runner`
  - #397, `Add MLX quantization convert backend`
  - #400, `Add CLI pipeline chain routing slice`

## Prompt-To-Artifact Checklist

| Issue requirement | Current evidence | Status |
| --- | --- | --- |
| `lora`, `qlora`, and `dora` supervised adapter training remains supported. | Existing LoRA training pipeline and regression tests remain in `services/mlx-worker-python/tests/test_lora_model_ops.py` and CLI tests. | Covered as baseline regression scope, not reclassified as complete Issue 365 release evidence by itself. |
| `dpo`, `orpo`, and `cpo` accept `preference_pair` datasets. | #368 adds contracts; #369 adds offline preference trainer routing and preference metrics. | Implemented on `origin/main`. |
| `dpo`, `orpo`, and `cpo` run real trainer paths rather than manifest-only placeholders. | #369 routes preference training through worker-side preference trainer logic and records preference metrics. | Implemented on `origin/main`, with targeted unit and worker evidence in the PR body. |
| `grpo` accepts prompt/candidate datasets and records candidate/reward traces. | #368 adds `prompt_candidate` validation. #394 adds a scored-trace runner plus opt-in `runtime_generate` policy-runtime candidate generation and explicit reward-runtime scoring in a draft PR. | Partially covered by open draft PR #394. Release-ready GRPO still needs real local runtime release evidence and real policy-update evidence. |
| `rlhf` consumes reward-model lineage from #366 and records reward-model lineage. | #368 validates readable reward manifests. #394 records reward-scored traces and an opt-in reward-runtime response scoring interface in a draft PR. | Partially covered by open draft PR #394. Reward-model training artifacts and PPO/reward-guided policy updates from #366 are still missing. |
| Every preference/RL run emits `melix.alignment_run.v1`. | #368 adds alignment run manifests and adapter backlinks; tests assert `melix.alignment_run.v1`. | Implemented for contract and current worker paths on `origin/main`; open #394 expands scored-trace, runtime-generated GRPO, and reward-runtime scoring metrics. |
| Adapter manifests backlink to alignment manifests through `alignment_run_manifest_path`. | #368 implementation evidence and worker tests cover adapter backlinking. | Implemented on `origin/main`. |
| Quantized bundle manifests record `quantization_mode`, `source_artifact_kind`, and release-gate evidence. | #368 and #386 extend quantization manifests and typed local smoke evidence. | Implemented on `origin/main`. |
| PTQ can quantize exported or merged artifacts. | Current `origin/main` has manifest/runtime evidence. #397 adds an opt-in `mlx_lm_convert` backend for real PTQ conversion in draft. | Not complete on `origin/main`; open draft PR #397 covers the next backend slice. |
| QAT runs before final quantized export and records quantization-aware settings. | #397 records QAT-aware export lineage, requires existing adapter-derived source artifacts, and now writes deterministic fake-quant optimizer trace/manifest/artifact evidence in a draft PR. | Partially covered by open draft PR #397. MLX-native QAT over full model tensors and real local-runtime release evidence are still missing. |
| QLoRA records quantized-base behavior and rejects unsafe targets. | Existing LoRA/QLoRA contract tests cover mode validation; #365-specific real release evidence is not complete. | Partial baseline coverage only. |
| CLI exposes `melix alignment train` separately from `melix lora train`. | #368 adds parser/runner/codec support and tests. | Implemented on `origin/main`. |
| CLI supports a full chained workflow across training, alignment, publish/export, quantize, local inference, and eval/bench evidence. | #400 adds `melix pipeline run` routing for post-training steps plus a draft Issue 365 acceptance bundle harness. | Not complete on `origin/main`; open draft PR #400 covers routing and plan/dry-run evidence orchestration, not final real-runtime acceptance. |
| Required CLI chain tests exist for every listed business line. | Existing tests cover focused slices. #400 now writes all 10 required chain cases into a machine-readable plan/dry-run matrix. | Partially covered by open draft PR #400. Real local runtime execution of the full matrix is still missing. |
| Window UI exposes every CLI business line. | Existing Window routing code and tests expose alignment mode state and forwarding paths. | Partial UI routing exists; full runnable/inspectable acceptance remains missing. |
| Window UI acceptance proves every business line is visible, selectable, runnable, and inspectable. | Existing Window tests cover routing surfaces. No full real-runtime acceptance matrix exists. | Missing. |
| Release evidence separates deterministic/unit/scored-trace results from real local runtime results. | PR bodies and plans label deterministic/scored-trace limitations. #400 adds a bundle schema that marks plan/dry-run evidence as not release-ready. | Partially covered by open draft PR #400. A final real-local-runtime release evidence bundle is still missing. |
| No business line is marked complete when only deterministic evidence exists. | Plans explicitly state remaining gaps, and open PRs are draft. | Process guard exists, but final release gate is missing. |

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

## Open Draft Work

### PR #394: Scored RL Alignment Runner

Draft PR #394 adds a deterministic scored-trace runner for GRPO and RLHF
datasets. It also adds opt-in GRPO `candidate_generation_mode=runtime_generate`
support that loads the policy runtime once per job, generates candidates, scores
them with a seed-overlap proxy, and records generated-candidate evidence in
policy-update traces plus `melix.alignment_run.v1` metrics. It now also adds
explicit `candidate_scoring_mode=reward_model`, loads an injected reward runtime
once per job, and records reward-scoring backend/id evidence for GRPO candidates
or RLHF responses. It is useful implementation progress, but it does not
satisfy final GRPO/RLHF acceptance because it still excludes PPO/reward-guided
updates, real local runtime release evidence, reward-model training artifacts
from #366, and Window UI acceptance.

### PR #397: MLX Quantization Convert Backend

Draft PR #397 adds opt-in real PTQ weight conversion through MLX-LM conversion.
It also tightens QAT-aware export evidence by requiring existing
adapter-derived source artifacts and recording fake-quant, source, optional QAT
training-manifest, and calibration lineage in the quantized bundle. It now also
runs a deterministic Melix fake-quant optimizer for QAT requests and records the
generated QAT training trace, training manifest, fake-quant artifact, source
digest, and quant-error proxy metrics. It is useful PTQ/QAT-evidence progress,
but it explicitly excludes MLX-native QAT over full model tensors and full
CLI/Window acceptance.

### PR #400: CLI Pipeline Chain Routing

Draft PR #400 adds pipeline routing for `alignment.train`, `lora.publish`,
`quantize`, `convert`, and `upload`. It also adds an Issue 365 acceptance bundle
harness that writes the full 10-case CLI matrix and explicitly separates
planning, deterministic dry-run, and real-local-runtime evidence. This is useful
release-evidence infrastructure, but it still does not provide full real local
runtime acceptance for every business line.

## Missing Completion Items

The objective is not achieved until all of these are implemented and verified:

1. Release-ready GRPO online candidate generation from a loaded policy runtime
   with real local runtime evidence, not only scripted/deterministic tests.
2. Release-ready GRPO reward-model scoring and policy update evidence, not only
   scripted reward-runtime scoring, seed-overlap proxy scoring, or scored-trace
   replay.
3. RLHF reward-model training artifact integration plus reward-guided/PPO-style
   policy updates from #366 artifacts.
4. MLX-native QAT training over full model tensors and real local-runtime QAT
   release evidence. Deterministic fake-quant optimizer execution is partially
   covered by open draft PR #397, but release-ready MLX-native QAT is not.
5. Full real-runtime CLI chain execution for every listed business line:
   - BaseModel -> LoRA -> export -> local inference
   - BaseModel -> QLoRA -> export -> local inference
   - BaseModel -> DoRA -> export -> local inference
   - BaseModel -> LoRA -> DPO -> export -> local inference
   - BaseModel -> LoRA -> ORPO -> export -> local inference
   - BaseModel -> LoRA -> CPO -> export -> local inference
   - BaseModel -> LoRA -> GRPO -> export -> local inference
   - BaseModel -> LoRA -> RLHF using #366 reward model -> export -> local inference
   - BaseModel -> LoRA/preference result -> merge/export -> PTQ -> local inference
   - BaseModel -> QAT/QAT-aware export -> quantized local inference
6. Real local runtime evidence for the final CLI acceptance matrix.
7. Window UI runnable and inspectable acceptance for every CLI-supported
   business line.
8. A final populated release evidence bundle that distinguishes:
   - unit tests
   - deterministic fixture tests
   - scored-trace evidence
   - real local runtime evidence

## Recommended Next Implementation Order

1. Land and undraft #394, #397, and #400 when CI and review are clean.
2. Use or extend the #400 acceptance bundle harness to run a configured
   real-local-runtime matrix and emit the final machine-readable #365 evidence
   bundle.
3. Promote QAT from deterministic fake-quant optimizer evidence to an
   MLX-native worker backend path, or keep MLX-native QAT explicitly unsupported
   with a final acceptance failure until the backend exists.
4. Integrate #366 reward-model training artifacts and PPO/reward-guided policy
   updates into RLHF before claiming RLHF completion.
5. Extend Window UI acceptance to consume the same real-runtime matrix evidence
   rather than screenshots or static routing tests.

## Audit Conclusion

Issue #365 is not complete. The current repository has strong contract,
manifest, offline preference, and quantization evidence foundations, plus three
active draft PRs for additional slices. The remaining acceptance items require
real runtime paths and release evidence, so this audit must not be used to mark
the objective complete.
