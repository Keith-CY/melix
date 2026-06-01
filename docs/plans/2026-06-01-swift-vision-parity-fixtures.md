# Swift Vision Parity Fixtures

## Goal

Define the fixture gate that must exist before migrating Python VLM execution to
the Swift Vision Worker. The gate freezes externally observable Python vision
behavior where it remains product intent, while intentionally replacing
text-backed or backend-unsupported video fallbacks with native video execution
requirements.

## Scope

- Request route contract fixtures for Text Worker and Vision Worker routing.
- Deterministic parity fixtures for Python VLM externally observable behavior.
- Real-model acceptance fixtures for Gemma 4, Qwen 3.5, and Qwen 3.6.
- Native video execution requirements for all three target model families.
- Explicit rejection of audio-bearing generation unless an Omni route is
  declared.

Out of scope for this first fixture gate:

- Audio input or output generation inside the Vision Worker.
- Image generation, image editing, embeddings, rerank, transcription, or speech.
- Preserving Python implementation structure, helper names, monkey patches, or
  fallback internals when the observable contract is replaced by a stricter
  route rule.

## Terms

The governing domain terms are defined in `CONTEXT.md`:

- Request Route
- Request Modality
- Request Route Declaration
- Route Conflict
- Legacy Route Inference
- Worker Family
- Worker Instance
- Worker Instance Selection
- Route Selection Receipt
- Vision Worker
- Text Companion
- Model Residency
- Multi Residency
- Vision Parity Fixture
- Fixture Manifest
- Route Contract Fixture
- Structured Route Rejection
- Deterministic Parity Fixture
- Real-Model Acceptance Fixture
- Blocked Acceptance Artifact
- Semantic Acceptance Gate
- Judge Audit Artifact
- Judge Score Cache
- Frozen Python Baseline
- Modality Suite
- Critical Sentinel Sample
- Temporal Video Sentinel
- Fixture Media Artifact
- Model Family Acceptance Target
- Native Video Execution
- Video Preprocessing Receipt

## Fixture Layers

## Fixture Layout

The first gate uses one suite manifest plus separate artifact files:

- `manifest.json`: schema version, model families, route expectations, suite
  support matrix, scoring policy, media index, and baseline artifact references.
- `samples.jsonl`: per-sample requests, expected targets, modality suite,
  scoring mode, and sentinel markers.
- `baselines/*.json`: frozen Python baseline artifacts.
- Runtime output directory: Swift acceptance outputs, judge prompt snapshots,
  judge audits, receipts, metrics, and timing.

The manifest is the fixture contract. Samples, baselines, and run outputs remain
separate so each artifact can be reviewed and diffed independently.

The manifest is not a second source of truth for serving route declarations.
Route contract tests must read request route declarations through the real
generated protobuf and model registry loading path, then compare the resolved
routes and errors with manifest expectations. Fixture tests must not construct
fake routes that bypass the registry path.

For Slice 1, `manifest.json` contains route contract expectations rather than
serving route declarations. The required manifest sections are:

- `schema_version`
- `fixture_suite_id`
- `model_fixtures`
- `worker_fixtures`
- `route_contract_cases`
- `receipt_artifacts`
- `metrics_policy`

Each `route_contract_cases` entry includes:

- `case_id`
- `model_id`
- `request_shape`
- `expected_task`
- `expected_request_modalities`
- `expected_route` for success cases
- `expected_worker_instance_id` for success cases that select an instance
- `expected_route_selection_receipt` for success cases that require a receipt
- `expected_payload_receipt` for Vision Worker payload preservation cases
- `expected_error` for admission or defensive-validation failure cases

The manifest never embeds authoritative `request_routes`. It may name the model
fixture and expected route outcome, but the actual declarations must be loaded
through the registry and generated protobuf path.

Slice 1 runtime artifacts use these stable relative paths under the fixture run
output directory:

- `receipts/route-selection.jsonl`
- `receipts/vision-payload.jsonl`
- `registrations/rejections.jsonl`
- `errors/route-rejections.jsonl`
- `errors/registry-validation.jsonl`
- `metrics/route-contract-summary.json`

Artifact writers must create parent directories before writing and must not
write outside the fixture run output directory.

### Route Contract Fixtures

Route contract fixtures do not load model weights. They validate route
resolution from:

- model identity
- inference task
- requested modalities
- request route declarations
- residency policy
- worker family availability
- worker instance readiness, residency, and load counters

Slice 1 route contract coverage has three layers. Modality extraction unit tests
cover text emptiness, MIME type normalization, filename and URL extension
inference, unknown media errors, and request modality sets before route matching.
Resolver unit tests cover the task, modality, route declaration, residency, and
deterministic instance selection rules directly. Control-plane admission
integration tests cover the real `ModelSummary` and `WorkerSummary` path so the
externally exercised route contract does not diverge from the resolver unit
behavior.

The route resolver input contract is:

- normalized `model_id`
- normalized `task`
- canonical `request_modalities`
- `ModelSummary.request_routes`
- ready worker instances keyed by stable worker instance id
- worker family, active request count, and loaded model residency per instance
- optional internal preferred worker instance id

The route resolver output contract is either:

- a selected route declaration, selected worker instance id, selection reason,
  and route selection receipt payload; or
- a structured route rejection `ErrorStatus`.

The resolver is side-effect-free. It does not load, unload, migrate, duplicate,
or warm up models. It only returns the selected route, selected worker instance,
receipt payload, or route rejection. Later control-plane stages perform
`ensure model loaded` when the selected route and residency policy allow it.
Resolver behavior must not depend on Swift dictionary iteration order. It sorts
worker instance ids, modality sets, and resident model records according to the
canonical ordering rules before comparing or emitting artifacts.

Modality extraction unit tests are table-driven code tests, not manifest-driven
fixture cases. The fixture manifest remains focused on route, worker family, and
worker instance contract scenarios.

Slice 1 modality extraction unit tests are Swift control-plane tests only. The
Swift control plane owns admission parsing and route matching. Python worker
coverage remains defensive validation and must not become a second source of
truth for request modality extraction.

Python worker defensive validation in the first route contract only validates
normalized task, request modalities, selected worker family, and
`ModelSpec.request_routes` consistency. It must not re-parse MIME types, URLs,
or filenames as an alternate admission path.

Swift Text Worker defensive validation also reads `ModelSpec.request_routes`.
It rejects requests whose normalized route does not match a Text Worker route,
including non-text worker families and non-text-only request modality sets. It
does not re-parse MIME types, URLs, or filenames.

Swift Vision Worker defensive validation reads `ModelSpec.request_routes` and
rejects requests that do not match a Vision Worker route. In Slice 1 it rejects
any request modality set containing `audio`; audio-bearing generation requires a
future explicit Omni route rather than Vision Worker handling.

