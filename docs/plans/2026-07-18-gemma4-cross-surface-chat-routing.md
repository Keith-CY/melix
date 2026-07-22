# Gemma 4 Cross-Surface Chat Routing Repair

## Goal

Make the managed `mlx-community/gemma-4-31b-it-4bit` model usable for real
text conversations through all operator-facing Melix entry points:

- `melix chat run`
- the OpenAI-compatible HTTP endpoint
- the macOS Melix Chat workspace

All three entry points must resolve the same execution model and preserve the
requested public model identifier in responses and transcripts.

## Problem Statement

Registry discovery correctly classifies the managed model as an MLX Gemma 4
VLM and model operations can load it through `python_vlm`. The OpenAI handler
also knows how to materialize a Swift text companion for text-only Gemma 4
requests. That companion resolution is currently private to the HTTP handler,
while direct control-plane chat requests from the CLI and macOS app bypass it.
Those requests therefore attempt to prepare the source VLM against the text
route and fail before generation.

Server-session lifecycle state must also agree with the actual HTTP listener;
the acceptance run must not treat a persisted `Running` label as endpoint
evidence.

Real packaged-App acceptance exposed two additional production-only gaps. The
Swift MLX worker executable had no colocated metallib, so its socket became
ready but the first real model load terminated with `Failed to load the default
metallib`. The desktop Chat gate also checked only the live control-plane model
array, even though Hugging Face cache discoveries intentionally live in the
merged registry catalog; this mislabeled an installed registry-backed Gemma 4
model as missing and replaced the composer with a repair panel.

The packaged desktop also runs provider mutations through the CLI workflow
runner. `Create And Start` launched creation asynchronously and then returned
whenever that runner was present, so the production path always left a newly
created provider in `Draft`. Creation and start must be one ordered workflow
using the exact created session ID returned by the CLI.

Final packaged acceptance found three more cross-process coherence failures.
The Chat attachment gate still blocked a running registry-backed provider while
its registry snapshot was hydrating. A persisted listener port could override
the packaged port even though readiness checks and the active-runtime descriptor
used the packaged value. The resident HTTP sidecar did not observe model-roster
updates written by the App's CLI subprocess. Finally, the App, CLI, and HTTP
sidecar each own a control-plane catalog but share one long-lived Swift worker;
without worker-level load deduplication, the same 31B model could be loaded once
per surface and exhaust memory.

Reloading the gateway or serving-defaults document before a write is not
sufficient when two of those processes write concurrently. Both writers can
load the same document, apply independent session updates, and atomically
replace the file in sequence, silently losing the first update. Atomic
replacement protects readers from a partial document; each complete
read-modify-write transaction also needs cross-process serialization.

The final coherence pass also showed that a forced unload in one control plane
can leave stale handles cached by the others, and that named development
instances need the same explicit listener authority as the packaged runtime.
Cached-handle validation must fail closed when worker inventory introspection
cannot prove residency. Both Swift and Python worker routes expose the existing
`ListLoadedModels` runtime RPC through their control-plane clients so a missing
handle or an unreachable inventory call invalidates the cached handle before a
safe load attempt.

Real Gemma 4 generation exposed one final model-compatibility gap. Its
tokenizer declares `<turn|>` as `eot_token`, but the generic Swift MLX model
configuration does not include that token in `extraEOSTokens` for an arbitrary
local repository ID. The worker therefore emitted the end-of-turn marker and
continued generating until the output limit instead of completing the turn.

Operator review of the packaged Chat transcript exposed a second acceptance
gap: non-empty output and EOS handling do not prove a usable conversation.
Gemma 4 was registered with the Qwen tool parser, Desktop requests left
Thinking disabled, Swift prompt rendering did not forward `enable_thinking`,
and the transcript could place reasoning after the final answer. Desktop Chat
also provided no trusted public runtime identity, so identity questions were
answered from pretraining guesses instead of the selected Melix model.

The operator accepted the Melix inline Thinking presentation on July 19:
an unfilled inline disclosure with a brain icon, muted trigger text, chevron,
and a two-point dotted primary-color rule. Streaming reasoning remains expanded
inside a 128-point scroll viewport, uses an adaptive grapheme typewriter reveal,
and collapses after completion. Reduced Motion bypasses the reveal. Only the
model's public reasoning channel is visible; hidden prompts and private
continuity state remain private.

Live Responses acceptance then exposed a wire-format mismatch behind that UI.
Gemma 4 places each channel body between `<|channel>NAME\n` and `<channel|>`,
while the Swift text filter treated `<channel|>` as the end of a channel header
and discarded everything before it. Reasoning was therefore buffered until the
channel closed and both reasoning and final bodies could be dropped entirely.
The compatible filter must select Gemma framing from execution parser metadata,
stream channel bodies before their closing marker, and retain the existing
marker-terminated-header behavior for models that use the historical format.
The Python fallback assembler has the same incremental-output obligation for
`<think>` and Gemma thought channels. Responses must also honor the standard
`max_output_tokens` field so a bounded acceptance request cannot silently fall
back to the much larger serving default.

The first natural Thinking acceptance also exposed two generation-policy
differences from the model repository. Swift Jinja does not apply the
whitespace-control markers surrounding the Gemma template's Thinking comment,
so it rendered a double-newline turn boundary where Transformers renders one
newline. In addition, the shared request schema carried `top_k`, but neither
catalog defaults nor the Swift MLX sampler consumed the model's declared
`top_k=64`. The packaged runtime must normalize only that proven Gemma boundary
and must carry explicit-or-model sampling defaults through every layer into a
real top-k sampler.

