# Melix

Melix is a local-first AI runtime for Apple Silicon. This context captures the core domain language used to describe its control plane, worker execution plane, and local inference capabilities.

## Language

**Swift Inference Worker Family**:
The set of Swift worker processes that own online serving and inference RPC execution across model capabilities while preserving the worker boundary from the control plane. Benchmark and evaluation orchestration may call this family but remain outside the term, as do model operations, training, registry tooling, and diagnostics unless explicitly brought into scope.
_Avoid_: Swift-only worker, Swift text worker, Python worker replacement

**Request Route**:
The worker selection for a single inference request, resolved from the model, requested task, and requested modalities. A single inference request must be executed end-to-end by one worker route rather than split across workers. A route matches when the request modalities are within the route's supported modalities and satisfy any required modality presence rule.
_Avoid_: Model route, route kind

**Request Modality**:
An input modality detected during control-plane admission from request content, such as text, image, audio, or video. Output artifacts are not request modalities unless they are also supplied as inputs. Text is present only when the request contains non-empty text content.
_Avoid_: Output modality, model capability

**Inference Task**:
The serving operation requested by a client after control-plane admission normalizes the request endpoint and content. The initial task set is `generate_text`, `generate_multimodal`, `embed`, `rerank`, `transcribe`, `speak`, `image_generate`, and `image_edit`.
_Avoid_: Model kind, model type, endpoint name

**Text Companion**:
An explicitly declared request route that lets a multimodal model serve text-only generation through a text worker. It is absent unless the model metadata declares support for that route, and it requires explicit multi residency when it can coexist with another residency for the same model. It cannot match image, video, or audio requests.
_Avoid_: Implicit fallback, text shortcut

**Request Route Declaration**:
Structured model metadata that declares which request routes a model supports. The model registry or catalog owns these declarations; the control plane consumes them instead of inferring routes from broad model kind labels, free-form extension strings, or legacy route classes. The same declaration is surfaced to workers for defensive validation.
_Avoid_: Control-plane route guess, model-kind routing

**Route Conflict**:
A pair of request route declarations for the same model whose task and modality match conditions cannot be resolved deterministically. Route conflicts are registry-load errors unless an explicit domain rule, such as Text Companion, resolves them.
_Avoid_: Route priority fallback, last route wins

**Registry-Load Validation**:
The validation that a model registry or catalog entry is well formed before Melix advertises the model as routeable. It catches invalid route declarations, conflicting routes, and impossible residency or modality rules before request admission.
_Avoid_: Request rejection, runtime fallback

**Legacy Route Inference**:
The deprecated practice of deriving serving routes from broad model kind labels, `route_class`, or free-form capability metadata instead of a request route declaration. New routing must reject requests without matching structured declarations.
_Avoid_: Route compatibility fallback, inferred worker family

**Runtime Family**:
A group of inference tasks that should share a worker process because they depend on the same runtime assets, preprocessing model, cache ownership, or artifact semantics. Runtime families are broader than individual inference tasks.
_Avoid_: Task worker, endpoint worker

**Worker Family**:
The routing target declared by a request route declaration. A worker family may have one or more worker instances; the initial worker families are `text`, `vision`, `audio`, `image`, `retrieval`, and `omni`.
_Avoid_: Worker route, worker socket, process name

**Worker Instance**:
A concrete running member of a worker family, identified by a stable worker identity and carrying its own readiness, active request count, and model residency state.
_Avoid_: Worker family, route class

**Worker Instance Selection**:
The control-plane choice of a concrete worker instance after request route resolution. It is deterministic for a given set of ready instances, request hints, residency state, and load counters.
_Avoid_: Family routing, load side effect

**Worker Capability Handshake**:
The control-plane-visible declaration by a running worker instance of its stable identity, worker family, and readiness to participate in request routing. It is the runtime counterpart to request route declarations, not a place to infer routes from legacy capability labels.
_Avoid_: Capability guess, route-class handshake