Worker defensive validation failures use `ErrorStatus.code = route_not_supported`
and `ErrorStatus.retriable = false`. The message must identify the failure as
worker defensive validation so it is distinguishable from control-plane
admission rejection during diagnosis.
They use the same required `ErrorStatus.details` keys as control-plane
structured route rejection.
Worker defensive validation uses the same reason set with worker-specific
boundaries: task mismatches use `no_route_for_task`, modality mismatches use
`no_route_for_modalities`, worker family mismatches use
`worker_family_mismatch`, and native-video flag mismatches use
`native_video_required`.

Worker defensive validation coverage has two layers. Unit tests cover the
validation function directly. Worker process contract tests invoke the real
worker RPC or IPC path and assert the returned `ErrorStatus` code, retriable
flag, message, details, and reason.
Both the Swift Text Worker and Swift Vision Worker require these two coverage
layers. Python worker defensive validation may remain during migration, but it
is not the target serving path for the unified Swift worker direction.

Control-plane admission integration tests must use real worker processes and the
real registration and capability handshake path. They must not satisfy the
admission contract by injecting synthetic `WorkerSummary` records only. The
route contract layer still does not require loading model weights.

The worker capability handshake must expose typed `worker_family`. Legacy
capability class or `route_class` fields may remain for compatibility inside the
protocol surface, but they must not participate in new request route matching.
If a worker capability handshake omits `worker_family` or reports
`WORKER_FAMILY_UNSPECIFIED`, the control plane treats that worker as unavailable
for structured request routing. If a matched route requires that family and no
other ready worker can serve it, admission fails with
`worker_family_unavailable`.
In Slice 1, a worker process declares exactly one `worker_family`. A single
worker instance must not advertise multiple worker families. Models that need
multiple worker families use multiple worker instances and explicit route
declarations rather than a multi-family worker process.
If the protocol surface represents this as a repeated `worker_families` field,
Slice 1 validation requires exactly one concrete family. If the protocol surface
uses a single enum field, the same constraint is satisfied by the field shape.
Worker instance ids come from worker process startup configuration and are
reported during capability handshake. The control plane validates uniqueness
within its live worker registry but does not mint fixture-visible worker
instance ids. This lets Slice 1 fixtures declare stable worker instance ids and
assert deterministic selection.
If a second live worker reports a worker instance id that is already registered,
the control plane rejects the second registration and keeps the existing
registration unchanged. It must not auto-rename worker instance ids.
Slice 1 includes an integration fixture for duplicate worker instance ids. The
fixture asserts that the duplicate registration is rejected, the original
registration remains the only selection candidate for that id, and deterministic
instance selection is not polluted by the rejected worker.
Rejected worker registration writes a registration rejection artifact with the
reported worker instance id, reported `worker_family`, rejection reason, and the
existing registration that caused the conflict. This artifact is for test and
diagnostic use and is not a public API response.

Slice 1 may use lightweight test worker binaries or stub runtimes for these
integration tests, as long as they implement the real worker protocol,
registration flow, and capability handshake. Route contract tests must not be
coupled to model weight loading or real inference cost.

Test workers must declare concrete worker families such as `text` and `vision`.
A single universal stub that claims every worker family is not sufficient for
the Slice 1 route contract because it can hide family selection and
`worker_family_unavailable` behavior.

Text Worker contract tests must use a real Swift Text Worker process. They must
not route through the Python worker or satisfy the Text Worker contract with a
stub-only process. Stub runtimes may still support non-Text admission scenarios
where real inference is not under test.

Vision Worker contract tests must use a real Swift Vision Worker process. They
may use a stub model or stub runtime for Slice 1 so the test validates the real
worker family, registration, handshake, route, and admission path without
requiring real VLM execution. Real-model Vision acceptance remains in Slice 2.
Slice 1 therefore includes a minimal Swift Vision Worker executable. The
executable may use a stub runtime for Slice 1, but it must participate in the
real worker process lifecycle, registration flow, capability handshake, route
validation, and request payload receipt path.
The minimal Swift Vision Worker should share the Swift worker server framework
with the Swift Text Worker. The first intended differences are the declared
`worker_family` and the runtime adapter; process lifecycle, registration,
capability handshake, route validation, and receipt plumbing should not fork
into a separate framework.

The shared Swift worker server framework needs a route-validating runtime
adapter boundary. The exact Swift type name may be chosen during implementation,
but the boundary must let Text and Vision adapters expose their `worker_family`,
the request routes they can serve, and a request validation hook used before
runtime execution.
The adapter's supported routes are derived by filtering `ModelSpec.request_routes`
for the adapter's `worker_family`. Runtime adapters must not declare a separate
static route table that becomes a third source of truth.

Slice 1 Vision Worker contract tests must also verify the worker receives media
inputs as media inputs. The test worker writes a payload receipt showing image
and video request parts reached the Swift Vision Worker without being rewritten
by the control plane into text-only prompts.

The Vision Worker payload receipt is JSONL. Each worker request writes one JSON
object line.

The first Vision Worker payload receipt records structure only, not raw media
content. It includes:

- `request_id`
- `task`
- `modalities_seen`
- `media_parts`
- `text_part_count`

Each `media_parts` entry includes `kind`, `media_id` or `sha256`, and
`mime_type`.

`modalities_seen` uses the same fixed canonical order as route selection
receipts: `text`, `image`, `audio`, `video`.

For Slice 1 Vision Worker payload receipts, `media_parts.kind` is limited to
`image` and `video`. Audio-bearing requests must be rejected by route admission
or routed by an explicit Omni route; they must not reach the Vision Worker
payload contract.

For mixed image and video requests, the Vision Worker payload receipt must
include both image and video entries in `media_parts`. The paired route
selection receipt must show `request_modalities` as either `[text, image,
video]` or `[image, video]`, depending on whether the request included a
non-empty text part.

Required route scenarios:

- Text model: `generate_text + [text] -> text`
- Vision model image request:
  `generate_multimodal + [text,image] -> vision`
- Vision model media-only image request:
  `generate_multimodal + [image] -> vision`
- Vision model request with whitespace-only text plus image:
  `generate_multimodal + [image] -> vision`
- Vision model media-only video request:
  `generate_multimodal + [video] -> vision` only when the route declares
  `supports_native_video = true`
- Vision model text-only with explicit Text Companion:
  `generate_text + [text] -> text`
- Same Vision model id with explicit Text Companion and Vision routes:
  text-only requests select the Text Worker route, while image requests select
  the Vision Worker route
- Same Vision model id with explicit Text Companion and Vision routes but
  without `residency_policy = allow_multi_residency` where co-residency is
  required:
  registry-load validation error
- Same Vision model id with explicit Text Companion and Vision routes and
  `residency_policy = allow_multi_residency`:
  route selection for the Text Worker is not blocked by existing Vision Worker
  residency; Slice 1 asserts selection, while duplicate load success is covered
  outside the route contract fixture