The operator's first real follow-up question then exposed an inference-parity
defect rather than a presentation defect. Gemma 4 declares
`attention_k_eq_v=true`; the official implementation derives value states from
the raw key projection, while the vendored Swift implementation derived them
from key states after normalization and RoPE. The error accumulated through
the full-attention layers and produced repetitive thought tokens before a final
channel could open. The same investigation found that generic imported
generation settings were sufficient to construct an OCR policy, incorrectly
clamping an ordinary Gemma conversation to the OCR 256-token fallback.

The operator accepted the Clean Single Card input Composer walkthrough on July
19. The existing Composer duplicates Provider, model capability, transient
status, usage, and destructive clear controls below the editor, while its
keyboard contract uses Command-Return to submit and plain Return to edit a new
line. The accepted design makes the editor primary, keeps the established
icon-only Thinking control, shows only a concise keyboard hint and Send action,
and leaves routing identity in the Chat header. Plain Return submits and
Command-Return inserts a new line; active input-method composition retains
Return for candidate confirmation. A blocked route must preserve the draft and
add a compact repair strip rather than replacing the editor.

On July 22, the operator accepted the Hybrid A refinement after a side-by-side
hierarchy review. Hybrid A keeps the Melix interaction
semantics above while making the editor the calm primary plane: a 16-point
continuous shell, low-contrast border, no persistent shadow or divider, and a
secondary action plane. Thinking uses accent foreground only. The shortcut hint
appears only for an empty focused editor, while generation uses a separate
`Generating · draft saved` status and leaves the next draft editable. The Send
button stays visually stable and unavailable while generating; no Stop action
is presented until real runtime cancellation exists. A five-line-capped editor
offers Expand/Collapse, and a warning-tinted Provider repair strip preserves the
draft and returns focus to the editor when recovery completes. An equivalent
global lifecycle or missing-model banner yields to this local repair strip on
Chat, while unrelated critical global signals remain visible.

The same July 22 component review accepted Variant A for the remaining Chat
chrome. Human-readable Identity keeps Provider selection separate, removes the
repository namespace from the persistent model label, and preserves a compact
quantization badge while exposing the full canonical ID through help,
accessibility, selectable detail, and copy. Inline Glyph Cluster replaces the
large capability tiles with status-bearing controls no taller than 30 points.
Precision Ledger replaces the repeated Chat Inspector section headings and
full-width action labels with dynamic icon-first rows and labeled icon actions;
explicit repair actions retain text.

The final merge audit found that direct Desktop and CLI chat carried the public
model but dropped the selected Server Session ID before control-plane
execution. The CLI receipt merely echoed its option while the service admitted
and shaped every direct request against the default session. Direct chat must
therefore preserve one session identity across client request construction,
lifecycle admission and activity, and serving-default lookup. Long-lived
processes must refresh serving-default records before reads so CLI subprocess
updates are visible to Desktop execution.

## End-State Design

- Move text execution model selection and Gemma 4 text companion
  materialization into one shared control-plane component.
- Use the shared component from both the OpenAI HTTP handler and direct
  control-plane chat execution.
- Keep route declarations authoritative: a text-only request may select the
  explicit text companion route, while media-bearing VLM requests continue to
  use the multimodal route.
- Validate cached dispatch handles against the selected worker's loaded-model
  inventory on both Swift and Python routes. A failed inventory RPC is not proof
  of residency: invalidate the cached handle and take the normal load path.
- Preserve the source model ID as the user-visible model identity even when a
  companion model performs execution.
- Carry the selected Server Session ID on direct Desktop and CLI chat requests,
  then use that exact ID for lifecycle admission, request-activity wakeup, and
  serving-default resolution. Normalize only an omitted or blank ID to the
  legacy default session.
- Refresh persisted serving-default records before long-lived reads and before
  read-modify-write updates so a Desktop process observes settings applied by a
  CLI subprocess and sequential writers preserve other sessions.
- Keep endpoint startup tied to real listener readiness and verify it with an
  HTTP request rather than session state alone.
- Bundle and supervise the HTTP control-plane executable with the packaged App,
  then publish an atomically replaced `0600` JSON descriptor after workers and
  `/health` are ready. The `melix.active_runtime.v1` schema carries app,
  control-plane, and worker PIDs, both worker socket paths, the service base
  URL, and an update timestamp.
- Keep a launcher watchdog alive across the final `exec` so crash and force-quit
  exits also remove the descriptor and stop the bundled sidecars.
- Let external CLI processes resolve each worker socket independently. A fully
  explicit environment pair remains an atomic debug override; with only one
  explicit socket, use the live active-runtime descriptor for the companion
  socket. Accept each descriptor-sourced socket only while the App PID is live
  and that companion path exists; otherwise retain its historical default.
- Package a Swift-core-compatible `mlx.metallib` as a single versioned asset,
  expose it through MLX's colocated relative path, and fail packaging when its
  version cannot be proven compatible. Do not reuse a newer Python MLX
  metallib merely because it is already present in the App.
- Make desktop Chat attachment gating use the same merged live-plus-registry
  catalog used by provider creation and model selection, so an installed
  registry-backed model is sendable without first appearing in a live snapshot.
- While that catalog is hydrating, treat an interactive running provider as
  executable evidence for its configured model. Runtime load failures remain
  authoritative and are surfaced by the normal Chat request path. The same
  live Provider evidence overrides a stale catalog `model_path_missing` flag
  both at composer attachment gating and immediately before submission.
- Make packaged provider creation an ordered `create -> restore -> start`
  workflow. Decode the exact session ID from the create receipt, preserve the
  created draft if start fails, and surface the typed CLI failure instead of
  silently returning.