**Worker Defensive Validation**:
A worker-side safety check that an admitted request matches the worker family and request route declarations the worker is allowed to serve. It protects execution boundaries but does not replace control-plane admission or become a second route source of truth.
_Avoid_: Worker router, route inference fallback

**Route Selection Receipt**:
The observable admission artifact that records the resolved request route and selected worker instance for a request, including the inputs and state used for deterministic selection.
_Avoid_: Stream-only worker id, inferred route

**Vision Payload Receipt**:
The worker-side evidence that a Vision Worker received image or video inputs as media inputs for a request. It proves request payload preservation across the control-plane-to-worker boundary without recording raw media content.
_Avoid_: Raw media dump, text rewrite evidence

**Vision Worker**:
The Swift inference worker runtime family for image- or video-conditioned understanding tasks, including multimodal generation and OCR. It owns vision preprocessing and vision-model request execution, but not image artifact generation or editing, and not audio-bearing multimodal generation unless a request route explicitly assigns that execution to the Vision Worker.
_Avoid_: VLM worker, OCR worker

**Audio Worker**:
The Swift inference worker runtime family for audio input and output tasks, including transcription and speech generation. It owns audio preprocessing, audio runtime-pack readiness, locale and voice policy, and audio output formatting.
_Avoid_: STT worker, TTS worker

**Image Worker**:
The Swift inference worker runtime family for image artifact creation and modification tasks, including image generation and image editing. It owns image job execution, artifact persistence, and generated-artifact lineage.
_Avoid_: Vision worker, image-generation worker, image-edit worker

**Retrieval Worker**:
The Swift inference worker runtime family for retrieval-adjacent inference tasks, including embedding generation and reranking. It owns vector output and ranking-score execution without image, audio, or generated-artifact ownership.
_Avoid_: Embedding worker, rerank worker

**Text Worker**:
The Swift inference worker runtime family for text-only generation, including ordinary text models and explicitly declared text companions. It does not execute requests that include image, audio, or video inputs.
_Avoid_: Language worker, chat worker

**Omni Worker**:
The Swift inference worker runtime family for unified multimodal models whose single forward path can consume multiple media modalities in one request. It owns end-to-end execution for requests that cannot be assigned to Text Worker, Vision Worker, Audio Worker, Image Worker, or Retrieval Worker without splitting one model execution, including explicitly declared audio-bearing generation routes.
_Avoid_: Cross-worker multimodal pipeline, universal fallback

**Model Residency**:
The presence of a loaded model inside a specific worker family and worker instance. Residency is keyed by model, worker family, and worker instance rather than by model alone.
_Avoid_: Global loaded model, model dispatch handle

**Multi Residency**:
The same model being loaded in more than one worker family or worker instance. It is absent by default and must be explicitly declared because each residency consumes its own memory budget.
_Avoid_: Shared load, implicit duplicate load

**Vision Parity Fixture**:
A repository-owned fixture that freezes the externally observable behavior of existing Python vision execution before migration to the Swift Vision Worker. It captures request shapes, route expectations, outputs, errors, and observable receipts or metrics that a replacement worker must preserve, without requiring identical internal helper, patch, or runtime structure.
_Avoid_: Implementation parity, helper parity, Python clone

**Fixture Manifest**:
The contract document for a fixture suite. It indexes route expectations, model-family support, modality suites, scoring policy, media artifacts, and baseline references while keeping samples, baselines, and run outputs in separate artifacts. It is not a replacement source of truth for model registry route declarations.
_Avoid_: Sample dump, runtime result bundle

**Native Video Execution**:
Vision-worker execution that treats video as media input through video-aware preprocessing and model execution. It does not rewrite the video request into a text-only prompt and does not silently drop the video input. It must be evidenced by a video preprocessing receipt.
_Avoid_: Text-backed video prompt, video fallback prompt

**Video Preprocessing Receipt**:
The runtime evidence that a video request was decoded and sampled as video media before model execution. It records the media identity, decoder path, sampled frame evidence, processor metadata, frame budget, and preprocessing latency.
_Avoid_: Non-empty video answer, text-only video marker