- Same Vision model id with Text Companion route using single residency while
  the model is already resident on a Vision Worker instance:
  admission error with `multi_residency_denied`
- Text Companion route with `worker_family` other than `text`:
  registry-load validation error
- Text Companion route with `supported_modalities` containing `image`, `video`,
  or `audio`:
  registry-load validation error
- Text Companion route with non-empty `requires_any_modality`:
  registry-load validation error
- Text Companion route with `supports_native_video = true`:
  registry-load validation error
- Vision model text-only without explicit Text Companion:
  `generate_text + [text] -> vision` when the model declares that route
- Vision model with audio and no explicit Omni route:
  admission error
- Vision model with video:
  allowed only when the request route declares native video support
- Vision model with video and a matching modality route that has
  `supports_native_video = false`:
  admission error with `native_video_required`
- Vision model with video and no route covering the `video` modality:
  admission error with `no_route_for_modalities`
- Route with `supports_native_video = true` but without `video` in
  `supported_modalities`:
  registry-load validation error
- Route with `video` in `supported_modalities` and
  `supports_native_video = false`:
  registry-load succeeds, but matching video requests fail admission with
  `native_video_required`
- Route with `requires_any_modality` containing a modality that is not present
  in `supported_modalities`:
  registry-load validation error
- Route with empty `supported_modalities`:
  registry-load validation error
- Image generation:
  `image_generate + [text] -> image` when a text prompt is present
- Image generation with empty or whitespace-only prompt:
  `image_generate + []` fails admission with `no_route_for_modalities`
- Image editing:
  `image_edit + [image]` or `image_edit + [text,image] -> image`
- Image editing with source image and no mask:
  `image_edit + [image] -> image`
- Image editing with text prompt but no source or mask image:
  `image_edit + [text]` fails admission with `no_route_for_modalities`
- Missing matching route:
  admission error with model id, task, requested modalities, available routes,
  and reason
- Request with empty `request_modalities`:
  admission error with `no_route_for_modalities`
- Whitespace-only text request with no media:
  extracts empty `request_modalities` and fails admission with
  `no_route_for_modalities`
- Request with an unknown media type:
  admission error with `invalid_request_media_type` before route matching
- Legacy route fields without structured `request_routes`:
  admission error with `route_not_supported`
- Preferred worker instance hint points to an instance in the wrong
  `worker_family`:
  hint is ignored, selection continues by residency, load, and stable-id rules
- Preferred worker instance hint points to an unknown instance id:
  hint is ignored, selection continues by residency, load, and stable-id rules
- Preferred worker instance hint points to a known but not-ready instance:
  hint is ignored, selection continues across ready candidates in the matched
  `worker_family`
- Matched `worker_family` has instances but all are not ready:
  admission error with `worker_family_unavailable`
- Matched `worker_family` has no registered instances:
  admission error with `worker_family_unavailable`
- Worker capability handshake omits `worker_family` or reports
  `WORKER_FAMILY_UNSPECIFIED`:
  worker is ignored for structured request routing; if no other ready worker can
  serve the matched family, admission error with `worker_family_unavailable`
- Duplicate worker instance id during capability handshake:
  second registration is rejected, original registration remains unchanged, and
  the rejected worker does not enter the route selection candidate set

The required scenarios are grouped into these Slice 1 test categories:

- route matching success
- route matching rejection
- registry-load validation rejection
- modality extraction normalization
- worker family availability
- worker instance selection
- worker registration rejection
- worker defensive validation
- receipt artifact emission
- no-legacy-route-inference guard

No legacy route inference is allowed in the first gate. `route_class` and
`melix.capability.route_kind` must not create, fill in, or broaden
`request_routes`. If a model has no matching structured request route, the
control plane must reject the request during admission.

Structured route rejection fixtures must assert this error shape:

- `ErrorStatus.code = route_not_supported`
- `ErrorStatus.retriable = false`
- `ErrorStatus.message` with a human-readable admission summary
- `ErrorStatus.details.model_id`
- `ErrorStatus.details.task`
- `ErrorStatus.details.requested_modalities`
- `ErrorStatus.details.required_modality_suite`
- `ErrorStatus.details.available_routes`
- `ErrorStatus.details.available_modality_suites`
- `ErrorStatus.details.worker_family_candidates`
- `ErrorStatus.details.reason`

Structured route rejection fixtures also write `errors/route-rejections.jsonl`.
Each line records `case_id`, `request_id`, `error_status`, and
`emitted_by = control_plane` or `worker_defensive_validation`. The artifact is
test evidence only; it does not change the public error response shape.

Registry-load validation fixtures write `errors/registry-validation.jsonl`.
Each line records `case_id`, `model_id`, `validation_code`, `field_path`, and a
human-readable message. These artifacts represent configuration validation
failures and must not be encoded as request admission `route_not_supported`
responses.

Initial registry validation codes are:

- `missing_request_routes`
- `unspecified_enum`
- `empty_supported_modalities`
- `requires_modality_not_supported`
- `native_video_without_video_modality`
- `unknown_model_family_target`
- `duplicate_route_declaration`
- `route_conflict`
- `invalid_text_companion`
- `invalid_residency_policy`

Registry validation codes use lower-snake-case names. `field_path` uses dotted
field names with zero-based repeated-field indexes, such as
`request_routes[0].supported_modalities`.

Slice 1 uses the existing `ErrorStatus` plus `details` map and does not add a
typed route-error protobuf message. HTTP/OpenAI surfaces map
`route_not_supported` to a non-retriable 4xx admission error.

The detail values represent:

- `model_id`
- `task`
- `requested_modalities`
- `required_modality_suite`
- `available_routes`
- `available_modality_suites`
- `worker_family_candidates`
- `reason`

Because `ErrorStatus.details` is a string map, detail values use stable string
encoding:

- enum values use lower-snake canonical names.
- `requested_modalities`, `available_modality_suites`, and
  `worker_family_candidates` are comma-separated canonical names sorted in a
  fixed order.
- `available_routes` is a JSON array string. Each route object includes only
  `task`, `supported_modalities`, `requires_any_modality`, `worker_family`, and
  `model_family_target`.
- empty collections are encoded as empty strings, and required detail keys are
  not omitted.

`ErrorStatus.details.reason` is a canonical reason code, not human-readable
text. The initial reason codes are:

- `missing_request_routes`
- `no_route_for_task`
- `no_route_for_modalities`
- `native_video_required`
- `worker_family_unavailable`
- `multi_residency_denied`
- `route_conflict`
- `worker_family_mismatch`

Human-readable explanation belongs in `ErrorStatus.message`.

`worker_family_mismatch` is reserved for worker defensive validation. It is used
when a worker receives a request whose normalized route does not match that
worker's family. Control-plane admission continues to use
`worker_family_unavailable` when the route matches but no ready worker instance
or capability handshake can serve the required worker family.
Structured route rejection fixtures include `worker_family_mismatch` in the
expected reason set, but only worker defensive validation tests may emit it.
Control-plane admission fixtures must not emit `worker_family_mismatch`.

