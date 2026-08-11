# Melix Architecture Spec

Date: 2026-03-27

## Summary

Melix is a native control plane plus worker-runtime architecture for local AI execution on Apple Silicon. The Swift runtime baseline for the shared protocol and worker path is macOS 15 or newer. The system is built around four layers:

1. A native SwiftUI desktop app for local operations, chat, image workflows, and model tools.
2. A Swift control plane daemon that owns system truth.
3. A polyglot worker pool connected over local RPC.
4. A tiered cache and storage layer that persists reusable execution state.

The design is optimized for agent-oriented workloads: repeated prefixes, tool-call recovery, branch-aware sessions, and fast follow-up requests.

Melix should keep the control plane Swift-first while moving the latency-critical default text path toward a dedicated Swift text worker. Python workers remain the primary execution layer for multimodal, embeddings, rerank, image, audio, and maintenance flows. See `decisions/2026-03-27-swift-text-runtime.md`.

## Runtime Topology

```text
┌────────────────────────────────────────────────────────────┐
│                Melix Desktop App (SwiftUI)                │
│ dashboard, models, tools, settings, logs, bench, chat,    │
│ image, HuggingFace sync, and operator workflows           │
└────────────────────────────────────────────────────────────┘
                            │ XPC (packaged)
                            │ private typed UDS (source-tree development)
                            ▼
┌────────────────────────────────────────────────────────────┐
│             Melix Control Plane Daemon (Swift)            │
│  HTTP/SSE gateway, scheduler, EnginePool, CacheIndex,     │
│  SessionRegistry, AgentRunCoordinator, policy, admin      │
└────────────────────────────────────────────────────────────┘
          │ gRPC over Unix Domain Sockets       │ typed local RPC
          ▼                                     ▼
┌────────────────────────────────────────────────────────────┐
│              Melix Worker Pool (Swift + Python)           │
│  swift text, python multimodal, MCP and tool execution    │
└────────────────────────────────────────────────────────────┘
                              ┌───────────────────────────────┐
                              │ Native Computer Use Broker    │
                              │ ScreenCaptureKit, AX, evidence│
                              └───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│                 Cache and Storage Layer                    │
│  L0 active state, L1 memory blocks, L2 SSD blocks,        │
│  boundary snapshots, metadata index                       │
└────────────────────────────────────────────────────────────┘
```

## Naming and Runtime Identifiers

Melix should use a single naming system across product docs and implementation examples.

- Repository root: `melix/`
- App bundle identifier: `com.melix.app`
- Control plane identifier: `com.melix.controlplane`
- XPC service identifier: `com.melix.controlplane.xpc`
- CLI name: `melix`
- Socket root: `/var/run/melix/`

Example socket layout:

```text
/var/run/melix/
  controlplane.sock
  worker-text-001.sock
  worker-vision-001.sock
  worker-image-001.sock
```

## Process Boundaries

### Menu Bar App

The desktop app is a native operations surface. It should:

- Connect only to the control plane through XPC in the final signed service
  boundary, or through the private typed control-plane UDS transport in the
  source-tree and packaged-preview launchers.
- Render snapshots and event-driven updates.
- Offer dashboard, models, tools, settings, logs, bench, chat, and image workflows only where backend support already exists.
- Offer model pin, warmup, unload, cache purge, quantization, HuggingFace upload or download, and adapter workflows through control-plane commands.
- Avoid direct access to worker sockets, cache databases, or on-disk payloads.

The desktop product may use multiple SwiftUI windows or tabs, but it remains one app process backed by the same control-plane truth.

### Control Plane Daemon

The control plane is the system coordinator and source of truth. It owns:

- OpenAI-compatible and Anthropic-compatible local HTTP APIs
- Ollama-compatible local HTTP APIs where planned by the roadmap
- Request admission and scheduling
- Session, branch, and workflow metadata
- agent-run orchestration, approval policy, budgets, and cancellation truth
- Model registry and EnginePool
- Cache metadata index
- Worker discovery and health state
- Operational flows such as doctor, bench, logs, diagnostics, quantization jobs, training jobs, and HuggingFace sync

This layer should remain Swift-first because it carries the longest-lived product logic.

There is exactly one control-plane writer for an effective `MELIX_HOME`. The
daemon acquires a process-lifetime advisory writer lease before constructing
stores or runtime services. The private lock file is a current-user regular file
inside the private state directory, and its persisted fencing token is also the
daemon instance ID. A second daemon for the same home fails fast; after a clean
release, a replacement daemon receives a new generation token. The desktop app
must never construct another `ControlPlaneService`, worker registry, model
catalog, or tool signer in its own process.

CLI in-process fallback obeys the same lease boundary. A missing, stale, or
invalid active-runtime descriptor may select the standalone route, but the CLI
must acquire and retain the `MELIX_HOME` writer lease before constructing a
mutable control plane. If another daemon or CLI owns it, operations fail closed
with a repairable ownership error instead of creating a second writer.