- Make the package's explicit HTTP host and port authoritative for the effective
  listener so the bound port, health probe, and runtime descriptor cannot drift.
  Keep the atomic gateway JSON as the canonical requested-listener, model
  roster, and next-bootstrap server-session owner store. Once a gateway has
  bootstrapped, its immutable runtime binding remains the routing owner until
  that listener restarts; a later config apply may update that bound session's
  roster but cannot silently move the running listener to another session.
  Legacy documents without an owner retain the default bootstrap fallback.
  Reload the document before reads and writes so the resident sidecar observes
  CLI subprocess updates for its bound session without a restart. A failed
  request-path read or decode preserves the last known good document and
  increments inspectable refresh diagnostics; a normally absent initial file
  remains a valid empty starting state. Serialize each write transaction with
  an exclusive advisory lock on a stable sibling lock file, retain atomic
  replacement for the JSON document, and fail a write rather than replace an
  unreadable existing document from an empty fallback. Apply the same
  sibling-lock transaction to the shared serving-defaults document so
  independent session updates cannot overwrite one another. Lock contention
  must use `O_NONBLOCK` acquisition plus cancellable async backoff so a competing
  process cannot park Swift's cooperative executor; any acquired descriptor is
  released exactly once on success, error, explicit release, or deinitialization,
  while an unsuccessful or cancelled acquisition owns none.
- Make the long-lived Swift worker the process-residency authority for text
  models. Identical load identities must share one handle through a single-flight
  load, failed loads must remain retryable, automatic unload must protect shared
  residency, and an explicit forced operator unload must still release it after
  active requests finish. Before reusing a cached handle, a control plane must
  validate it against the worker and lazily reload when another process removed it.
- Treat explicit development HTTP ports as authoritative runtime bindings so
  named worktree instances cannot drift to a persisted listener port.
- At local Swift-model load time, merge the tokenizer's declared `eot_token`
  into the runtime's additional EOS set. Stop before emitting that token while
  retaining the model factory's existing EOS policy for models that do not
  declare an explicit end-of-turn token.
- Give Gemma 4 family entries their native Gemma parser metadata instead of the
  generic Qwen VLM fallback.
- Carry resolved reasoning policy and chat-template kwargs through both Swift
  generation and prefill into the model template context, including
  `enable_thinking`.
- Keep one ordered assistant turn in Desktop Chat: public reasoning and tools
  precede the final answer, and each active block has its own streaming state.
- Seed Desktop conversations with a trusted, non-visible Melix runtime identity
  message containing the public selected model ID. Never expose the internal
  `#text` companion identity.
- Present public reasoning with the operator-approved Melix inline
  disclosure. While streaming, cap the visible body at 128 points, reveal
  grapheme clusters with an adaptive backlog-aware cadence, auto-follow only
  while the operator remains near the bottom, and render immediately when
  Reduce Motion is enabled.
- Select output-channel framing from the resolved execution parser. Gemma
  framing reads the channel name through the first newline and incrementally
  emits the following body until `<channel|>`; marker fragments may span token
  chunks and must never leak. Other parsers retain the historical Harmony
  marker-terminated-header behavior.
- Resolve Swift single-shot Generate framing from request metadata first and
  the loaded model specification second, including its parser field and parser
  extensions. This matches Decode, whose stored Prefill execution and loaded
  model specification already provide the same fallback authority.
- Stream active reasoning bodies incrementally in the Python fallback assembler
  while retaining only a possible closing-marker suffix. When an unclosed
  reasoning body reaches a separator that can begin terminal assistant recovery,
  hold that ambiguous tail outside the public reasoning stream. A later close
  marker confirms and immediately flushes it as reasoning; EOS recovers it as
  assistant content, and a 4,096-character bound commits an oversized candidate
  to assistant content rather than risking a final-answer leak into Thinking.
  Generate must publish any EOS reasoning-recovery deltas before its usage and
  Completed events so streaming clients receive the recovered answer exactly
  once; unrelated aggregate-only partial-marker tails remain unstreamed.
  Suppressed reasoning must remain private when Thinking is disabled.
- Decode and validate Responses `max_output_tokens` at the HTTP boundary, map it
  to the worker sampling cap, reject conflicting compatibility aliases, and
  preserve the legacy fields for existing clients.
- Normalize the Thinking-only Gemma turn boundary after template tokenization so
  Swift rendering matches the canonical Transformers token sequence without
  changing non-Gemma prompts, media tensors, or Thinking-disabled turns.
- Import `generation_config.top_k` into model sampling policy, let an explicit
  request value win, and apply the resolved value inside the Swift MLX sampler
  before optional nucleus sampling.
- For Gemma 4 K=V attention, derive both key and value branches independently
  from the raw key projection: normalize and rotate only the key branch, and
  apply value normalization directly to the raw projection.
- Construct an OCR execution policy only when at least one non-empty
  OCR-specific setting declares it. Once declared, imported generic generation
  settings may remain fallback values for that OCR policy.
- Use the accepted Hybrid A Composer: a one-to-five-line editor above a quiet
  action plane with an icon-first Thinking control and stable Send button. Use a
  16-point continuous corner, low-contrast border, and no persistent shadow or
  divider. Keep Provider and public model identity in the Chat header; move
  usage to response metadata and clear-conversation to session actions.
- Let unmodified Return and keypad Enter submit only from the focused Composer.
  Command-Return inserts a newline, composition Return confirms IME candidates,
  the short post-composition guard prevents an accidental send, and empty,
  blocked, or streaming submission attempts are silent no-ops.
- Preserve the editor and draft when the route is blocked. Present the existing
  recovery actions in a compact warning strip inside the Composer instead of
  replacing the input surface. Restore editor focus when the repair clears.