For video requests, `native_video_required` is used when a route matches the
task and modality set but does not declare `supports_native_video = true`.
`no_route_for_modalities` is used when no route covers the requested video
modality at all.

`worker_family_unavailable` is used only after a route declaration matches but
no ready worker instance or worker capability handshake can serve the route's
worker family. In that case, `available_routes` still reports the matched route
declarations and `worker_family_candidates` reports the required family names.
`worker_family_candidates` is derived from the matched route declarations, not
from the set of currently ready worker instances. It is populated with the
required worker family in both the no-registered-instance and all-not-ready
cases.
The first error contract does not add
`details.worker_instance_state_summary`. Instance state remains available
through receipts, metrics, and logs rather than expanding the structured route
rejection payload.
Because no concrete worker instance is selected on this path, the request does
not write a route selection receipt.

`multi_residency_denied` is used only after a route declaration matches and the
worker family is available, but the same model already has residency in another
worker family or instance and the matched route's `residency_policy` is not
`allow_multi_residency`. The control plane must not automatically unload,
migrate, or duplicate the model to satisfy the request. Slice 1 keeps current
residency details in `ErrorStatus.message` rather than adding more
`ErrorStatus.details` fields.

Route resolution uses this deterministic failure order:

1. no `request_routes`: `missing_request_routes`
2. no route with the normalized task: `no_route_for_task`
3. task matches but modality subset or `requires_any_modality` fails:
   `no_route_for_modalities`
4. video route shape matches but `supports_native_video = false`:
   `native_video_required`
5. duplicate route ambiguity reaches admission despite registry validation:
   `route_conflict`
6. route matches but no ready worker family or capability handshake can serve it:
   `worker_family_unavailable`
7. worker family is available but residency policy denies the request:
   `multi_residency_denied`
8. successful route then proceeds to worker instance selection

Slice 1 validates concrete worker instance selection in addition to worker-family
route resolution. Instance selection is deterministic:

1. filter to ready instances in the matched `worker_family`
2. honor an explicit preferred worker instance id when present and ready
3. if exactly one ready candidate remains, select it
4. prefer an instance that already has the requested model resident
5. prefer the lowest active request count
6. break ties by the lexicographically smallest stable worker instance id

The selection fixture must assert the selected worker instance id, the selected
worker family, and that route resolution itself does not load, unload, migrate,
or duplicate model residency.

Worker instance ids used by Slice 1 fixtures are explicit stable ids declared by
the fixture setup. Selector tie-breaking uses these stable ids. Runtime-random
worker instance ids must not participate in fixture assertions.

Preferred worker instance id is an internal admission or test harness hint in
the first gate, not a public API contract. It may be represented by an internal
execution metadata extension or by the fixture harness, but external clients
must not be able to select worker instances directly.

If the preferred worker instance id is absent, unknown, not ready, or in the
wrong worker family, the selector ignores the hint and continues with residency,
load, and stable-id ordering. A bad preferred-instance hint must not fail an
otherwise serviceable request. `worker_family_unavailable` is returned only when
the matched worker family has no ready candidate at all.

When a preferred worker instance id identifies a ready instance in the matched
worker family, the selector uses that instance even if another ready instance
already has the requested model resident. Preferred instance selection has
higher precedence than resident-model selection.

If the preferred instance is selected and the requested model is not resident on
that instance, the control plane may run `ensure model loaded` on the preferred
instance after selection. This still respects the matched route's residency
policy; if loading on the preferred instance would violate single residency, the
request fails with `multi_residency_denied` rather than unloading, migrating, or
duplicating the model implicitly.

When a same-model Text Companion route and Vision route explicitly declare
`residency_policy = allow_multi_residency`, an existing Vision Worker residency
does not block a text-only request from selecting a Text Worker instance and
loading the model there. The explicit policy allows this duplicate residency.

Slice 1 emits a route selection receipt so fixtures can assert selection without
reverse-engineering stream events. The receipt includes:

- `request_id`
- `model_id`
- `task`
- `request_modalities`
- `selected_route.task`
- `selected_route.supported_modalities`
- `selected_route.requires_any_modality`
- `selected_route.supports_native_video`
- `selected_route.worker_family`
- `selected_route.model_family_target`
- `selected_route.residency_policy`
- `selected_worker_instance_id`
- `selection_reason`
- `preferred_worker_instance_id`
- `preferred_instance_used`
- `model_residency_before`
- `active_requests_snapshot`
- `selection_snapshot_id`
- `selected_at_unix_ms`

`selection_reason` is a canonical code. The first codes are:

- `preferred_instance`
- `resident_model`
- `least_active_requests`
- `stable_tie_break`
- `only_ready_candidate`

`selection_reason` records the highest-priority rule that selected the worker
instance. When a preferred worker instance is used, `selection_reason` is always
`preferred_instance`, even if that instance also has the model resident or has
the lowest active request count.

When the matched worker family has exactly one ready candidate and no preferred
worker instance hint is honored, `selection_reason` is `only_ready_candidate`,
even if that instance also has the requested model resident. No residency or
load comparison is needed in that case. If a preferred worker instance hint
identifies that same sole ready candidate, `selection_reason` is
`preferred_instance` and `preferred_instance_used = true`.

The first receipt contract does not include a separate ignored-preference
reason. When a preferred worker instance hint is not used,
`preferred_instance_used = false` and `selection_reason` records the actual
winning rule.

`preferred_worker_instance_id` is always present in the receipt. If no preferred
worker instance hint was provided, it is encoded as an empty string rather than
`null` or an omitted field.

`selection_snapshot_id` identifies the control-plane worker registry snapshot
used for selection. `selected_at_unix_ms` records when the control plane made
the route and worker instance selection decision. These fields are diagnostic
artifact fields and must not be used as route matching inputs.
`selection_snapshot_id` is a monotonic logical id assigned by the control plane
when it snapshots the worker registry for selection. It is not a timestamp,
random UUID, or worker-provided value.

The receipt does not include `matched_route_index` or any other route-order
identifier. Route declaration order is not part of the contract; fixtures assert
the structured `selected_route` fields instead. `selected_route` includes the
matched route's task, supported modalities, and required-any modalities so
fixtures can prove the selected route matched the request modality set rather
than only the worker family. It also includes `supports_native_video` so
video-bearing fixtures can prove that route selection used a native-video route.
It includes `residency_policy` so residency-related selection and rejection
fixtures can trace their outcome back to the matched route declaration.

In Slice 1, the route selection receipt is a fixture or runtime artifact only.
It is not added to public HTTP responses or streaming `ExecuteEvent` payloads,
so internal worker topology does not become an external API contract.