**Route Contract Fixture**:
A fixture layer that validates request route resolution without executing model weights. It proves that model identity, inference task, requested modalities, worker family, residency rules, and admission errors produce the expected routing decision.
_Avoid_: Runtime fixture, model smoke

**Structured Route Rejection**:
An admission-time error that explains why no request route can execute a request. It names the model, task, requested modalities, modality suite, available routes, worker-family candidates, and reason so unsupported capability, missing declaration, unavailable worker, and residency denial are distinguishable.
_Avoid_: Worker failure, generic unsupported error, skipped fixture

**Deterministic Parity Fixture**:
A fixture layer that validates externally observable vision-worker behavior without relying on real model weights. It freezes deterministic request shaping, event streams, errors, and receipts or metrics.
_Avoid_: Real-model test, mock-only unit

**Real-Model Acceptance Fixture**:
A fixture layer that validates the same vision-worker behavior with actual local model weights. It proves that supported model families run through the real runtime path rather than only through deterministic or mocked execution.
_Avoid_: Synthetic fixture, route-only test

**Blocked Acceptance Artifact**:
A run artifact that records why a required acceptance gate could not execute. It is used for missing prerequisites such as model weights, judge targets, media artifacts, or baselines, and it is not a passing result.
_Avoid_: Skip, xfail, soft pass

**Semantic Acceptance Gate**:
A real-model acceptance criterion that uses Melix evaluation or judge scoring to validate model output against fixture expectations in addition to runtime correctness. For Python-to-Swift migration, it requires both an absolute score floor and a Python-baseline delta floor. It records the scoring mode, judge identity when used, prompt or rubric version, score, failures, and evidence artifacts. Mechanically checkable samples may use deterministic scoring; open-ended visual reasoning uses judge-backed semantic scoring.
_Avoid_: Runtime smoke, manual quality check

**Judge Audit Artifact**:
The persisted review record for judge-backed scoring. It explains how each judge-backed score was produced, including judge identity, prompt or rubric provenance, model answer, target, score, failure reason, and timing.
_Avoid_: Score-only artifact, terminal-only judge output

**Judge Score Cache**:
A constrained reuse mechanism for judge-backed scores. A cached score is valid only when the judge, prompt, rubric, sample, model answer, target, and media references all match; cache hits still produce judge audit artifacts.
_Avoid_: Global score cache, opaque judge reuse

**Frozen Python Baseline**:
An explicit acceptance artifact that records Python worker scores and provenance for a fixture manifest before migration. Swift acceptance reads this artifact for baseline comparison rather than rerunning Python during the Swift gate. Refreshing it is a separate, audited operation.
_Avoid_: Live Python comparison, implicit baseline

**Modality Suite**:
A group of fixture samples that exercise one media shape or interaction pattern for a model family. The initial required suites are image, multi-image, video, mixed image and video, OCR, and text-conditioned vision. Semantic acceptance is evaluated at this level so a broad family score cannot hide a modality-specific regression.
_Avoid_: Overall model score, task bucket

**Critical Sentinel Sample**:
A fixture sample that must pass individually because it protects a non-negotiable capability boundary such as native video execution. It cannot be hidden by aggregate semantic scores.
_Avoid_: Ordinary sample, weighted sample

**Temporal Video Sentinel**:
A critical video sample whose expected answer depends on temporal evidence across frames, such as order, change, or later-frame content. It prevents native-video acceptance from being satisfied by a static thumbnail or first frame.
_Avoid_: Static video sample, thumbnail check

**Fixture Media Artifact**:
An immutable media input owned by the fixture set and identified by path and content hash. Acceptance fixtures use these artifacts instead of live external URLs so image and video inputs remain reproducible.
_Avoid_: External URL input, floating media reference

**Model Family Acceptance Target**:
A real-model acceptance target defined at the model-family level and satisfied by one or more concrete model artifacts. It records both the family identity and the concrete model evidence so similarly configured families are not accidentally treated as interchangeable.
_Avoid_: Single model ID gate, display-name matching
