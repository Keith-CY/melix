# Issue 365 Completion Audit

## Objective

Complete https://github.com/Keith-CY/melix/issues/365: make alignment
algorithms and quantization optimization a real end-to-end post-training
product path from base model, through adapter training and alignment, through
export/merge and PTQ/QAT quantization, into local inference, CLI evidence, and
Window UI evidence.

This audit is the final Issue 365 source-of-truth evidence map. It records the
merged implementation slices, the merged-tree real-runtime evidence rerun, the
Window bridge evidence, and the #366 boundary.

## Audit Snapshot

- Date: 2026-05-07
- Base inspected: `origin/main` at
  `1e49c42a4bf4c6b0a48a51e5b8c84411be2ff52b`
- Merged Issue 365 PRs inspected:
  - #368, `Add Issue 365 alignment and quantization contracts`
  - #369, `Implement Issue 365 offline preference trainer routing`
  - #386, `Record quantization runtime smoke evidence`
  - #394, `Add scored RL alignment runner`
  - #397, `Add MLX quantization convert backend`
  - #400, `Add CLI pipeline chain routing slice`
  - #412, `Add Issue 365 Window acceptance matrix`
  - #442, `Route Issue 365 PTQ through MLX-LM conversion`
    - merge commit `964ba30f351336f04b20d05bd63500764daa5309`
  - #446, `Add Issue 365 QAT-aware MLX export`
    - merge commit `295d367bb7e05a8ac6a69b8a6075ee7386be7e8e`
  - #451, `Issue 365: wire reward runtime scoring`
    - merge commit `c595c48b8f0897c12a2d0e2eb571ca96ecdc884c`
  - #457, `Bridge Window acceptance to Issue 365 runtime evidence`
    - merge commit `1e49c42a4bf4c6b0a48a51e5b8c84411be2ff52b`
- Related support PRs inspected:
  - #393, `Add dataset management and selection`

## Issue Comment Adoption

The 2026-05-04 roadmap audit comment is reasonable and adoptable. Its findings
are now covered as follows:

- CPO, GRPO, RLHF mode contracts, dataset contracts, and alignment lineage are
  covered by #368, #394, and #451.
- DPO, ORPO, and CPO real offline preference trainer paths are covered by #369.
- Quantization manifest release-gate fields, PTQ runtime conversion, and local
  smoke evidence are covered by #368, #386, #397, and #442.
- QAT-aware export/runtime manifest behavior is covered by #397 and #446.
- `melix alignment train` parser, runner, codec, and pipeline routing are
  covered by #368 and #400.
- Window route evidence and Window-to-real-CLI readiness are covered by #412
  and #457.
- Reward-model training and PPO/reward-guided policy optimization remain #366
  scope. Issue 365 consumes reward-model manifests and records reward lineage;
  it does not claim reward-model construction or PPO.

The 2026-05-06 owner follow-up comment mapped the same work to the
#442/#446/#451/#457 stack. That stack has now landed, and the final evidence was
rerun from the merged `origin/main` tree.

## CI And Merge Note

PRs #442, #446, #451, and #457 were merged while GitHub-hosted `macos-15` CI
jobs were stuck in a long `QUEUED` state. At the time of the merge path:

- the branch protection REST API reported `main` as not protected
- the repository `main` ruleset had `enforcement=disabled`
- the PRs were mergeable but `UNSTABLE` because checks were still pending

This is an audit caveat rather than an ignored branch-protection failure. The
compensating evidence is the merged-tree rerun below from
`origin/main=1e49c42a4`, after the stack landed.

## Final Merged-Tree Evidence

### CLI Real Runtime Bundle

- Worktree: `.worktrees/issue365-final-main-audit`
- Base: `origin/main=1e49c42a4bf4c6b0a48a51e5b8c84411be2ff52b`
- Runtime instance: `i365-final-main`
- HTTP port: `12490`
- Worker sockets:
  - `/tmp/mx365-final-main-python.sock`
  - `/tmp/mx365-final-main-swift.sock`
- Bundle path:
  `.runtime/issue365/final-main-real-runtime-bundle-r2/bundle.json`
- Result:
  - `execution_mode=real`
  - `release_ready=true`
  - `succeeded_count=10`
  - `failed_count=0`
  - `blocked_count=0`

The first merged-tree CLI attempt wrote
`.runtime/issue365/final-main-real-runtime-bundle/bundle.json` and failed 7
alignment/quantization cases because the runtime input dataset directories were
empty. After populating the `preference_pair`, `prompt_candidate`,
`reward_scored`, `calibration`, and reward-model manifest fixtures, the `r2`
bundle passed all 10 cases.

Succeeded real CLI cases:

- `lora_export_inference`
- `qlora_export_inference`
- `dora_export_inference`
- `lora_dpo_export_inference`
- `lora_orpo_export_inference`
- `lora_cpo_export_inference`
- `lora_grpo_export_inference`
- `lora_rlhf_export_inference`
- `lora_preference_ptq_quantized_inference`
- `qat_quantized_inference`

### Window Bridge Bundle

- Worktree: `.worktrees/issue365-final-main-audit`
- Command entrypoint:
  `MELIX_PHASE8_WINDOW_UI_ACCEPTANCE=1 swift run --package-path apps/macos-menubar melix-menubar`
- Window bundle path:
  `.runtime/home-issue365-final-main/acceptance/phase8/window-ui/2026-05-07TFINALMAINR2Z/bundle.json`
- Consumed CLI bundle:
  `.runtime/issue365/final-main-real-runtime-bundle-r2/bundle.json`
- Screenshot PNG:
  generated during acceptance and removed from ignored `.runtime` storage after
  verification per operator request