The route selection receipt artifact is JSONL. Each request writes one JSON
object line after route resolution and worker instance selection complete and
before `ensure model loaded` begins. This keeps the artifact append-only,
diffable, and aligned with existing runner-style event artifacts. It also keeps
the receipt focused on route and selection decisions, not model loading side
effects.

Route selection receipts are written only for requests that successfully resolve
a route and select a concrete worker instance. Admission failures, including
`multi_residency_denied`, do not write route selection receipts; fixtures assert
those paths through the structured route rejection error instead. A single
fixture case asserts either a route selection receipt or a structured route
rejection, never both.

If a route selection receipt is written and a later `ensure model loaded` step
fails, the receipt remains valid evidence that route resolution and worker
instance selection succeeded. The later load failure is asserted as a separate
control-plane or worker loading error, not as a route rejection.

`model_residency_before` is a structured JSON object, not a string. It records
only the pre-selection residency snapshot as `worker_instance_id -> resident
model records`, where each resident model record includes `model_id` and
`model_handle`. The first contract does not require or emit a post-selection
residency snapshot. The snapshot is limited to instances in the matched
`worker_family`; it does not record cross-family topology.

`active_requests_snapshot` is also a structured JSON object. It records
`worker_instance_id -> active_request_count` from the control-plane snapshot used
by the selector at the decision point. The snapshot is limited to instances in
the matched `worker_family`.

Route selection receipt JSON fields use lower-snake-case names. Enum values and
canonical selection codes in the receipt also use lower-snake-case names,
matching the structured route rejection details convention.

Modality arrays in the receipt use a fixed canonical order: `text`, `image`,
`audio`, `video`. This applies to `request_modalities`,
`selected_route.supported_modalities`, and
`selected_route.requires_any_modality`.

Receipt JSON objects that are keyed by `worker_instance_id` are emitted with
lexicographically sorted keys. This applies to `model_residency_before` and
`active_requests_snapshot` so fixture diffs remain stable.

Resident model records inside each `model_residency_before` instance entry are
sorted by `model_id` and then `model_handle`.

### Deterministic Parity Fixtures

Deterministic parity fixtures run without real model weights and freeze
observable behavior for:

- image-only requests
- multi-image requests
- video-only requests with native video requirement metadata
- mixed image and video requests
- OCR requests
- tool parser behavior for vision requests
- text-only vision requests
- text companion route behavior
- media URI and inline media normalization
- video frame policy metadata
- multimodal hash behavior
- attention budget receipts
- position metadata receipts
- fast-path cache probe receipts
- temporary media cleanup receipts
- cancellation before first token and after partial emission
- structured errors

Deterministic fixtures must not count a video-to-text prompt rewrite as native
video execution.

### Real-Model Acceptance Fixtures

Real-model acceptance fixtures use locally available model weights and prove the
real runtime path. They are manifest-driven so multiple concrete model ids can
satisfy one model-family target.

Each target records:

- `family_id`
- accepted concrete `model_id` values
- accepted `model_type` values
- required modalities
- required runtime features
- required route declaration
- required residency policy
- minimum acceptance cases
- artifact and receipt evidence paths
- semantic acceptance scoring requirements

Real-model acceptance has two required gates:

- Runtime correctness gate: the request resolves to the expected worker family,
  consumes the required media modalities through the real runtime path, emits
  the required route and runtime evidence, and returns a non-empty successful
  response or the expected structured error.
- Semantic acceptance gate: the response is scored against the fixture's
  expected answer or rubric using the configured Melix evaluation scoring mode
  or judge-backed scorer, and the target satisfies the fixture threshold.

Deterministic parity fixtures do not require remote judge execution.

## Semantic Acceptance Gate

Semantic acceptance uses the existing Melix evaluation and judge artifact model
instead of a separate scorer. Fixture manifests must declare:

- `scoring_mode`
- expected answer, rubric, or structured target
- model family
- modality suite
- absolute score floor
- Python-baseline comparison floor
- critical samples that must pass individually
- judge server requirements when scoring is judge-backed
- artifact paths for prompt snapshots, judge audits, per-sample scores, summary
  scores, timing, and failures

Judge-backed real-model acceptance is blocked when the required judge target is
unavailable or when the judge run fails. It must not silently degrade to a smoke
test or manual review.

For Python-to-Swift migration, semantic acceptance compares the Swift candidate
against both an absolute floor and the frozen Python baseline. A Swift candidate
passes only when:

- `swift_score >= absolute_floor`
- `swift_score >= python_baseline_score - allowed_delta`
- every critical native-video sentinel sample passes individually

The first gate defaults are:

- `absolute_floor = 0.70`
- `allowed_delta = 0.05`
- `critical_sentinel_score = 1.0`

Fixture manifests may raise these thresholds for a stricter suite, but they
must not lower them below the defaults.

Native video sentinel samples are individual pass/fail samples, not only
contributors to an aggregate score.

Scoring is layered by sample type:

- `normalized_exact_match` is allowed for OCR, simple enumerations, counts, and
  clearly bounded single-token or short-answer samples.
- `judge_backed_semantic` is required for image reasoning, video reasoning,
  mixed image and video reasoning, and open-ended descriptions.
- Critical native-video sentinel samples must be judge-backed or structurally
  validated in a way that proves video content was used. Non-empty output is not
  sufficient sentinel evidence.

Judge-backed samples must persist prompt snapshot and per-sample audit artifacts.
The minimum audit fields are:

- judge model id
- judge prompt hash
- rubric
- messages hash or redacted messages
- model answer
- expected answer or rubric target
- typed score
- failure reason
- latency

Missing prompt snapshot or per-sample audit artifacts fail the semantic
acceptance gate.

Judge-backed scoring may use a score cache. Cache keys must include:

- judge model id
- judge prompt hash
- rubric hash
- sample id
- model answer hash
- expected target hash
- media reference hash

Any key mismatch requires a new judge call. Cache hits must still write
per-sample audit rows with `judge_source = cache`.

Fixture image and video media must be repository-owned or artifact-bundled
immutable files. Acceptance inputs must not depend on live external URLs. Each
media artifact entry must record:

- `media_id`
- `path`
- `sha256`
- `mime_type`
- `duration` for video media
- `frame_count` for video media when known or fixed by the fixture

External URLs may be used only while creating a fixture. Once a fixture is
accepted, the media must be vendored or bundled and referenced through the
immutable artifact entry.

Native video acceptance must emit a `video_preprocess_receipt` for each video
request. The receipt must include:

- `media_id`
- `sha256`
- decoder identity
- sampled frame count
- sampled timestamps in milliseconds
- video token count or equivalent processor metadata
- frame budget
- preprocessing latency in milliseconds

A video semantic score without this receipt does not satisfy native video
acceptance.

Each video-bearing suite must include at least one temporal video sentinel. A
temporal video sentinel must set `requires_temporal_reasoning = true` and use an
expected answer or rubric that depends on order, change over time, or later-frame
content. The sentinel cannot be answerable from the first frame, a thumbnail, or
a single static crop.