The final signed distribution keeps the XPC-first app boundary. Source-tree and
packaged-preview launchers use the schema-generated `ControlPlaneIPCService`
over a private Unix domain socket so native walkthroughs and preview bundles
preserve the same one-daemon ownership model before the launchd/XPC package is
installed. That private transport
accepts only bounded typed protobuf messages, creates its parent as a
current-user `0700` directory, seals the socket to the current user with `0600`
mode, refuses to replace paths it does not own, and removes only the socket it
validated. Clients independently reject non-private, non-owned, non-socket, or
non-canonical endpoints. A Chat stream must return start metadata within a
bounded client deadline; expiry cancels the transport task and therefore the
server request. It carries handshake, command execution, subscriptions, Chat
stream and cancellation, and Agent-run start. It does not give the app or CLI
worker socket paths, the Computer Use broker socket, or the control-plane
authorization key. A separately invoked CLI uses an explicit control-plane
socket or the live, validated active-runtime descriptor and otherwise retains
the standalone in-process fallback; an explicitly malformed socket fails
closed rather than constructing a second writer. The private UDS does not
provide XPC audit-token code-sign identity; it is an interim local transport,
not a claim that packaged XPC validation is complete.

The packaged-preview launcher keeps `MELIX_RUNTIME_DIR` as the home for
metrics, caches, logs, and the active-runtime descriptor, but it must not derive
UDS pathnames directly from that potentially long operator-selected path. Each
launch creates one unpredictable current-user `0700` socket root under `/tmp`,
validates that the root is a real directory owned by the
effective user, and verifies every worker, control-plane, and Computer Use
socket pathname is at most 103 UTF-8 bytes before any service is forked. The
launcher removes only the files and directory created for that exact launch.
Root creation, validation, or cleanup failure is explicit and never falls back
to a shared fixed pathname.

The foreground bundle identifier belongs to exactly one regular AppKit process:
the desktop UI. An AppKit-linked helper must not inherit or register under the
foreground bundle identifier. The packaged Computer Use broker therefore lives
inside its own nested background-only helper bundle with a distinct identifier,
while the outer app's `Contents/MacOS` UI binary remains the only regular
application for the foreground identifier. Native acceptance must verify this
process identity through the current signed bundle before relying on
Accessibility or window automation evidence.

For model discovery, the control plane owns the typed `ModelCatalog` exposed to XPC and local HTTP clients, but it should synchronize registry-discovered entries from worker-owned snapshots instead of deriving registry state from scattered per-model environment variables.

### Worker Pool

Workers are execution engines, not public servers. The worker plane may be implemented in multiple languages so long as it stays behind the shared worker RPC contract.

Workers own:

- Model runtime load and unload
- Prefill and decode execution
- Cache materialization and restoration
- Tool and reasoning parser glue
- normalized tool execution, including live MCP client lifecycle
- Multimodal execution
- Maintenance flows such as conversion, diagnostics, and benchmarking

Workers should not expose network-facing APIs beyond local RPC.

### Computer Use Broker

Computer Use executes in an independent Swift process attached to the
active macOS GUI session. It owns only native desktop execution and bounded
evidence:

- ScreenCaptureKit window capture;
- AXUIElement inspection and semantic press;
- broker-local permission state, action commit state, and evidence artifacts.

The broker does not call models, evaluate approval policy, or own agent-run
state. The control plane supplies a short-lived session capability and an
approval grant bound to the exact run, tool call, action digest, target, policy
revision, actor, and expiry. The broker must reject stale frame handles,
cross-owner capabilities, secure fields, targets outside the allowlist, and any
action after cancellation or session expiry.

The current transport is a private Unix-domain socket with path owner, mode,
inode, and device checks, a private caller verification capability, and exact
Ed25519 request authorization. The current gRPC UDS API does not expose a macOS
audit token, so the broker cannot attest the peer's code-sign identity. This is
an explicit advertised boundary, not evidence of a signed peer. Text, key,
scroll, pointer, and coordinate actions remain unsupported in the current
semantic-press capability.

Source-tree launchers create distinct per-instance `0700` parents for the
control-plane and Computer Use sockets under the configured short socket root.
The broker verification capability is a `0600` regular file in the broker's
private parent. Launcher path normalization must preserve the operator-selected
canonical spelling across Python and Foundation; it must not resolve a socket
root alias into a spelling that the receiving runtime will reject after the
file exists. The headless broker initializes an AppKit application with the
prohibited activation policy before serving ScreenCaptureKit requests; this
establishes the GUI-session connection without presenting a Dock app.

The app must not execute Computer Use directly or infer broker permission from
the app's own TCC state. The broker reports its own Screen Recording and
Accessibility state. System permission prompts require an explicit operator
gesture and must never be triggered by a model tool call.

#### Swift Text Worker

The default text generation path should move into an independent Swift text worker. In its first implementation phase it should own:

- text `Generate`
- model lifecycle for text models routed to the Swift path
- text streaming and abort
- latency-critical text runtime integration