- Show the keyboard hint only for an empty focused editor. During generation,
  keep the editor editable, disable Thinking and Send, and show an independent
  `Generating · draft saved` status. Do not put activity dots in Send or present
  a Stop affordance without runtime cancellation.
- Cap the resting editor at five visible lines and offer Expand/Collapse only
  once content reaches that cap.
- Use the accepted Human-readable Identity in the Chat header: keep Provider
  and model as separate controls, hide the canonical namespace from the resting
  label, preserve a non-shrinking quantization badge, and make the complete ID
  selectable and copyable in one activation as well as available to help and
  accessibility APIs.
- Replace Chat capability tiles with an Inline Glyph Cluster of 28-point icon
  controls. Keep ready and unavailable distinguishable without color alone and
  expose full names, state, and evidence through help, accessibility, and a
  compact detail popover.
- Replace the generic Chat Inspector stack with the 232-point Precision Ledger.
  Keep Provider/model identity, capabilities, health, endpoint, usage, trust,
  idle state, repair, and three destinations visible without scrolling at the
  760-point acceptance height. Stable categories use icons rather than repeated
  headings; destination buttons remain separately focusable and fully labeled.

## Delivery Slices

1. Add a direct-chat regression test proving that a supported MLX Gemma 4 VLM
   resolves to its text companion and never loads or generates through the
   Python VLM client for a text-only request.
2. Extract the existing HTTP-only companion policy, context-window inference,
   and companion construction into a shared resolver.
3. Adopt the resolver in the OpenAI and direct control-plane chat paths while
   retaining public response model identity.
4. Add focused API and direct-chat parity tests, then run scoped coverage and
   performance probes.
5. Package the control-plane sidecar, add lifecycle/readiness coverage, and add
   active-runtime discovery for a terminal-launched CLI.
6. Package and validate the matching Swift MLX metallib and all worker SwiftPM
   resource bundles.
7. Align the desktop Chat model-attachment gate with the merged registry
   catalog.
8. Serialize packaged `Create And Start` across CLI creation and lifecycle
   start using the returned session ID.
9. Keep Chat usable while a running provider's registry model is hydrating.
10. Align packaged and named-development listener authority, then reload the
    shared gateway roster across resident and CLI processes.
11. Deduplicate identical model loads inside the shared Swift worker and define
    safe shared-unload and stale-handle recovery behavior.
12. Import tokenizer-declared end-of-turn tokens into Swift text generation and
    prove the terminal token is not emitted or followed by extra output.
13. Build the packaged app and run real-model acceptance through CLI, HTTP, and
    the desktop Chat workspace.
14. Correct Gemma 4 registry parser metadata and carry Thinking template context
    through Swift generate and prefill paths.
15. Reorder Desktop transcript blocks, add trusted public identity context, and
    make reasoning/tool/answer streaming states independent.
16. Replace the existing reasoning bubble with the accepted Melix inline
    disclosure and adaptive grapheme presentation.
17. Repeat cross-surface acceptance in clean sessions with natural semantic and
    reasoning prompts; keep synthetic EOS probes out of operator conversations.
18. Add a Gemma-aware streaming channel state machine to Swift generate and
    decode, prove reasoning is emitted before channel closure, and repeat the
    real Responses and desktop Thinking acceptance.
19. Align the Python fallback reasoning stream and Responses
    `max_output_tokens` compatibility with the same bounded acceptance contract.
20. Match canonical Gemma Thinking prompt whitespace and carry the model's
    `top_k` default from discovery through request shaping into Swift sampling.
21. Preserve the Swift MLX generator's terminal cause so an exhausted output
    budget reports `length`, while EOS/end-of-turn reports `stop` and operator
    cancellation reports `cancelled` across API, CLI, and Desktop Chat.
22. Raise the built-in local chat serving budget to 1,024 tokens so a
    Thinking-enabled Gemma response has room to cross from its thought channel
    into the final answer; explicit request limits remain authoritative.
23. Preserve terminal causes in Melix's phase-aware Swift MLX decode loops as
    well as the upstream generator, including baseline, continuous-batch,
    speculative, and DFlash paths; verify the installed App with a bounded real
    Responses request.
24. Resolve Desktop Chat text readiness from the model bound to the selected
    provider, using the shared text-generation capability predicate so a
    text-capable VLM is not blocked by an unrelated unloaded catalog row.
25. Treat a thinking-enabled Gemma stream as an implicit initial reasoning
    channel when the model omits its opening channel header, while still
    consuming canonical explicit headers and routing the post-close body to the
    public answer.
26. Restore official Gemma 4 K=V attention semantics and repeat a deterministic
    real 31B multi-turn request against the packaged Swift runtime.
27. Prevent generic text/VLM generation settings from activating OCR defaults,
    while preserving declared OCR profiles and their imported-config fallback.
28. Implement the accepted Hybrid A Composer, reverse its Return and
    Command-Return contract, remove conflicting App-level Command-Return
    interception, preserve editable drafts through streaming and repair, and
    verify the packaged App through real keyboard input.
29. Make direct Chat session routing execution-authoritative across Desktop,
    CLI, lifecycle activity, and serving defaults, including cross-process
    serving-default refresh.
30. Adopt the accepted Human-readable Identity, Inline Glyph Cluster, and
    Precision Ledger in production SwiftUI without changing Hybrid A Composer
    hierarchy or interaction semantics.
31. Pin every running gateway request to the session identity captured in its
    bootstrap runtime binding, and make request-path config refreshes preserve
    last-known-good state with typed failure diagnostics instead of silently
    routing through empty defaults.