The Python baseline is a frozen artifact, not a live rerun during Swift
acceptance. Each baseline must record:

- Python worker git SHA
- concrete model id
- model artifact hash or model config hash
- fixture manifest hash
- judge prompt hash when judge-backed scoring is used
- judge model id when judge-backed scoring is used
- score by model family and modality suite
- per-sample scores
- timing

Swift acceptance reads the frozen baseline artifact for delta comparison.
Baseline refresh is a separate explicit operation. It must not be triggered by
the Swift acceptance command. Each refresh must produce an audit artifact and a
reviewable diff that records:

- refresh reason
- old and new score summaries
- old and new per-sample scores
- old and new fixture manifest hashes
- old and new judge prompt hashes when judge-backed scoring is used
- old and new model artifact hashes or model config hashes
- old and new concrete model ids when they change

Semantic scores must be aggregated by both model family and modality suite. A
family-level aggregate is allowed for reporting, but it cannot satisfy the
migration gate by itself. Each required family and modality-suite pair must pass
the absolute floor and Python-baseline comparison floor.

The first fixture gate uses this fixed modality-suite set:

- `image`
- `multi_image`
- `video`
- `mixed_image_video`
- `ocr`
- `text_conditioned_vision`

Each Gemma 4, Qwen 3.5, and Qwen 3.6 target must declare each suite as
supported or unsupported. Unsupported suites are not skipped. They require a
route-level structured rejection fixture. Supported suites require real-model
semantic acceptance.

Each supported model-family and modality-suite pair must include at least three
real-model samples in the first gate. Video-bearing suites must include at least
one critical temporal video sentinel sample that proves native video execution
and passes individually.

## Required Model Family Targets

### Gemma 4

Targets:

- `gemma4_vlm.multimodal`
- `gemma4_vlm.text_backed`
- `gemma4_vlm.native_video`

Requirements:

- Gemma 4 image requests must execute through the Vision Worker when the model
  declares image support.
- Gemma 4 text-only requests may use Text Companion only when explicitly
  declared.
- Gemma 4 text-backed models must reject image requests when no vision weights
  are present.
- Gemma 4 video requests must pass native video real-model acceptance before a
  Gemma 4 video route can be declared.
- Text-backed video prompt rewrite is not accepted as native video execution.

### Qwen 3.5

Targets:

- `qwen35_vlm.multimodal`
- `qwen35_vlm.native_video`
- `qwen35_vlm.native_mtp`

Requirements:

- Qwen 3.5 VLM routes must be declared by request routes, not inferred from
  broad text capability.
- Qwen 3.5 native video acceptance requires artifact evidence for a
  video-capable VLM runtime. Model naming is only a hint and cannot upgrade a
  text or generic any-to-any artifact into a Vision route.
- Native MTP compatibility must be fixture-covered using config metadata and
  MTP weight presence.
- Native video real-model acceptance is required before a Qwen 3.5 video route
  can be declared.

### Qwen 3.6

Targets:

- `qwen36_vlm.multimodal`
- `qwen36_vlm.native_video`
- `qwen36_vlm.native_mtp`

Requirements:

- Qwen 3.6 may present `model_type=qwen3_5`; fixtures must distinguish the
  Qwen 3.6 target by family metadata and concrete model evidence rather than by
  display name alone.
- Qwen 3.6 native video acceptance requires artifact evidence for a
  video-capable VLM runtime. Model naming is only a hint and cannot upgrade a
  text or generic any-to-any artifact into a Vision route.
- Native MTP compatibility must be fixture-covered using config metadata and
  MTP weight presence.
- Native video real-model acceptance is required before a Qwen 3.6 video route
  can be declared.

## Native Video Artifact Evidence

Native video acceptance for Qwen-family targets requires evidence from the
concrete artifact, not from display names alone:

- repository or local model id evidence;
- config model type evidence;
- processor class or processor config evidence;
- video token or video token index evidence;
- vision tower or equivalent visual encoder evidence;
- real video fixture output evidence;
- route declaration evidence that binds the artifact to the Vision Worker.

An artifact whose name resembles Qwen 3.5 or Qwen 3.6 but whose evidence only
supports text generation remains a text route. A Qwen 3.6 artifact whose display
name does not contain `VL` may still satisfy `qwen36_vlm.native_video` when its
fixture manifest records the required video-capable artifact evidence.

## Route Declaration Requirements

Vision route declarations must include structured fields instead of free-form
extension strings:

- `task`
- `supported_modalities`
- optional `requires_any_modality`
- `worker_family`
- `model_family_target`
- `supports_native_video`
- `is_text_companion`
- `residency_policy`

The first proto surface adds repeated `request_routes` fields to both
`controlplane.v1.ModelSummary` and `worker.v1.ModelSpec` using an equivalent
`RequestRouteDeclaration` shape. `ModelSummary.request_routes` is the
control-plane and operator-facing surface. `ModelSpec.request_routes` is the
worker defensive validation surface. Existing `route_class` fields may remain in
the protobuf for now, but they must not participate in new request routing.

Schema changes must use new field numbers and must not reuse, repurpose, or
remove existing field numbers. The worker and control-plane packages may define
package-local generated message types if import boundaries require it, but the
field names, enum vocabularies, validation rules, and JSON fixture encodings
must remain semantically equivalent.

Route declaration fields use typed protobuf enums, not free-form strings, for
`task`, `supported_modalities`, `requires_any_modality`, `worker_family`, and
`residency_policy`. `model_family_target` remains a string because it identifies
fixture and registry family targets such as `gemma4_vlm.native_video` rather
than a closed protocol enum, but it is not free text. The registry loader must
validate that `model_family_target` matches a declared registry or manifest
target id. Unknown target ids are registry-load errors. `UNSPECIFIED` enum
values are invalid in accepted route declarations and must produce admission or
registry-load validation errors instead of falling back.

The first proto enum surface includes the full initial route vocabulary even
though Slice 1 only verifies Text Worker and Vision Worker routes:

- `InferenceTask`: `generate_text`, `generate_multimodal`, `embed`, `rerank`,
  `transcribe`, `speak`, `image_generate`, `image_edit`
- `RouteModality`: `text`, `image`, `audio`, `video`
- `WorkerFamily`: `text`, `vision`, `audio`, `image`, `retrieval`, `omni`
- `RouteResidencyPolicy`: `default`, `single_residency`,
  `allow_multi_residency`

`RouteResidencyPolicy` is the only route-level multi-residency control. The
route declaration does not include a separate `allow_multi_residency` boolean.
`default` exists only as the protobuf wire/default value. Versioned registry and
fixture route declarations must explicitly use `single_residency` or
`allow_multi_residency`; `default` in a loaded declaration is a registry-load
validation error. Text Companion routes that coexist with Vision or Omni
residency require `residency_policy = allow_multi_residency`.