It should not:

- run inside the control plane process
- silently fall back to the Python text path on failure
- take ownership of multimodal or maintenance families in the same phase

#### Python Workers

Python workers remain the broader execution layer. They should continue to own:

- multimodal execution
- embeddings and rerank
- image and audio families
- convert, quantize, upload, download, train, doctor, info, and bench flows
- any text-compatible compatibility path retained during migration

Embedding execution uses one worker runtime interface with explicit backend
identity. `mlx-bert-v1` and `mlx-xlmr-v1` load a local tokenizer,
`config.json`, and safetensors into the existing model-handle lifecycle. They
tokenize one request batch and perform exactly one encoder forward before
device-side pooling and normalization. `deterministic-fixture-v1` is reserved
for repository fixtures and development seed models; catalog metadata must not
advertise its digest projection as BERT or XLM-R execution. The legacy
`bert-v1` and `xlmr-v1` identifiers are not executable aliases; callers must
migrate explicitly to the named fixture backend or to an artifact backend.

Artifact-backed embedding discovery requires both an explicit MLX signal and
structured embedding metadata such as a supported Sentence Transformers
pooling module. A BERT-shaped `model_type` or directory name alone is not
enough to create an embedding route. The runtime verifies the artifact again at
load, copies supported files through no-symlink descriptors into a private
read-only snapshot, and computes model and tokenizer hashes from that snapshot.
Admission requires a vocabulary-bearing tokenizer artifact; auxiliary token
metadata alone is not executable. Encoder dimensions include a positive layer
count, so an empty encoder stack is refused.
Tokenizer construction and weight loading may consume only the bound snapshot;
the source model path remains provenance and is not reopened by the backend.
Media or multi-vector artifacts are refused before model execution. Decoder,
encoder-decoder, cross-attention, and non-absolute-position BERT configurations
are rejected until the local encoder implements them. An active Sentence
Transformers pipeline must be exactly `Transformer -> Pooling -> optional
Normalize`; unsupported or reordered modules fail closed. Snapshot file
identity and content hashes are verified after tokenizer and weight loading so
a receipt cannot describe bytes different from those consumed for execution.

Artifact embedding load, inference, and teardown share the Python worker's
single-owner MLX executor with text and VLM execution. The public embedding
response remains a list of dense vectors. Effective load evidence and the
latest bounded request receipt are projected through the loaded model summary
rather than added to that response.

MLX-backed Python text compatibility and VLM runtimes must execute model load,
warmup, prompt/template preparation, and token streaming on an executor-owned
runtime thread. The executor is responsible for initializing the MLX stream
context on that thread when MLX is available and for publishing runtime evidence
through `RuntimeStats.generation_stream_owner_mode`,
`RuntimeStats.worker_thread_init_latency_ms`, and
`RuntimeStats.stream_sync_fallback_count`. Control-plane observability should
project those fields into `python_worker.*` metrics whenever worker runtime
stats are refreshed, and it must reserve distinct numeric sentinel codes for
missing owner-mode state versus unrecognized future owner-mode strings.

Python workers also own ordered multi-root on-disk registry scanning. Registry sources are user-configured model roots first, followed by the effective Hugging Face cache root when it exists: `HUGGINGFACE_HUB_CACHE`, `<HF_HOME>/hub`, or the default `~/.cache/huggingface/hub`. Root order is significant, the first root wins on duplicate `model_id`, and invalid roots must not poison discovery from valid roots. Scanning recognizes Hugging Face cache snapshots at `models--<org>--<repo>/snapshots/<snapshot-id>` and plain local MLX model directories that contain `config.json` plus model weights. The scanner must skip Hugging Face `blobs` payloads and must not load the MLX runtime during discovery.

Melix-managed Hugging Face downloads write model bytes directly into the resolved Hugging Face cache root by passing that path as `snapshot_download(cache_dir=...)`. The default root is `~/.cache/huggingface/hub`; request metadata `melix.hf_cache_root` or `hf_cache_root` takes precedence, followed by process-level `HUGGINGFACE_HUB_CACHE` and `HF_HOME` roots, even when the target directory does not exist yet. New Hub downloads no longer create registry descriptors under `MELIX_MANAGED_MODEL_ROOT`, and download receipts report both the real runtime snapshot path and `melix.effective_hf_cache_root`. Registry metadata for cache/root-discovered models exposes `melix.model_path`, `melix.source_kind=hf_cache_snapshot` or `local_mlx_directory`, `melix.registry_root_path`, and `melix.registry_relative_path`; Hugging Face cache snapshots also expose `melix.hf_repo_id` and `melix.hf_revision`. Cache/root-discovered models do not expose `melix.registry_descriptor_path`. If a Hugging Face snapshot is deleted and the registry is rescanned, the model disappears instead of entering a descriptor-driven missing-cache state. Legacy descriptor scanning remains only as a compatibility path for older managed roots that are still configured.