32. Disable the Desktop provider picker while a response is streaming and
    invalidate the active request identity before any programmatic provider
    rebinding, so late events from the old provider cannot enter the selected
    conversation.
33. On an unclosed public-reasoning channel, retain text that was already
    emitted as reasoning and recover only the unstreamed remainder. Never
    reclassify already-visible reasoning as final assistant content at EOS.

## Performance Probes and Success Metrics

- Preserve `control_plane.text_first_load_ms`,
  `control_plane.text_first_load_estimated_resident_bytes`, and
  `control_plane.text_first_load_resident_bytes`.
- Preserve request route and first-token timing receipts already emitted by the
  request coordinator and gateway.
- Companion context inference must remain cached by model path; repeated
  requests must not reread `config.json`.
- The packaged metallib version must match a compatibility version accepted by
  the vendored Swift MLX core; the relative link and code signature must remain
  valid after archive extraction.
- Initial and resumed responses must preserve the served Gemma 4 model ID, and
  the internal `#text` companion must remain absent from user-visible catalogs.
- The packaged provider command sequence must be `create`, `update`, `select`,
  `start`; all four commands must target the one newly returned session ID.
- A running registry-backed provider must expose the Chat composer before a
  manual registry rescan; registry hydration must not create a false missing
  model repair state.
- The effective HTTP listener, `/health` probe, and active-runtime descriptor
  must all use the packaged host and port even when persisted requested binding
  values differ.
- A roster update written by the CLI for the session already captured in the
  runtime binding must affect the next HTTP request without restarting the App.
  Configuring a different session updates the next-bootstrap owner only; the
  running listener's roster, serving-default selection, and summary ownership
  stay pinned to its bound session. `gateway.model_route_resolution_ms` remains
  the probe for the small atomic-config reload on that path.
- A request-path gateway-config read or decode failure must keep serving the
  last known good roster. Refresh diagnostics record total and consecutive
  failures, a typed failure kind and timestamp, and whether last-known-good
  state is active; a missing file before the first successful persisted load is
  healthy and does not increment failure counts.
- Switching a Desktop chat to another provider must cancel the active request
  identity before changing its binding. Delayed reasoning, answer, and terminal
  events from the previous provider must be ignored, and the visible picker is
  disabled for the duration of a stream.
- A malformed unclosed reasoning channel may remain reasoning-only, but no text
  previously emitted on the reasoning stream may be duplicated or reclassified
  into assistant content during final recovery.
- A malformed unclosed reasoning channel must not emit a possible final-answer
  tail as a live reasoning delta. Confirmed reasoning before the candidate tail
  still streams incrementally, a normal close marker flushes the held tail with
  no semantic change, and the bounded overflow path prefers assistant content.
  At EOS, a recovered assistant tail must appear as one or more token deltas
  before usage and Completed, matching the Completed aggregate without
  duplication.
- Concurrent gateway-config and serving-defaults writers targeting different
  server sessions must preserve every listener and defaults record. The final
  gateway active owner may follow lock acquisition order, but it must identify
  exactly one of the committed records. Readers must continue to observe either
  the complete previous document or the complete replacement document without
  taking the writer lock.
- A contended sibling-lock waiter must observe task cancellation during the
  async backoff, release no descriptor it does not own, and leave the lock
  immediately reusable. The focused latency probe starts cancellation after
  25 milliseconds and must complete the waiter/reacquire sequence without
  blocking unrelated cooperative work.
- Repeated and concurrent identical loads across control-plane clients must
  produce one worker handle and one backend load. Failed first loads must be
  retryable; shared automatic unload must be rejected while explicit forced
  unload remains available after active requests finish. Cached-handle validation
  latency is recorded by `control_plane.model_handle_validation_ms`, and a stale
  handle must trigger one lazy reload instead of a persistent `not_found` loop.
- Focused changed-scope line coverage must be at least 95 percent.
- Gemma 4 requests must complete at its declared `<turn|>` token without
  exposing the marker and without running to the configured maximum token
  count.
- Real acceptance succeeds only when each surface returns at least one
  semantically relevant assistant answer from the selected Gemma 4 model.
- Gemma 4 registry snapshots must select the Gemma parser and must not record a
  Qwen parser request for a no-tools identity or reasoning conversation.
- A Thinking-enabled request must emit at least one public reasoning delta before
  the first final-answer token. The settled transcript order is
  `user -> reasoning -> tool (when present) -> assistant`.
- A Gemma reasoning body must produce its first worker reasoning delta before
  `<channel|>` arrives. Split open and close markers must not leak or duplicate
  text, and an output-limit finish must preserve already-emitted reasoning.
- A Swift Generate request that omits parser metadata must still use the loaded
  Gemma model specification, route implicit pre-close text to reasoning, consume
  `<channel|>`, and route the following text to the assistant answer.
- A Responses request with `max_output_tokens` must apply that exact worker cap
  and record it as the output-cap source; non-positive, malformed, or conflicting
  values must fail before worker dispatch.
- A Swift MLX stream that exhausts `max_output_tokens` before an EOS/end-of-turn
  token must report `length`; it must not report a successful `stop` completion.
- Fresh local server sessions use a 1,024-token built-in serving budget. A
  caller-supplied smaller `max_output_tokens` remains unchanged and can finish
  with `length`.
- Every phase-aware Swift MLX decode summary reports `length` when its effective
  output cap is exhausted, `stop` for EOS/end-of-turn, and `cancelled` for an
  aborted request. A real installed-App request capped at 64 tokens must close
  as `length` while preserving streamed public reasoning.
