# Gemma 4 QAT MLX Support

## Goal

Define the Melix implementation path for Gemma 4 Quantization-Aware Training
(QAT) assets so Apple Silicon operators can discover, import, serve, and
measure official or community-converted QAT MLX model assets without confusing
them with Melix's existing adapter-derived QAT export workflow.

## Confirmed Direction

The first supported direction is MLX-first:

- Prefer existing Hugging Face MLX QAT assets when available.
- Do not implement local conversion from Google's `qat-q4_0-unquantized`
  checkpoints in the first implementation path.
- Keep QAT assets inside the existing `Model Asset` category and expose QAT as
  lineage, quantization metadata, and compatibility receipts rather than as a
  separate operator-facing asset category.
- Pair compatible Gemma 4 QAT target assets with matching MTP assistant assets
  automatically by default for prompt-only speculative decode, while allowing an
  explicit operator override for compatibility experiments.
- If no compatible draft companion is present, baseline generation remains
  available and speculative capability is marked degraded; Melix must not
  automatically download the missing companion.
- Keep compressed-tensors, mobile compressed-tensors, and LiteRT-LM/mobile
  runtime support outside the first implementation slice, but keep those assets
  visible in Hub and Models surfaces as unsupported for Melix-native serving.
- Limit automatic support, automatic pairing, and release-gate evidence in the
  first slice to `mlx-community/gemma-4-*qat*` assets. Other organizations'
  Gemma 4 QAT MLX assets remain visible but experimental and require manual
  operator selection.

Current Hugging Face API evidence on 2026-06-07 shows these relevant MLX QAT
assets already exist:

- `mlx-community/gemma-4-E2B-it-qat-4bit`
- `mlx-community/gemma-4-E4B-it-qat-4bit`
- `mlx-community/gemma-4-12B-it-qat-4bit`
- `mlx-community/gemma-4-26B-A4B-it-qat-nvfp4`
- matching `mlx-community/gemma-4-*-it-qat-assistant-*` MTP assistant variants
  for E2B and E4B, with tags such as `mtp`, `speculative-decoding`, and
  `draft-model`.

## Non-Goals

- Do not make Google compressed-tensors (`*-ct`) assets a native Melix runtime
  target in the first slice.
- Do not add a LiteRT-LM or mobile-transformers runtime in the first slice.
- Do not implement a local conversion fallback from Google unquantized QAT
  checkpoints in the first slice.
- Do not add a distinct QAT asset category beside `Model Asset`.
- Do not automatically download a missing draft companion during model import,
  server creation, or chat execution.
- Do not reclassify Melix's existing adapter-derived QAT export path as official
  Gemma 4 QAT checkpoint support.
- Do not hand-roll Gemma 4 speculative verification outside the existing
  MLX/MLX-VLM drafter integration boundary.

## Existing Anchors

- `CONTEXT.md` defines `Model Asset` as a downloaded, imported, or
  remote-referenced model artifact managed by the Models domain.
- `docs/plans/2026-05-06-gemma4-mtp-speculative-decode.md` already defines the
  prompt-only Gemma 4 MTP speculative decode boundary and keeps multimodal MTP
  out of scope until upstream support is stable.
- `services/mlx-worker-python/worker/model_registry/catalog.py` already detects
  Gemma 4 MTP assistant assets and marks them with
  `melix.speculative.role=assistant`, `melix.speculative.kind=mtp`, and
  `melix.serving.hidden=true`.
- `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`
  already has `quantization_mode=qat`, but that path currently describes
  adapter-derived QAT-aware export evidence and MLX-LM conversion rather than
  official Google Gemma 4 QAT asset import.

## Required Optimizations

1. Model registry and Hub catalog detection
   - Recognize `mlx-community/gemma-4-*-qat-*` target assets as Gemma 4 QAT MLX
     model assets.
   - Treat third-party Gemma 4 QAT MLX assets outside `mlx-community` as
     experimental manual imports: visible, inspectable, but excluded from
     automatic pairing and release gates.
   - Keep non-MLX Gemma 4 QAT assets visible but blocked with local-fit evidence
     such as `local_fit_status=blocked`, `recommended_action=unavailable`, and an
     unsupported runtime format reason.
   - Preserve base-model lineage from Hugging Face tags such as
     `base_model:google/gemma-4-*-qat-q4_0-unquantized`.
   - Distinguish QAT MLX assets from ordinary PTQ MLX assets and from Melix
     adapter-derived QAT export bundles.
   - Keep MTP assistant variants hidden from normal serving pickers while still
     making them available as compatible draft companion assets.