Registry discovery is intentionally MLX-only. A model is published only when repo identity, README/card metadata, tags, `library_name`, file metadata, or local path naming provides an explicit MLX signal. Non-MLX Transformers repositories, unreadable directories, and ambiguous local model folders are hidden.

Hugging Face download tokens are stored by the Swift CLI/Desktop layer in `$MELIX_HOME/secrets/huggingface-token.json` with private directory and file permissions. The token is sent to the worker only as a transient request `ext` value for `snapshot_download(token=...)`; token-like values must be redacted from operation state, manifests, registry metadata, `/v1/models`, logs, and UI surfaces. Hugging Face 401/403 failures map to `hf_auth_failed` with message `Hugging Face authentication failed. Check your token and try again.` Local imports remain copied into `MELIX_MANAGED_MODEL_ROOT/local/<model-id>/<revision>`.

### Storage Ownership

Metadata and payload ownership are split intentionally:

- Control plane owns metadata truth, scopes, summaries, and indices needed for scheduling and UI.
- Workers own materialized payloads, active decode handles, block files, and snapshot payloads.

Melix must not send large tensor or KV payloads over RPC.

## Public and Internal Interfaces

### External HTTP API

V1 should expose these local endpoints:

- `POST /v1/chat/completions`
- `POST /v1/completions`
- `POST /v1/responses`
- `POST /v1/embeddings`
- `POST /v1/rerank`
- `POST /v1/images/generations`
- `POST /v1/images/edits`
- `POST /v1/audio/transcriptions`
- `POST /v1/audio/speech`
- `POST /v1/messages`
- `GET /v1/models`
- `GET /v1/cache/stats`
- `GET /health`
- `GET /v1/melix/health`

`GET /health` is public liveness only. Route readiness and model counts belong
to the authenticated `GET /v1/melix/health` diagnostics endpoint.

When gateway authentication is enabled, all non-liveness routes share the same
access policy before body decoding or worker dispatch. Shared API-key mode
accepts both `x-api-key` and `Authorization: Bearer` only for configured keys;
the accepted key ID is the rate-limit identity for both header forms and for
persistent auth sessions issued from that key. Rate-limit refusals must not
echo raw credentials.

MCP tool integration must discover configuration only from explicit operator
inputs or Melix-owned state: `MELIX_MCP_CONFIG_PATH` first, then
`$MELIX_HOME/config/mcp-tools.json`. Process current working directory files are
not configuration sources. Diagnostics must expose the requested/effective MCP
policy, refused high-risk namespaces, operator override source, and discovery
receipt.

MCP environment references are worker-only credentials. Development launchers
must parse the active config through the same discovery order with bounded input
and validated environment-key names. After trimming, an explicit
`MELIX_MCP_CONFIG_PATH` must be an absolute path or use current-user `~` /
`~/...` syntax; relative paths, named-user tilde paths, NUL, and paths over 4096
UTF-8 bytes fail closed. Current-user tilde expansion accepts `HOME` only when
it is absolute, otherwise it uses the platform current-user home, and every
boundary lexically standardizes the result without imposing a different
symlink-resolution policy. The Python tool worker inherits only the values
referenced by the active configuration at worker startup so it can resolve
stdio and HTTP credentials at connection time. An active-config change that
introduces a new credential source key is restart-required and fails closed in
the running worker; arbitrary unreferenced parent credentials never enter the
worker. The app, its CLI children, readiness probes, Swift model workers, control
plane, and Computer Use broker start from a minimal allowlist whose keys are
reserved from MCP references; this prevents both current references and values
that become referenced after an earlier child was forked from crossing the
boundary. The App/CLI, control plane, Swift workers, probes, broker, and Python
worker each have an explicit role contract; shared workflow settings are
declared for every role that consumes them, while gateway credentials remain
control-plane-only and MCP credential references remain Python-tool-worker-only.
The Python worker repeats the same reserved-key validation when typed stdio or
HTTP source configuration enters the runtime, so a caller cannot bypass the
launcher boundary. Credential source keys, stdio child environment names, and
static or referenced HTTP header names are bounded to 255 UTF-8 bytes each.
Credential-bearing headers such as authorization, cookie, token, secret, and
API-key headers must use environment references and are invalid as static
values. HTTP names must use RFC token-compatible ASCII syntax and static/referenced
names within one transport must be unique case-insensitively. A config has at
most 1,024 credential references across stdio and HTTP, with the raw reference
target-name list bounded to 32,768 bytes. Independently, all raw static and
referenced HTTP header-name entries across the config share a 1,024-entry and
32,768-byte budget; an HTTP credential reference counts against both budgets.
The deduplicated comma-separated credential source-key list is also bounded to
32,768 bytes, so valid-looking configuration cannot exhaust child-process
argument or environment space.
Launchers freeze one deduplicated, bounded credential-key snapshot from the
initial active configuration before any child is forked. A later refresh may
only remove keys from that snapshot; introducing a new key fails closed with a
restart-required receipt. The Python tool worker receives values only for the
frozen active snapshot, non-Python roles receive none of those values, and the
App sentinel carries the same frozen key list for descendant sanitization. The
control plane independently accepts only a regular configuration file no larger
than 1 MiB. Launcher, App, and direct-daemon readers resolve the operator-selected
symlink path, open the final path component with no-follow and non-blocking flags,
then classify, size-check, and bounded-read that same descriptor. A replacement
with a FIFO, device, directory, or final-component symlink therefore fails closed
before any configuration bytes are consumed. Raw JSON admission rejects duplicate
object keys, non-standard
numeric constants, every non-integer numeric lexical token, explicit null for
known fields, nesting deeper than 128,
more than 16,384 value tokens, or more than 8,192 object members. The config has
at most 256 sources, source IDs matching the worker's bounded
64-byte identifier contract with no normalized duplicates, supported transport
kinds with their required typed fields, and the same reference/header
cardinality and name limits. Launcher and App preflight enforce that same source
and transport shape before forking the stack. Direct daemon startup therefore
cannot bypass launcher preflight or turn a special-file replacement into an
unbounded read.
Missing default config means no referenced
credentials; an explicit unreadable, oversized, or invalid config must stop App
launch rather than silently passing an unknown credential set through it.