Route declarations must be unique for a model by `(task, supported_modalities,
requires_any_modality)`. The first proto surface does not include route
priority. The only allowed duplicate-match exception is an explicitly declared
Text Companion route. Any other duplicate or conflicting route declaration is a
registry-load error.

Registry-load validation errors fail model registry or catalog loading before
the model is advertised as routeable. They are configuration errors, not request
admission `route_not_supported` responses. Request admission errors are reserved
for well-formed route declarations that do not support a specific request or
cannot be served by current worker availability and residency state.

Route modality matching uses set semantics:

- `supported_modalities` is the upper bound:
  `request_modalities` must be a subset of `supported_modalities`.
- `requires_any_modality` is a presence requirement:
  when non-empty, `request_modalities` must intersect it.
- when `requires_any_modality` is empty, subset matching is sufficient.

Text-only routes use `supported_modalities = [text]` and an empty
`requires_any_modality`. A Vision route that should not accept text-only
requests uses `supported_modalities = [text, image, video]` and
`requires_any_modality = [image, video]`. Text-only Vision execution requires a
separate explicit route declaration.

Control-plane admission normalizes request endpoints and content into inference
tasks before route matching:

- text-only chat or completions requests: `generate_text`
- chat or completions requests with image or video input:
  `generate_multimodal`, including media-only requests without non-empty text
- embeddings endpoint: `embed`
- rerank endpoint: `rerank`
- transcription endpoint: `transcribe`
- speech endpoint: `speak`
- image generation endpoint: `image_generate`
- image edit endpoint: `image_edit`

The inference task is not the raw endpoint name and is not derived from model
kind.

Control-plane admission extracts request modalities from input content before
route matching:

- non-empty text prompt, message text, or input text adds `text`.
- empty string text, whitespace-only text, and media-only messages do not add
  `text`.
- image URLs, inline image bytes, and image artifact references add `image`.
- video URLs, video files, inline video bytes, and video artifact references add
  `video`.
- audio input bytes, audio files, and audio artifact references add `audio`.
- image generation and image edit outputs are not request modalities.
- image edit source and mask inputs add `image`.

Unknown media types are request parsing admission errors with
`ErrorStatus.code = invalid_request_media_type`. They happen before route
matching, are not `route_not_supported`, and must not be delegated to workers
for guessing.

The first `invalid_request_media_type` contract also uses the existing
`ErrorStatus.details` map rather than adding a typed error proto. Required
details keys are:

- `media_type`
- `media_part_index`
- `reason`

`media_part_index` is zero-based and counts media parts in request order. It is
not a message index.
For unknown media types, `details.reason` is `unsupported_media_type`.
If the request does not provide an explicit MIME type and the URL or filename
extension cannot be recognized, `details.media_type` is an empty string.
Explicit MIME type takes precedence over URL or filename extension inference. If
the request explicitly provides `application/octet-stream` for a `.png` file,
the media type is treated as `application/octet-stream`, not inferred as image,
and admission fails with `invalid_request_media_type`.
If the request explicitly provides `image/png` for a filename ending in `.mp4`,
the media type is treated as image because the explicit MIME type wins.
Explicit MIME types matching `image/*`, `video/*`, and `audio/*` map to the
corresponding request modality. `application/octet-stream` and other
non-media-family MIME types do not match any modality.
MIME type matching is case-insensitive and ignores MIME parameters before
matching; for example, `Image/PNG; charset=binary` maps to `image`.
When no explicit MIME type is provided, the first recognized image filename or
URL extensions are `.png`, `.jpg`, `.jpeg`, `.webp`, and `.gif`.
The first recognized video filename or URL extensions are `.mp4`, `.mov`,
`.webm`, and `.mkv`.
The first recognized audio filename or URL extensions are `.wav`, `.mp3`,
`.m4a`, `.flac`, and `.ogg`.
Filename and URL extension matching is case-insensitive and ignores query
strings and fragments before matching; for example, `clip.MP4?x=1#t=2` maps to
`video`.

Media-only image or video chat requests therefore route as `generate_multimodal`
with `request_modalities = [image]`, `[video]`, or `[image, video]`. A Vision
route with `supported_modalities = [text, image, video]` and
`requires_any_modality = [image, video]` can match these media-only requests
through the normal subset rule.

Image generation and image editing are Image Worker tasks, not Vision Worker
tasks. Image edit source and mask inputs add `image` to request modalities, but
the normalized task remains `image_edit` and must route to `worker_family =
image` when supported.

Text Companion route declarations are valid only when:

- `is_text_companion = true`
- `task = generate_text`
- `supported_modalities = [text]`
- `worker_family = text`
- `supports_native_video = false`
- `residency_policy = allow_multi_residency` when the same model also declares a
  Vision or Omni residency route

A Text Companion route must not match image, video, or audio requests. Invalid
Text Companion declarations are registry-load errors.

Video-bearing request routes must declare native video support explicitly. If no
matching native-video route exists, the control plane rejects the request during
admission. Workers keep defensive validation but must not rewrite video requests
into text-only prompts.

## Migration Gate

The Python-to-Swift Vision Worker migration is blocked until:

- route contract fixtures pass for Text Worker and Vision Worker routing;
- deterministic parity fixtures pass for the existing Python VLM observable
  contract;
- real-model acceptance fixtures pass for Gemma 4, Qwen 3.5, and Qwen 3.6;
- semantic acceptance gates pass for the real-model targets that require judge
  or semantic scoring;
- frozen Python baseline artifacts exist for supported real-model semantic
  acceptance targets before Swift acceptance runs;
- all three target families pass native video real-model acceptance;
- audio-bearing generation is either rejected with a structured route error or
  routed by an explicit Omni declaration;
- Swift Vision Worker emits the same externally observable route, event,
  receipt, metric, and error fields required by the fixture manifests.

## Implementation Slices

### Slice 1: Route Contract and Seed Fixtures

The first slice stabilizes request route declarations before real model
execution. It includes:

- `request_routes` protobuf/schema fields.
- regenerated Swift and Python protobuf artifacts.
- model registry loading through the real generated protobuf path.
- fixture manifest layout and seed Text Worker and Vision Worker route fixtures.
- Text Worker route contract tests.
- Vision Worker route contract tests.
- no legacy route inference fixture.
- structured route rejection fixture.
- deterministic worker instance selection fixture.
- route selection receipt artifact.

Slice 1 implementation work items:

1. Update protobuf schemas with route declaration enums, repeated
   `request_routes`, and typed worker-family handshake fields; regenerate Swift
   and Python protobuf artifacts.
2. Add registry-load validation for route declarations, Text Companion
   constraints, native-video consistency, residency policy, duplicate route
   conflicts, and model family target ids.
3. Add Swift control-plane modality extraction and task normalization unit tests
   using table-driven cases.