- Desktop Chat's text capability receipt names the selected provider's bound
  model and becomes ready when that text-generation-capable provider can serve
  interactively (including on-demand loading); unrelated catalog ordering and
  currently unloaded models must not block the composer.
- Thinking-enabled Gemma output never leaks channel markers or public reasoning
  into the assistant answer when the model omits the initial reasoning header;
  both implicit and canonical explicit channel framing route to the same
  reasoning and final-answer event contract.
- A Thinking-enabled Gemma prompt must contain the canonical
  `<turn|>\n<|turn>` boundary rather than a double newline, and the normalization
  must be a no-op for prompts without the Gemma Thinking token.
- An omitted request `top_k` must resolve to the model's declared value; an
  explicit request value must override it. Swift sampling must never select a
  token outside the resolved top-k candidate set.
- Desktop presentation backlog must stay below 200 milliseconds during the
  focused probe. The stream viewport remains at or below 128 points, manual
  upward scrolling suspends auto-follow, and Reduce Motion presents buffered
  text without the typewriter cadence. Token arrival and the presentation timer
  must not produce two flushes inside the same 24-millisecond cadence window.
- `desktop.chat_composer_input_update_ms` must remain at or below 16 milliseconds
  p95 for a five-line draft, including visual-wrap remeasurement.
- `desktop.chat_composer_state_transition_ms` must remain at or below 100
  milliseconds p95 across ready, generating, and Provider-repair presentation
  transitions without changing draft text or selection.
- Model identity questions in Desktop Chat must report the selected public ID
  `mlx-community/gemma-4-31b-it-4bit` and must not expose an internal companion
  ID or guess a different product/model family.
- A deterministic real Gemma 4 follow-up request must match the official
  implementation's coherent first reasoning phrase, enter the final channel,
  and terminate with `stop` rather than repeating until the output cap.
- Generic generation settings alone must not create an OCR execution policy or
  impose the 256-token OCR fallback. Declared OCR profiles retain their existing
  defaults and generic-config fallback behavior.
- An 80-plus-character model ID does not move the Chat title or quantization
  badge. The resting header hides the namespace, and the canonical ID is
  available to help and accessibility APIs and can be selected or copied after
  one activation.
- Chat capabilities render as an icon-first cluster no taller than 30 points;
  no large capability tile or permanent Text/Vision label remains. Ready and
  unavailable states retain distinct shapes and complete accessible values.
- At 760 points high, the 232-point Chat Precision Ledger presents readable
  Provider/model identity, capability glyphs, health, endpoint, usage, trust,
  idle state, repair, and three separately focusable destination actions without
  scrolling or repeated Context, Health, Metrics, Actions, and Evidence headings.
- The resting Composer contains no duplicated Provider, capability, usage,
  status, or clear controls. It remains below 120 points for a one-line draft,
  grows through five lines, and preserves transcript space in a 980-by-760
  window.
- The Composer shell has a 16-point continuous corner, no persistent shadow or
  internal divider, and no filled Thinking On state. Its keyboard hint is visible
  only for an empty focused editor. Streaming status is independent of Send,
  drafts remain editable, and no fake Stop affordance appears.
- Content at the five-line cap offers Expand/Collapse; shorter drafts do not.
  A blocking Provider repair uses warning styling, preserves the editor and
  draft, and restores focus after recovery. An equivalent global banner is not
  duplicated above Chat or allowed to push the Composer out of the 980-by-760
  acceptance viewport.
- Plain Return sends exactly once; Command-Return inserts exactly one newline
  without sending. Input-method marked text and the short post-composition
  guard, empty drafts, blocked routes, and streaming state never submit or play
  a failure sound.
- For a short draft, VoiceOver traverses Message, Thinking, then Send. At the
  five-line cap, Expand/Collapse appears between Message and Thinking. Thinking
  exposes a stable label and On/Off value, the visible shortcut hint is not the
  sole accessible description, streaming status is announced without becoming
  a keyboard stop, and a repair strip leaves each action separately focusable.

## Verification

- Focused Swift regression tests for the shared resolver, direct control-plane
  chat, OpenAI chat completions, and Responses API.
- Focused worker-client tests for Swift/Python loaded-model inventory transport,
  missing-handle recovery, and fail-closed recovery after introspection errors.
- Focused desktop tests for registry-hydration Chat gating and ordered packaged
  provider creation, trusted identity context, reasoning-before-answer ordering,
  independent streaming state, 128-point overflow behavior, grapheme cadence,
  manual-scroll suspension, Reduce Motion fallback, provider-switch request
  invalidation, the streaming-time provider-picker gate, and stale
  `model_path_missing` suppression only when a matching Provider is genuinely
  interactive.
- Focused stream-assembler and receipt tests for truncated reasoning, partial
  close markers, and EOS recovery without reasoning-to-content duplication.
- Focused gateway tests for packaged listener authority, legacy owner fallback,
  bound-session roster refresh without live owner rebinding, last-known-good
  behavior and diagnostics after read/decode failures, sibling-lock failures,
  and concurrent gateway-config and serving-defaults read-modify-write
  preservation, plus cancellation and reuse of a contended nonblocking lease.
- Focused Swift-worker tests for repeated/concurrent load deduplication, failed
  load recovery, shared unload protection, active-request protection, and forced
  unload, plus tokenizer-declared end-of-turn token loading and Gemma channel
  framing across split markers in both generate and decode, including a Generate
  request whose parser authority exists only on the loaded model specification.
- Focused control-plane tests for cached-handle validation and lazy stale-handle
  recovery across independently constructed clients.
- Focused Responses tests for standard `max_output_tokens` mapping, validation,
  alias conflicts, and request receipts.