Remote media ingress must pass URL admission before a request can reach any
future download or worker dereference path. Local paths and `file:` URLs remain
local media references. Remote media URLs require `https` and a public host;
loopback, private, link-local, and malformed hosts fail with typed operator
errors and refusal metrics.

The gateway should also leave room for Ollama-compatible local endpoints such as:

- `POST /api/chat`
- `POST /api/generate`
- `GET /api/tags`
- `POST /api/show`
- `POST /api/embeddings`

Streaming should use SSE and support:

- content deltas
- reasoning deltas when supported
- tool-call deltas
- usage trailers
- cache trailers
- heartbeat events

Melix may accept additional local-only request fields such as:

- `session_id`
- `branch_id`
- `parent_request_id`
- `cache_policy`
- `pin_prefix`
- `save_checkpoint`
- `latency_class`
- `workflow_run_id`
- `workflow_node_id`

### Control Plane Protocol

The control plane protocol should be command-and-event oriented, versioned, and schema-driven.

The envelope should combine normalized metadata such as `command_type`, `event_type`, `source`, `correlation_id`, and `causation_id` with typed protobuf bodies for first-party command and event families. Melix should not collapse core control-plane traffic into an untyped `bytes payload` transport model.

Required XPC entry points:

- `handshake`
- `execute`
- `subscribe`
- `unsubscribe`

Command families:

- `ServerCommand`
- `ModelCommand`
- `CacheCommand`
- `SessionCommand`
- `OpsCommand`
- `PresetCommand`

Core event families:

- server state
- worker state
- model state
- request progress
- session state
- cache stats
- resource pressure
- benchmark progress
- logs

### Worker RPC

Worker RPC should be defined with gRPC over Unix Domain Sockets and cover four service groups:

- `RuntimeService` for lifecycle and model loading
- `InferenceService` for `Generate`, `Prefill`, `Decode`, `Abort`, and multimodal execution
- `CacheService` for stats, prefix pinning, snapshots, and cache purge
- `MaintenanceService` for convert, info, doctor, and bench

Melix should keep `Generate`, `Prefill`, and `Decode` because the split is required for chunked prefill, tool recovery, checkpointing, and future scheduler upgrades. These RPCs should share one underlying execution schema so tracing, metrics, scheduling hints, and event semantics remain unified.

The same RPC contract should be implementable by both Swift and Python workers. The control plane should route by worker capability and engine class rather than by implementation language assumptions.

## Request Model and Scheduling

### Request Identity

Every execution request should carry identity that supports scheduling and cache reuse:

- `request_id`
- `session_id`
- `branch_id`
- `parent_request_id`
- `workflow_run_id`
- `workflow_node_id`
- `latency_class`

These fields are not decorative. They determine queue priority, cache affinity, checkpoint scope, and tool-follow-up recovery.

The control plane should also expose session graph state, including branch lineage, active branch, head request, checkpoint state, and resume snapshot metadata.

### Queue Design

Melix should use four scheduling lanes:

- `Q0`: interactive decode, tool follow-up, immediate same-session continuation
- `Q1`: hot-prefix prefill with strong cache affinity
- `Q2`: cold or long prefill, including chunked prefill and checkpoint-friendly work
- `Q3`: background work such as embeddings, rerank, convert, bench, warmup, image, and audio tasks

The control-plane and worker protocols should use explicit lane identifiers rather than exporting the `Q0-Q3` shorthand directly:

- `Q0` maps to `text.decode.interactive`
- `Q1` maps to `text.prefill.hot`
- `Q2` maps to `text.prefill.background`
- `Q3` remains the conceptual background lane family for later non-text phases

The control plane protocol should expose queue read models, including lane-level queued counts, active counts, queue delay, admission latency, and backpressure.