4. Add the Swift route resolver and deterministic worker instance selector,
   including side-effect-free input/output contracts, structured route
   rejection, deterministic ordering, and route selection receipt JSONL
   emission.
5. Extend the worker registry to use typed `worker_family`, stable worker
   instance ids, duplicate registration rejection, worker readiness, model
   residency snapshots, and active request snapshots.
6. Add the shared Swift worker server route-validation adapter boundary used by
   Text and Vision runtime adapters.
7. Add Swift Text Worker defensive validation tests and worker-process contract
   tests through the real worker RPC or IPC path.
8. Add the minimal Swift Vision Worker executable with stub runtime, defensive
   validation, and Vision payload receipt JSONL emission.
9. Add control-plane admission integration tests that start real Text and Vision
   worker processes and exercise route selection, worker-family availability,
   preferred worker instance hints, duplicate worker ids, and receipt artifacts.
10. Add seed fixture manifest entries for the required Text Worker and Vision
    Worker route contract scenarios.

Slice 1 PR status:

- Request route declarations, typed `worker_family` handshake fields, and
  generated Swift/Python protobuf artifacts are implemented for the Text Worker
  and Vision Worker route contract path.
- Control-plane inference admission resolves structured request routes, selects
  concrete worker instances deterministically, emits route selection receipt
  metadata, and returns structured admission errors for unsupported routes or
  unavailable worker families.
- The Swift Text Worker and Swift Vision Worker share worker-side route
  validation. The Vision Worker path uses a deterministic Swift runtime for the
  first real-worker fixture slice and records image/video/OCR receipt and metric
  surfaces needed by the parity fixtures.
- Real-model semantic judge acceptance and native-video real-model receipt
  enforcement remain gated by later slices in this plan.

Current implementation touch points:

- `packages/protocol/schema/worker/v1/common.proto`: add the shared route
  declaration enums/message and `ModelSpec.request_routes`.
- `packages/protocol/schema/controlplane/v1/control_plane.proto`: add
  `ModelSummary.request_routes` and typed worker-family surface on
  `WorkerSummary`.
- `packages/protocol/schema/worker/v1/runtime.proto`: add typed worker-family
  handshake surface so runtime registration does not depend on legacy route
  class metadata.
- `services/control-plane-swift/Sources/WorkerClient/WorkerRegistry.swift`:
  replace request serving route selection that currently consults
  `melix.capability.route_kind`, `route_class`, capability metadata, or model
  kind with the structured request route resolver for new inference routing.
  Existing helper APIs may remain temporarily for non-inference callers during
  the slice, but the new inference admission path must not call them to decide
  worker family or worker instance.
- `services/mlx-text-worker-swift/`: add the shared Swift worker server
  route-validation adapter boundary and reuse it from Text Worker and the new
  minimal Vision Worker executable.
- `services/mlx-worker-python/`: update generated protobuf imports and keep
  Python defensive validation aligned when Python worker code touches
  `ModelSpec.request_routes` during migration.

Generated protobuf artifacts under `packages/protocol/swift` and
`packages/protocol/python` must be regenerated from schema changes with
`make proto`. They must not be hand-edited.

Slice 1 verification commands:

- `make proto`
- targeted Swift control-plane route/modality/worker-registry tests
- targeted Swift Text Worker and Vision Worker contract tests
- targeted Python worker defensive-validation tests if Python worker route
  validation code changes
- `make swift-test`
- `make py-test` when generated Python protobuf artifacts or Python defensive
  validation change

Slice 1 success metrics:

- route contract fixture pass rate: 100%
- structured route rejection fixture pass rate: 100%
- worker instance selection fixture pass rate: 100%
- worker defensive validation contract pass rate: 100% for Swift Text Worker and
  Swift Vision Worker
- no legacy route inference from `route_class` or
  `melix.capability.route_kind`
- route selection and Vision payload receipt JSONL artifacts are emitted for
  the expected success paths and omitted for expected admission failures

Slice 1 does not satisfy the full migration gate by itself.

### Slice 2: Real-Model Vision Acceptance

The second slice must complete real-model execution, semantic judging, and native
video evidence for the Vision Worker. It includes:

- real-model acceptance fixtures for Gemma 4, Qwen 3.5, and Qwen 3.6.
- frozen Python baseline artifacts for supported semantic targets.
- semantic acceptance with judge-backed scoring where required.
- judge prompt snapshots and per-sample audit artifacts.
- judge score cache behavior with audited cache hits.
- immutable image and video media artifacts.
- native video preprocessing receipts.
- temporal video sentinel samples.
- family and modality-suite score aggregation.

Slice 2 is required before claiming Vision Worker migration readiness.

Slice 2 prerequisites are hard gates. Missing model weights, judge targets,
fixture media artifacts, or frozen Python baselines must produce a blocked
acceptance artifact that lists the missing prerequisites. These cases must not
be recorded as pass, skip, or xfail.

Blocked acceptance artifacts must include:

- `status = blocked`
- `gate`
- `family_id`
- `modality_suite`
- `model_id`
- `missing_prerequisites`
- `expected_paths_or_ids`
- `detected_paths_or_ids`
- `remediation_hint`
- `created_at`
- `repo_git_sha`
- `fixture_manifest_hash`

## Known Blockers

- Swift MLXVLM currently registers Qwen video-capable families such as Qwen3VL,
  but Gemma 4 VLM native video support is not yet represented by the observed
  Swift VLM registry.
- Existing Python behavior contains video fallback paths, including
  backend-video-argument fallback and Gemma 4 text-backed video prompt rewrite.
  These fallbacks do not satisfy the new native video requirement.
- Existing control-plane Qwen 3.5 and Qwen 3.6 benchmark import behavior treats
  some multimodal-looking metadata as text generation. The new route declaration
  contract must replace that inference for serving routes.

## Verification Plan

Initial verification commands will be finalized with the implementation slices.
The expected gates are:

- Swift route contract tests for model summary request routes and admission
  errors.
- Python deterministic fixture tests for current VLM behavior.
- Swift Vision Worker deterministic fixture tests consuming the same fixture
  manifests.
- Real-model smoke commands for Gemma 4, Qwen 3.5, and Qwen 3.6. Missing local
  prerequisites produce blocked artifacts, not skip or pass results.
- Real-model semantic acceptance runs with persisted score summaries and judge
  artifacts when configured.
- Coverage and metrics reports for the changed route-contract and fixture
  scopes.

## Metrics

- Route resolution latency for successful and rejected vision requests.
- Native video preprocessing latency.
- Native video frame count and requested frame budget.
- Native video first-token latency.
- Peak memory for each real-model target.
- Model residency count by worker family and instance.
- Multi-residency denial count.
- Semantic score by family, modality, and fixture suite.
- Judge call count, failure count, and latency when judge-backed scoring is
  configured.