- Focused Python assembler tests for incremental `<think>` and Gemma thought
  channels, split close markers, disabled-reasoning suppression, malformed
  terminal recovery, split visible-tail candidates, bounded candidate overflow,
  close-confirmed low-latency flushing, and the Generate event sequence for an
  EOS-recovered answer before usage and completion.
- Focused development launcher tests for explicit environment listener authority.
- Focused CLI socket-discovery tests for one-sided descriptor fallback,
  per-socket usability validation, fully explicit atomic override, and invalid
  descriptor fallback.
- Focused prompt-token normalization and top-k propagation/sampling tests.
- Focused K=V projection-source coverage plus a real deterministic 31B
  multi-turn packaged-runtime comparison against the official Python output.
- Focused OCR declaration tests covering generic-only settings, declared OCR
  defaults, and declared OCR profiles using imported generation fallbacks.
- Focused Composer policy tests for Return, keypad Enter, Command-Return,
  pass-through modifiers, IME marked text and its post-composition guard, silent
  invalid submission, editor growth and expansion bounds, contextual status,
  repair-strip draft/focus preservation, and removal of the global
  Command-Return hot key.
- Focused direct-chat tests with distinct default and selected Server Sessions:
  lifecycle admission and wakeup follow the selected session, worker sampling
  uses its serving defaults, Desktop and CLI forward its ID, and long-lived
  serving-default stores observe sequential external writes.
- Packaged 980-by-760 visual acceptance plus real keyboard input proving Return
  sends and Command-Return edits a multiline draft before submission.
- Focused Swift coverage report for every changed production file.
- `make swift-test`
- `make py-test`
- `make integration-test`
- Packaged app smoke and signature checks.
- Real-model checks:
  - `melix chat run` answers a clean natural-language prompt coherently. The packaged CLI
    acceptance invocation must not inject worker socket environment variables,
    proving active-runtime discovery works.
  - `POST /v1/chat/completions` answers the same clean prompt coherently and
    reports the public model ID.
  - `POST /v1/responses` answers the same clean prompt coherently and reports
    the public model ID.
  - A natural reasoning prompt sent from Melix Chat emits a visible public
    Thinking block before the final answer, reaches completion, and persists in
    the desktop transcript.

## Hybrid A Verification Evidence (2026-07-22)

- The related macOS package regression selection passed 595 tests across
  `AppScreenshotCaptureTests`, `DesktopFoundationViewTests`, and
  `RuntimeViewModelTests` with zero failures.
- The packaging smoke suite passed 145 tests and all packaging target metrics.
- The production SwiftUI acceptance runner captured 25 scenarios at 980 by 760
  from the packaged App. Ready, no-Provider, missing-model, offline-Provider,
  and degraded-Provider Composer states retain the editor and the accepted
  Hybrid A hierarchy; equivalent global lifecycle and missing-model banners do
  not duplicate the local repair strip.
- The final App archive is ad-hoc signed, verifies after extraction, and bundles
  the compatible `mlx-metal` 0.31.1 resource. The installed artifact is
  `~/Downloads/Melix.app`; the replaced build is retained beside it as
  `~/Downloads/Melix.before-hybrid-a-<timestamp>.app`.
- The installed runtime answered `/health`, published the selected
  `mlx-community/gemma-4-31b-it-4bit` model through `/v1/models`, returned
  `MELIX_OK` through `/v1/chat/completions`, and returned `CLI_OK` through the
  packaged `melix chat run` command.
- Final changed-production-line coverage measured against `origin/main` meets
  the repository's 95-percent commit gate in every executable scope changed by
  this plan: macOS App 96.40 percent (1,956/2,029), control plane 97.91 percent
  (657/671), Swift text worker and vendored execution path 96.25 percent
  (873/907), CLI 100 percent (109/109), and Python runtime and packaging 98.58
  percent (277/281).
- The coverage runs also completed the corresponding full suites: 877 macOS
  tests across 25 suites, 1,189 control-plane tests across 42 suites, 288 Swift
  text-worker tests, 431 CLI tests with one skip, and 5,124 Python tests with 14
  skips. Structured Gemma 4 text companion routing, Swift Vision media routing,
  and speech-only Chat Completion rejection are covered explicitly so legacy
  route metadata cannot override the structured request-route contract.
- The final integration gate completed 123 tests with one skip and zero
  failures. The final packaging smoke gate completed 145 tests and reported all
  eight packaging-target metrics as healthy.
- An exploratory forced pre-commit run on the 64-GiB development host completed
  all three full test gates and all 15 selected performance probes. Seven
  focused coverage commands initially under-counted changes shared by their
  source files; after broadening those commands to the corresponding complete
  test files, every affected probe reports 100-percent changed-line coverage.
  The only in-scope hot-path signal, stream parser mode, measures 3.113 ms versus
  3.016 ms at the paired median (+3.22 percent, below the 5-percent gate) after
  restoring the buffer-only loop condition and retaining final reasoning
  recovery. The remaining reported timing warnings exercise production
  functions whose implementations are byte-for-byte unchanged from the base,
  while the same-cohort batching evidence is identical between base and head.

## Accepted Variant A Chat Chrome Evidence (2026-07-22)

- Six focused `DesktopFoundationViewTests` pass for compact workspace metrics,
  Human-readable Identity parsing, canonical-ID accessibility and copy
  disclosure, the 28-point Inline Glyph Cluster, the 232-point Precision
  Ledger, and preservation of the accepted Hybrid A Composer contract.
- The focused run compiles the production `DesktopChatView.swift` and renders a
  live Precision Ledger fixture with dynamic health, endpoint, trust, and idle
  values while confirming that repeated section headings and visible
  destination labels are absent.