Worker requests should also carry scheduling hints such as lane, priority, latency sensitivity, and queue delay so execution can honor control-plane intent without turning the worker into the global scheduler.

The current continuous-batching baseline should be enabled only on the Swift text route and only for phase-aware prefill work. Batch cohorts should be keyed by route, model, prefill lane, and cache-affinity class so hot and restored work do not collapse into the same admission group accidentally. Admission fairness should remain FIFO across cohorts: a compatible request may join the active batch only while no earlier incompatible work is already queued.

### Priority Function

Requests should be ordered with a weighted function shaped by:

- latency class
- cache affinity
- session continuity
- aging
- estimated prefill cost
- memory pressure

This prevents Melix from behaving like a simple first-come-first-served server.

### Abort and Resume

Melix must support:

- abort during queued, prefill, or decode phases
- resume from a saved boundary snapshot
- fast follow-up after tool execution

The control plane should translate cancellations into best-effort worker aborts and still produce explicit terminal request state.

## Cache Architecture

### Tier Layout

Melix uses three cache tiers:

- `L0`: active runtime state for current execution
- `L1`: in-memory shared prefix and paged block cache with dedup, refcounting, pinning, and copy-on-write
- `L2`: SSD-backed block and snapshot store for restart-safe reuse

This layout is the product architecture and exists to balance hot-path latency
with persistence. Runtime capabilities must still describe the payloads that a
particular worker can execute; a metadata index alone is not an implemented
cache tier.

The default cache mode should remain `tiered`, which requests compatible L1 and
L2 reuse without experimental eviction or rolling-window behavior. A worker
that does not own executable payloads for one of those tiers must fail that tier
closed and advertise the narrower capability. Melix should also reserve
explicit protocol-visible cache modes for experimental long-context execution:

- `rotating`: a rolling active-window strategy for long decode paths where earlier KV state may be compacted behind a stable restore boundary
- `hybrid`: a mixed strategy that keeps tiered prefix reuse while allowing a rotating active window for the tail of execution

These modes should be visible in runtime policy and cache metrics before they become default execution behavior. Experimental modes must remain opt-in until benchmark and recovery evidence are stable.

### Scope and Reuse Rules

Cache reuse should be isolated by a scope that includes:

- model identity and revision
- tokenizer hash
- quantization profile
- prompt template hash
- parser mode
- reasoning mode
- multimodal adapter identity when relevant

Prompt reuse should rely on stable fingerprints and block tables rather than raw text-only matching.

The control plane should expose logical cache identity through cache keys and block or snapshot references, while keeping cache payloads worker-side.

The worker schema should define typed `CacheKey` and `BlockTable` structures so cache reuse and resume are computable protocol concepts rather than opaque identifiers. KV cache quantization should happen at the storage boundary so active execution can stay accuracy-aware while persisted cache assets remain space-efficient.

### Current Swift Text L1 Contract

The Swift MLX text worker implements executable L1 paged KV reuse for models
whose complete cache layout is append-only `KVCacheSimple` state. Each admitted
block owns the real per-layer key and value tensors. Its reported bytes are the
sum of those tensor shapes and dtypes, never a token-count estimate.

The worker restores and pins the longest block-aligned production-token prefix
atomically. Restored immutable blocks can be shared by stored prefixes and
active decode sessions; request-private suffixes append separately, and a
partial trim copies only the affected shared block. Attention receives a paged
cache view that gathers the shared block table plus the private tail. Physical
resident bytes count each shared tensor block once and each active private
allocation owner's current per-layer tensors once. Logical bytes include stored
prefix ownership, active shared-block leases, and active private tails. Private
owner bytes are refreshed after append, trim, copy-on-write, state replacement,
and release, so L1 and runtime `kv_cache_bytes` cannot report zero while a
private paged tail is live.

Compatibility includes the loaded model residency epoch, MLX stream owner,
full cache scope, acceleration profile, prefill-shape signature, block size,
and every layer cache type. Every variable compatibility component is encoded
as a UTF-8 byte-length-prefixed value, so delimiter characters inside scope or
model fields cannot create a cross-scope signature collision. The backend derives the prefill-shape signature
from the prepared `LMInput` tensor rank, dtype, non-token dimensions, mask and
multimodal presence, plus the block-aligned maximum model-call shape derived
from the effective prefill window. The same configured chunk and the actual
call count and min/max token shapes are execution metrics; request extension
fields cannot supply or override them. The token block digest chain is the
stored boundary identity. A reuse store is accepted only with the still-current,
same-generation lookup-and-pin result whose signature, block size, layer count,
digest prefix, lease, and pool membership all validate under the pool lock.
Materializing a lookup transfers its lease into one cache set exactly once;
subsequent materialization attempts return no caches, and the lookup retains
only a weak lease reference for the later atomic store validation. Successful
stores also pin the new generation under that lock and transfer the committed
lease exactly once into the decode caches. The submitting private owner is
removed from private accounting only inside the same owner-to-pool transaction
that transfers those tensors into committed shared blocks; a failed store
leaves the owner accounting unchanged. Arbitrary snapshots cannot construct an
unaccounted decode view.
Rotating or moving-window caches, recurrent or composite state, mixed layouts,
unsupported input shapes, stale lookup handles, and active-KV-quantized state
are not admitted. Those requests use ordinary contiguous prefill and return a
typed fallback reason without recovered-token credit.