2. Model asset metadata and compatibility receipts
   - Record QAT source lineage, quantization family, MLX quantization mode, and
     draft companion compatibility in stable metadata.
   - Expose compatibility receipts that show whether the asset can serve
     text-only, multimodal, and prompt-only speculative decode requests.
   - Surface missing or mismatched draft companion assets as degraded speculative
     capability, not as a failure to serve baseline generation.
   - Include an explicit operator remediation such as downloading or selecting a
     compatible draft companion, but do not perform that remediation implicitly.

3. Import and fallback conversion flow
   - Prefer direct download/import of existing MLX QAT assets.
   - Reject or defer non-MLX QAT assets instead of converting them locally in the
     first slice, while keeping their catalog rows visible with explicit
     unsupported-format evidence.
   - Keep imported assets tied back to source model, QAT lineage, and local smoke
     evidence.

4. Runtime loading and routing
   - Validate that target QAT MLX assets load through the existing MLX/MLX-VLM
     runtime path before advertising them as routeable.
   - Patch the current MLX-VLM Gemma 4 load boundary for QAT shared-KV layouts
     where `num_kv_shared_layers` omits K/V projection and norm weights from
     later layers.
   - Normalize current MLX-VLM `load_drafter()` results from `(model,
     resolved_kind)` to the drafter model object expected by `generate_step()`.
   - Preserve the current boundary that media-bearing requests do not enter the
     MTP speculative path.
   - Bind compatible draft companion assets only for prompt-only Gemma 4
     text-backed speculative decode.
   - Default pairing should match family, size, QAT lineage, and quantization
     family. Operator override remains available for advanced experiments such
     as comparing bit widths or using a BF16 companion.
   - Automatic pairing should only use `mlx-community` first-slice assets.

5. Measurement and release gates
   - Add real-model smoke evidence for both E2B and E4B QAT 4-bit targets with
     matching draft companions.
   - Keep E2B as the lightweight default development smoke and E4B as the
     release/performance evidence target.
   - Measure memory footprint, load latency, TTFT, decode tokens per second,
     speculative acceptance counters, fallback counters, and baseline-vs-MTP
     deltas.
   - Keep quantization release evidence separate from LoRA/adaptation quality
     metrics.

## Work Plan

1. Add Hub/catalog tests for Gemma 4 QAT MLX target and draft companion assets.
2. Add registry metadata for QAT lineage and draft companion compatibility.
3. Add import/download behavior that accepts existing MLX QAT assets and rejects
   non-MLX QAT assets with an explicit unsupported-format reason.
4. Extend compatibility receipts and route declarations so baseline serving,
   multimodal serving, and prompt-only speculative decode are independently
   visible.
5. Add runtime smoke and performance evidence for E2B and E4B QAT 4-bit targets
   plus matching draft companions.
6. Update operator-facing docs after the implemented slices produce evidence.

## Delivery Slices

1. Registry and catalog foundation
   - Land QAT MLX target detection, draft companion detection, QAT lineage
     metadata, automatic pairing, override metadata, and explicit non-MLX QAT
     blocked/unavailable classification before adding real runtime gates.
   - Keep first-slice automatic support scoped to `mlx-community` model IDs and
     classify other organizations' QAT MLX assets as experimental.
   - This slice should be covered by deterministic Hub/catalog fixtures and does
     not require downloading model weights.
2. Compatibility receipts and operator surfaces
   - Surface baseline generation, multimodal generation, prompt-only speculative
     decode, degraded missing-companion state, and hidden draft companion status
     from stable metadata.
   - Keep server creation and chat admission available for baseline generation
     when the draft companion is missing.
   - Emit receipt-ready `melix.acceleration.*` metadata from the model registry
     rather than adding a separate QAT asset category or a Gemma-specific
     control-plane receipt path.
3. Runtime evidence and release gates
   - Add real-model E2B and E4B QAT smoke/performance evidence after the metadata
     contract is stable, so runtime probes use the same IDs and pairing rules as
     production.