- The design-system `ChatView.jsx` mirror parses and bundles successfully with
  Bun when the browser-provided React JSX runtime is marked external. The print
  mirrors and component reference document the same Header, capability, and
  Inspector hierarchy.
- The complete post-adoption macOS suite passed 875 tests across 25 suites with
  zero failures. Changed-production-line coverage for all seven touched macOS
  production files is 96.40 percent (1,956/2,029); `DesktopChatView.swift` is
  96.59 percent (1,390/1,439) and `RuntimeViewModel.swift` is 95.56 percent
  (516/540). Detail surfaces reuse the production popover bodies through
  internal test seams, Composer focus uses a mounted AppKit bridge, and copy
  verification uses an in-memory pasteboard so tests do not mutate the
  operator's clipboard.

## Pull Request Review Follow-up Evidence (2026-07-22)

- The gateway binding and last-known-good refresh selection passed 17 focused
  store and OpenAI integration tests. `GatewayConfigStore.swift` changed-line
  coverage is 97.13 percent (237/244). Refresh diagnostics are exported
  atomically into `MetricsStore` at bootstrap, on the HTTP rate-limit and model
  routing paths, through control-plane snapshots, and after failed config
  persistence. The metrics expose total and consecutive failures, last-known-good
  service state, failure timestamp, and a typed failure-kind code.
- Fail-closed cached-handle validation and Python loaded-model inventory passed
  88 focused Swift tests and five focused Python bridge tests. Swift changed-line
  coverage is 95.97 percent (119/124), with both changed production files at
  100 percent; Python changed-line coverage is 100 percent (12/12).
- Desktop provider rebinding and the streaming picker gate passed both focused
  tests. The four-file macOS review slice reports 98.25 percent changed-line
  coverage (56/57); the request-invalidation implementation and its behavioral
  test are fully covered, while the single SwiftUI `.disabled` modifier line is
  held by the adjacent source contract.
- Reasoning finalization and Python bridge coverage passed 181 focused stream,
  receipt, generation, and bridge tests. The stream recovery slice reports
  100-percent changed-line coverage (27/27).
- The final serial control-plane coverage run passed all 1,189 tests in 42
  suites. Aggregate changed-line coverage for the complete touched control-plane
  scope is 97.89 percent (1,905/1,946); the new MetricsStore batch write,
  OnDemand loader, Python bridge, and ControlPlaneService production lines are
  each at 100 percent. The coverage-only long-prefill polling window was widened
  after instrumentation exposed its previous 500-millisecond timing assumption.
- All three registered stream-assembler probes completed without correctness
  failures. The parser-mode probe ran 512 samples at a 5.891 ms mean, the
  structural-prefix probe retained all 1,750,000 expected identity and suffix
  hits, and the token-byte probe assembled all 80,000 events per sample with no
  decode errors. The pull-request performance workflow remains authoritative
  for the paired base-versus-head regression decision.

## Second Pull Request Review Follow-up Evidence (2026-07-22)

- Swift single-shot Generate now resolves Gemma framing from the loaded model
  specification when request metadata is absent. The complete Swift text-worker
  suite passed 289 tests; the changed `TextGenerationEngine.swift` slice reports
  100-percent changed-line coverage (41/41).
- Python EOS recovery now emits a recovered visible answer before usage and
  completion without changing the historical partial-marker stream contract.
  The focused stream and Generate selection passed 151 tests, and the complete
  Python suite passed 5,128 tests with 14 skips. The changed assembler and engine
  slice reports 97.35-percent changed-line coverage (110/113).
- The final paired Python probes reported no gated regression: parser-mode
  paired median was approximately +2.28 percent, structural-prefix was -7.11
  percent, and token-byte elapsed median was -2.74 percent. Every correctness
  checksum, structural hit count, tool call, channel transition, and decode
  error invariant passed.
- Gateway and serving-default writes now use cancellable nonblocking sibling
  leases, including a post-open cancellation guard that closes the acquired
  descriptor before propagating cancellation. The complete control-plane suite
  passed 1,191 tests across 43 suites. The changed lock and store slice reports
  97.37-percent changed-line coverage (111/114).
- CLI one-sided socket overrides now retain the live active-runtime companion
  socket while a fully explicit pair remains atomic. The complete CLI suite
  passed 432 tests across 10 suites with one skip; the changed factory slice
  reports 100-percent changed-line coverage (22/22).
- Desktop Chat trusts a matching interactive Provider over stale catalog cache
  state only during attachment, submission, and preload decisions; explicit
  load and Restore Download continue to observe the real cache state. Three
  focused regressions, 281 Desktop Foundation tests, and the complete macOS
  suite of 878 tests across 25 suites all passed. The changed
  `RuntimeViewModel.swift` slice reports 96.30-percent changed-line coverage
  (26/27).
- The transient reasoning, tool, and assistant presentation test records the
  synchronous state-notification history instead of polling the current state.
  It verifies exclusive visibility and the exact reasoning-to-tool-to-assistant
  sequence without depending on scheduler timing; the final test passed five
  consecutive runs, and the adjacent zero-delay/out-of-order regression passed.
- The final integration gate passed 123 tests with one skip. The packaging smoke
  gate passed 145 tests and all eight packaging-target metrics.

## Known Boundaries

- This repair covers text-only conversation with the selected Gemma 4 VLM.
- Media-bearing Gemma 4 requests retain the existing multimodal route and are
  not redefined by this task.
- Model weights are unchanged. The vendored Gemma 4 attention implementation is
  corrected to match the model's published K=V semantics.
- The UI displays only public model-emitted reasoning. It does not expose hidden
  system prompts, private continuity data, or implementation-internal traces.