If budget admission or atomic snapshot validation fails after paged model
prefill has already computed K/V, the worker does not run model prefill again.
It materializes that evaluated state once into ordinary `KVCacheSimple`
instances, releases the paged private owner and block lease, and continues
decode on the contiguous caches with `admitted=false` and the typed failure
reason. Any reused-prefix evidence remains audit evidence for work already
executed; it is not an active paged-cache admission claim.

Paged cache views retain the exact MLX stream that created their tensor state.
Decode on a different current stream materializes the already-computed state
once into `KVCacheSimple` caches and records `paged_stream_owner_mismatch` in
the decode fallback summary. Homogeneous batch admission rejects such paged
rows before model evaluation so each request takes the same per-request
materialization path.

The pool enforces the effective request/model/process cache budget against real
resident tensor bytes, including other active private owners. The submitting
owner is not double-counted when its tensors become the proposed shared blocks.
The prefill response reports this same tightest effective budget; global cache
statistics without a request context continue to report process headroom.
The pool evicts least-recently-used unleased entries only; active decode leases
and private owners remain resident, and an admission that cannot fit without
reclaiming them is rejected without mutating the prior pool state.

Homogeneous decode remains available for compatible paged sessions. The batch
adapter retains each request's original paged cache and block lease, splits
incoming K/V updates by batch row, and concatenates the resulting full K/V
state for attention. When a cohort shrinks or materializes, the adapter returns
the same row cache objects rather than reconstructing dense caches. Admission
requires equal paged layout signatures, offsets, per-block tensor shapes, and
metadata across all layers.

The current Swift disk records and boundary snapshot records contain cache
identity and block-table metadata, not executable KV tensor payloads. Therefore
the Swift worker advertises `supportsDiskCache=false` and
`supportsBoundarySnapshots=false`; an L2 metadata match cannot restore tokens,
increment an executed hit, or populate an L1 tensor block. A future Swift L2
implementation must persist and validate architecture-aware tensor payloads
before those capabilities can become true.

### Pinned Prefixes

Melix should support pinning reusable prefixes for:

- system prompts
- developer prompts
- tool schemas
- fixed examples
- response format wrappers

Pinning should refer to logical cache objects, not raw prompt strings.

### Boundary Snapshots

Boundary snapshots are required for fast recovery around:

- tool calls
- long chunked prefill
- branch transitions
- hybrid-model state that cannot be reconstructed by simple prefix slicing

Snapshots and block tables must be first-class runtime concepts, not ad hoc implementation details.

## Model Lifecycle and Operations

### EnginePool

The control plane should manage models through an EnginePool that handles:

- discovery
- load and unload
- pin and unpin
- warmup
- TTL and LRU eviction
- budget-aware admission
- model aliasing and type overrides
- per-model sampling and template policy
- acceleration profile selection
- HuggingFace import and export workflows

Multi-model lifecycle is a product capability, not a worker-only implementation detail.

EnginePool should also treat engine class as a first-class routing dimension. In the next runtime phase:

- text models default to the Swift text worker
- non-text model families continue to route to Python workers
- Swift text worker failures should surface explicitly rather than silently re-route to Python

### Runtime and Maintenance

Workers should also expose operational tools as product features:

- `melix convert`
- `melix quantize`
- `melix upload`
- `melix download`
- `melix train`
- `melix info`
- `melix doctor`
- `melix bench`

These flows should be backed by the same runtime metadata model used by the control plane.

### Agentic Tool Runtime

Agentic training replay, online rollout, benchmark, and evaluation must share one
worker-owned tool registry contract. The built-in registry lives in the Python
worker runtime and exports deterministic OpenAI-compatible function schemas plus
Melix `ToolConfig` metadata for image crop, layout parsing, text search, image
search, visit, and local compute tools. The deterministic local adapter runtime
executes those six tools in fixture-backed mode and projects the same evidence
shape into SFT replay, RL alignment trace rows, benchmark request rows, and
evaluation sample JSONL artifacts.

Tool observations must cross the same worker-owned boundary before they are
persisted into training traces, benchmark artifacts, or evaluation evidence. The
observation contract sanitizes nested payload text through configured exact
redaction terms, enforces UTF-8 byte limits without invalid text, records
completed/timeout/failed status metadata, and emits deterministic replay
fingerprints over the sanitized payload plus call identity. Downstream consumers
must treat the sanitized observation record as the durable source of truth rather
than re-reading raw adapter output.