## Verification

Slice 1 focused verification:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_model_registry_catalog.py \
  services/mlx-worker-python/tests/test_hub_catalog.py
```

Expected slice 1 behavior evidence:

- `mlx-community/gemma-4-*qat*` MLX targets receive QAT lineage metadata and a
  deterministic `melix.draft_companion.auto_pair_key`.
- Matching `mlx-community/gemma-4-*qat-assistant*` assets remain hidden normal
  serving targets and are marked as MTP draft companions.
- Non-MLX Gemma 4 QAT CT/mobile/LiteRT assets remain visible in Hub catalog
  responses but are marked unavailable with an explicit unsupported runtime
  format.
- Gemma 4 QAT MLX assets outside `mlx-community` remain visible but require
  manual experimental import/selection.

Slice 2 focused verification:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_model_registry_catalog.py \
  services/mlx-worker-python/tests/test_hub_catalog.py
```

Expected slice 2 behavior evidence:

- Matching automatic-scope Gemma 4 QAT target and assistant assets with the same
  `melix.draft_companion.auto_pair_key` produce target-side
  `melix.draft_companion.status=available`,
  `melix.draft_companion.model_ids=<assistant-id>`,
  `melix.acceleration.supported_modes=baseline,speculative_decode`,
  `melix.acceleration.valid_draft_model_ids=<assistant-id>`,
  `melix.acceleration.target_capability=speculative_decode`, and
  `melix.acceleration.drafter_capability=speculative_draft`.
- Hidden assistant assets produce
  `melix.draft_companion.status=available` and
  `melix.acceleration.drafter_capability=speculative_draft`, with
  `melix.draft_companion.target_model_ids` added only when a compatible target is
  present in the same registry snapshot.
- Missing assistant assets produce
  `melix.draft_companion.status=missing` and an explicit remediation hint while
  preserving `baseline` in `melix.acceleration.supported_modes`. The target keeps
  `speculative_decode` visible as degraded capability but omits
  `melix.acceleration.valid_draft_model_ids`, so the existing control-plane
  acceleration receipt resolves speculative requests back to baseline with a
  missing-draft reason.
- Automatic pairing remains limited to `mlx-community` Gemma 4 QAT MLX assets;
  third-party QAT MLX assets remain manual experimental imports.

Slice 3 focused verification:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_mlx_vlm_runtime.py \
  tests/test_gemma4_qat_runtime_evidence.py
```

Real-model E2B evidence command:

```bash
E2B_TARGET_SNAPSHOT="$(PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx python - <<'PY'
from huggingface_hub import snapshot_download
print(snapshot_download(repo_id="mlx-community/gemma-4-E2B-it-qat-4bit", revision="main", local_files_only=True))
PY
)"
E2B_DRAFT_SNAPSHOT="$(PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx python - <<'PY'
from huggingface_hub import snapshot_download
print(snapshot_download(repo_id="mlx-community/gemma-4-E2B-it-qat-assistant-bf16", revision="main", local_files_only=True))
PY
)"
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx python \
  scripts/gemma4_qat_runtime_evidence.py \
  --target-model-id mlx-community/gemma-4-E2B-it-qat-4bit \
  --draft-model-id mlx-community/gemma-4-E2B-it-qat-assistant-bf16 \
  --target-model-path "$E2B_TARGET_SNAPSHOT" \
  --draft-model-path "$E2B_DRAFT_SNAPSHOT" \
  --max-tokens 16 \
  --num-draft-tokens 6 \
  --output .runtime/gemma4-qat-runtime-evidence/e2b.json
```

Real-model E4B evidence command:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx python \
  scripts/gemma4_qat_runtime_evidence.py \
  --target-model-id mlx-community/gemma-4-E4B-it-qat-4bit \
  --draft-model-id mlx-community/gemma-4-E4B-it-qat-assistant-bf16 \
  --download \
  --max-tokens 16 \
  --num-draft-tokens 6 \
  --output .runtime/gemma4-qat-runtime-evidence/e4b.json
```

Slice 3 real-model evidence captured on 2026-06-07:

- E2B target `mlx-community/gemma-4-E2B-it-qat-4bit` with
  `mlx-community/gemma-4-E2B-it-qat-assistant-bf16`: baseline passed,
  speculative decode passed, no implicit download, no baseline fallback,
  completion tokens 16, baseline TTFT 826.231 ms, baseline decode 6.7079 tok/s,
  baseline peak memory 4.4001 GB, speculative TTFT 3129.294 ms, speculative
  decode 5.5667 tok/s, speculative peak memory 4.5566 GB, acceptance rate 0.2,
  accepted tokens 8, rejected tokens 32, decode delta -17.0128 percent.
- E4B target `mlx-community/gemma-4-E4B-it-qat-4bit` with
  `mlx-community/gemma-4-E4B-it-qat-assistant-bf16`: baseline passed,
  speculative decode passed, explicit download performed, no implicit download,
  no baseline fallback, completion tokens 16, baseline TTFT 140.748 ms,
  baseline decode 68.4346 tok/s, baseline peak memory 6.9023 GB,
  speculative TTFT 277.052 ms, speculative decode 72.5255 tok/s, speculative
  peak memory 7.0606 GB, acceptance rate 0.3, accepted tokens 9, rejected tokens
  21, decode delta +5.9778 percent.

Slice 3 runtime notes:

- Short smoke samples are release-gate compatibility evidence, not a stable
  performance claim. The E2B sample regressed decode throughput while the E4B
  sample improved it.
- Prompt-only Gemma 4 QAT requests may use MTP through the current MLX-VLM
  `generate_step()` path. Media-bearing Gemma 4 requests still remain outside
  MTP and use baseline generation.
- The evidence script requires an existing local target and draft snapshot by
  default. `--download` is explicit and records `download_performed`; Melix
  runtime generation still does not implicitly download missing companions.

Slice 1 coverage and metrics command:

```bash
mkdir -p .runtime/coverage && \
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx coverage run \
  --source=services/mlx-worker-python/worker,services/mlx-worker-python/tests \
  -m pytest -q \
  services/mlx-worker-python/tests/test_model_registry_catalog.py \
  services/mlx-worker-python/tests/test_hub_catalog.py && \
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx coverage json \
  -o .runtime/coverage/gemma4_qat_catalog.json && \
python3 scripts/changed_scope_coverage.py \
  --coverage-json .runtime/coverage/gemma4_qat_catalog.json \
  services/mlx-worker-python/worker/model_registry/catalog.py \
  services/mlx-worker-python/worker/model_ops/hub_catalog.py \
  services/mlx-worker-python/tests/test_model_registry_catalog.py \
  services/mlx-worker-python/tests/test_hub_catalog.py
```

Slice 1 runtime metrics are `N/A`: this slice changes deterministic model
catalog and registry metadata only, with no model load, token generation, or
request path execution. Runtime E2B/E4B smoke, memory, TTFT, decode rate, and
speculative acceptance metrics remain part of slice 3.

Slice 2 runtime metrics are also `N/A`: this slice enriches registry metadata for
existing capability receipts only. It does not load QAT weights, start a server,
or execute prompt-only speculative decode. Runtime E2B/E4B smoke, memory, TTFT,
decode rate, and speculative acceptance metrics remain part of slice 3.

Final implementation verification must also include the relevant repository
gates from `AGENTS.md`. Slice 3 must run real-model E2B/E4B probes and the
registered PR-scoped performance report before release-gate claims.

## Acceptance Criteria

- Gemma 4 QAT MLX target assets are discoverable and distinguishable from PTQ
  assets.
- First-slice automatic support and release-gate evidence are scoped to
  `mlx-community/gemma-4-*qat*` target and draft companion assets.
- Compatible QAT draft companion assets are discoverable but hidden from normal
  serving target lists.
- Baseline generation remains available when assistant pairing is missing.
- Missing draft companion state is reported as degraded speculative capability
  with an explicit operator remediation and no implicit download.
- Prompt-only speculative decode records MTP evidence when a compatible assistant
  is paired.
- E2B and E4B QAT 4-bit targets each have real-model smoke evidence with their
  matching draft companions.
- Mobile/CT/LiteRT assets are not advertised as first-slice Melix-native
  runtime targets, but remain visible with explicit unsupported runtime format
  evidence.