- Result:
  - `schema_version=melix.phase8.window_ui_acceptance.v1`
  - `business_line_count=10`
  - `release_ready_count=10`
  - `blockers=[]`

Window timing metrics from the bundle:

- `phase8.ui.cli_bridge_ms=42897.08983898163`
- `phase8.ui.snapshot_render_ms=472.7550745010376`
- `phase8.ui.base_chat_roundtrip_ms=7414.916038513184`
- `phase8.ui.derived_chat_roundtrip_ms=5460.765957832336`
- `phase8.ui.bench_run_ms=7431.174993515015`
- `phase8.ui.bench_matrix_run_ms=7478.310942649841`
- `phase8.ui.evaluation_run_ms=5341.758966445923`

## Prompt-To-Artifact Checklist

| Issue requirement | Final merged evidence | Status |
| --- | --- | --- |
| `lora`, `qlora`, and `dora` supervised adapter training remains supported. | The merged-tree real CLI bundle records `lora_export_inference`, `qlora_export_inference`, and `dora_export_inference` as `succeeded` and `release_ready=true`. | Complete. |
| `dpo`, `orpo`, and `cpo` accept `preference_pair` datasets. | #368 adds the dataset contract and #369 adds offline preference trainer routing. The merged-tree real CLI bundle records all three preference chains as `succeeded` and `release_ready=true`. | Complete. |
| `dpo`, `orpo`, and `cpo` run real trainer paths rather than manifest-only placeholders. | #369 routes preference training through worker-side trainer logic and records preference metrics. The final real CLI bundle validates DPO/ORPO/CPO through full pipeline execution. | Complete. |
| `grpo` accepts prompt/candidate datasets and records candidate/reward traces. | #368 adds `prompt_candidate`; #394 adds scored-trace and generated-candidate evidence; #451 adds reward-runtime scoring. The final real CLI bundle records `lora_grpo_export_inference` as `succeeded` and `release_ready=true`. | Complete for #365 scope. |
| `rlhf` consumes reward-model lineage from #366 and records reward-model lineage. | #368 validates readable reward manifests; #394/#451 record reward-scored traces and runtime reward-model consumption. The final real CLI bundle records `lora_rlhf_export_inference` as `succeeded` and `release_ready=true`. | Complete for #365 lineage scope; reward-model training and PPO remain #366. |
| Every preference/RL run emits `melix.alignment_run.v1`. | #368 adds alignment manifests and adapter backlinks; #394/#451 expand scored-trace and runtime reward metrics. | Complete. |
| Adapter manifests backlink to alignment manifests through `alignment_run_manifest_path`. | #368 implementation and worker tests cover adapter backlinking. | Complete. |
| Quantized bundle manifests record `quantization_mode`, `source_artifact_kind`, and release-gate evidence. | #368/#386 add manifest and smoke evidence; #442/#446 exercise PTQ/QAT paths in the final real CLI bundle. | Complete. |
| PTQ can quantize exported or merged artifacts. | #397/#442 route PTQ through MLX-LM conversion. The final real CLI bundle records `lora_preference_ptq_quantized_inference` as `succeeded` and `release_ready=true`. | Complete. |
| QAT runs before final quantized export and records quantization-aware settings. | #397/#446 add QAT-aware export and trace/manifest evidence. The final real CLI bundle records `qat_quantized_inference` as `succeeded` and `release_ready=true`. | Complete. |
| QLoRA records quantized-base behavior and rejects unsafe targets. | Existing validation remains covered and the final real CLI bundle records `qlora_export_inference` as `succeeded` and `release_ready=true`. | Complete. |
| CLI exposes `melix alignment train` separately from `melix lora train`. | #368 adds parser/runner/codec support; #400 routes it through the pipeline harness. | Complete. |
| CLI supports a full chained workflow across training, alignment, publish/export, quantize, local inference, and eval/bench evidence. | #400 adds the 10-case harness. The final merged-tree real bundle passes all required cases. | Complete. |
| Required CLI chain tests exist for every listed business line. | The final real CLI bundle executes all 10 required business-line cases from the merged tree. | Complete. |
| Window UI exposes every CLI business line. | #412 exposes the Window 10-case business-line matrix. | Complete. |
| Window UI acceptance proves every business line is visible, selectable, runnable, and inspectable. | #457 bridges Window business-line evidence to the final real CLI bundle. The final Window bundle records 10 business lines, 10 release-ready cases, and no blockers. | Complete. |
| Release evidence separates deterministic/unit/scored-trace results from real local runtime results. | The Issue 365 bundle schema keeps plan/dry-run evidence non-release-ready and the final `r2` bundle is explicitly `execution_mode=real`. This audit separates unit/scored-trace history from final real CLI and Window bridge evidence. | Complete. |
| No business line is marked complete when only deterministic evidence exists. | The final completion claim is based on merged-tree real CLI runtime evidence plus Window bridge evidence, not deterministic-only output. | Complete. |

## Scope Boundary

Issue 365 is complete for the post-training alignment and quantization product
path it owns. The following are explicit non-claims:

- Reward-model training and PPO/reward-guided policy optimization remain #366.
- The Window evidence proves route visibility, selectability, runnability,
  inspectability, and release readiness through the mapped real CLI bundle. It
  does not claim separate manual click-through execution for every business line.
- Runtime `.runtime` evidence is local operator evidence and is intentionally
  not committed.

## Audit Conclusion

Issue #365 is complete within its scoped roadmap criteria. The current
`origin/main` tree includes the alignment, quantization, CLI, and Window bridge
slices, and the final merged-tree evidence passes:

- full real CLI matrix: 10/10 succeeded, `release_ready=true`
- Window bridge matrix: 10/10 release-ready business lines, no blockers

The #366 reward-model training/PPO boundary remains outside this completion
claim.