Interactive agent runs extend this deterministic foundation without changing
its ownership. One control-plane `AgentRunCoordinator` owns the model-turn
loop, tool admission, approval waits, budgets, cancellation tree, and terminal
run receipt. The Python worker exposes one deep `ToolExecutionRuntime` boundary
for deterministic built-ins, live MCP sources, and Computer Use through the
native broker. The desktop app renders this state and submits typed operator
decisions; it never invokes a tool adapter directly.

Each active model execution owns one cancellation single-flight gate. Explicit
Stop and model-stream task cleanup share that gate, so Swift actor reentrancy
cannot dispatch the same transport cancellation more than once.

The desktop pre-binds an unpredictable run ID before Agent admission. The
control plane reserves that identity while it loads catalogs and validates
targets, prepares the coordinator in a suspended state, and resumes model work
only after the run is durable and addressable by `CancelAgentRun`. Interactive
admission is two-phase: `StartAgentRun(defer_activation = true)` returns the
durable suspended snapshot, then a separately authenticated
`ActivateAgentRun` begins model work. Stop during admission records terminal
intent immediately. If Stop is reordered ahead of Start, the client retries it
after the Start reply and withholds activation, so no provider turn or tool
execution may begin.

Live MCP support must perform protocol initialization and version negotiation,
discover tools with `tools/list`, execute with `tools/call`, process catalog
change notifications, and close or cancel transports deterministically. Stdio
servers use explicit command vectors and a scrubbed environment. Streamable
HTTP servers use configured URLs and credential references; credential values
must not enter catalogs, prompts, logs, receipts, or UI read models.

The initial live loop executes tool calls sequentially. It validates completed
argument fragments as a JSON object, binds every call to one run and schema
digest, enforces turn and call budgets, projects normalized results as
untrusted prompt data, and starts another model turn only while the run remains
non-terminal. Parallel tool execution is not permitted until the same approval
and cancellation guarantees are proven for a group.

### Quantization

V1 requires:

- offline model conversion
- advanced quantization manifests and profiles
- quantization manifests
- KV cache q4 and q8 support at storage boundaries
- a path for lower-bit and mixed-precision cache or model quantization profiles

Worker maintenance flows should also leave room for:

- artifact upload to HuggingFace
- artifact download from HuggingFace
- LoRA and QLoRA adapter packaging
- calibration and validation reports

The architecture should leave room for future mixed-precision and calibration extensions without redesigning core metadata formats.

Worker capability reporting should use typed core capability groups with extensible metadata rather than a flat boolean-only capability map.

## State Models

The architecture should consistently represent:

- server state: booting, ready, degraded, draining, stopped, failed
- worker state: starting, idle, busy, saturated, draining, exited, crash loop
- model state: discovered, loading, warm, pinned, evicting, unloaded, failed
- request phase: queued, prefilling, decoding, tool-wait, checkpointing, completed, aborted, failed

These states drive UI, metrics, retry behavior, and operational decisions.

In addition to lifecycle states, the control plane should expose resource snapshots for workers and server-level aggregates. At minimum these should cover CPU utilization, GPU utilization, memory used, memory total, memory budget, and active Metal memory.

## Observability and Admin

Melix should expose a coherent operational story across the menu bar app and local admin surface.

Required metrics include:

- TTFT by cold, warm, and hot path
- end-to-end latency
- queue delay
- admission latency
- queue backpressure
- prefill and decode token counts
- abort rate
- L1 and L2 hit rate
- dedup ratio
- pinned-prefix hit rate
- snapshot restore rate
- model load and warmup time
- worker memory pressure
- worker and server resource snapshots
- speculative decode acceptance and rollback rate
- cache quantization compression ratio
- HuggingFace transfer timings
- quantization and training job duration

The menu bar app is the most convenient local control surface. A local admin HTTP surface may coexist, but both must reflect the same control-plane truth.

Image generation belongs in dedicated worker families that may wrap a specialized runtime distinct from the text or analysis runtimes. By contrast, backend capabilities such as quantized matrix multiplication and SDPA remain runtime assumptions provided by the selected MLX stack rather than first-class control-plane modules.

## V1 Non-Goals

Melix V1 should explicitly avoid:

- custom compute kernels
- a built-in workflow DAG engine
- shipping tensor payloads through the control plane
- direct UI access to cache databases or worker internals
- depending on a single upstream server wrapper as the architecture boundary

## Recommended Delivery Order

The implementation should proceed in this order:

1. Repository skeleton, schemas, XPC base, worker RPC base, and menu bar shell
2. Single-model text path with streaming and in-memory cache
3. Dedicated Swift text worker for the default text `Generate` hot path
4. EnginePool depth, phase-aware text runtime behavior, queueing, and session or branch state
5. SSD-backed cache, snapshots, restart recovery, and cache inspection
6. Broader API, desktop operations, and model workflows such as embeddings, rerank, desktop panels, HuggingFace sync, and quantization
7. Multimodal families such as vision, OCR, audio, and image flows
8. Packaging, diagnostics, training workflows, and benchmark completeness

This order keeps the architecture aligned with product value: first usable, then durable, then broad.
