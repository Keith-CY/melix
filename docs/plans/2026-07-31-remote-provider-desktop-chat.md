# Remote Provider Desktop Chat Plan

## Goal

Make a configured Remote Provider selectable and usable from the native macOS
Chat surface, with the same direct control-plane route already verified by the
Melix CLI.

## Governing Contracts

- `CONTEXT.md` defines Proxy Parity between local and configured remote Server
  Profiles.
- `docs/plans/2026-04-27-remote-server-direct-target.md` defines Remote Server
  as a direct Chat target and requires secret redaction.
- `docs/runbooks/agent-ui-walkthrough.md` defines the walkthrough and real-App
  verification workflow for material desktop UI changes.

## Current Gap

- Providers already lets the operator add and edit a Remote Provider.
- Chat's provider picker enumerates only local `serverSessions`.
- `RuntimeViewModel.submitChatPrompt` requires a local
  `selectedChatServerSession` and never constructs a
  `ControlPlaneChatRequest.RemoteTarget`.
- The composer and inspector derive readiness and identity only from a local
  server lifecycle.
- The packaged macOS App does not declare an App Transport Security policy for
  operator-configured cleartext endpoints, so an otherwise valid private-network
  `http://` Remote Provider fails in `URLSession` with `NSURLErrorDomain -1022`.

## End-State Architecture

1. Bind each desktop Chat session to a generic provider-target ID, while
   retaining the existing local `serverSessionID` compatibility surface.
2. Resolve the selected Chat provider through the existing unified
   `providerTargets` collection.
3. For local targets, preserve the current lifecycle, model attachment,
   capabilities, and repair behavior.
4. For remote targets, load the API key only at dispatch time, construct a
   transient `ControlPlaneChatRequest.RemoteTarget`, and never copy the raw key
   into Chat state, transcript, logs, or UI labels. Dispatch-time validation
   covers the same fields the composer readiness check treats as required —
   credential, model, provider kind, and endpoint — so a corrupted Server
   Profile fails with the operator-facing Provider message instead of a
   low-level remote-provider error.
5. Present local and remote providers in the existing Chat provider picker.
   Reuse the current Chat layout; do not add a separate remote-chat screen.
6. Treat the Thinking toggle consistently for reasoning-capable remote
   providers: disabling Thinking sends `reasoning_effort = none`; enabling it
   preserves OpenAI-compatible `reasoning_content` as typed reasoning events
   and final reasoning text instead of folding it into assistant content.
   `enable_thinking` is a vendor extension rather than an OpenAI-compatible
   field, so the outbound remote body carries it only as an explicit opt-out
   (`false`), for endpoints that honor the vendor key but ignore
   `reasoning_effort`. It is never sent as `true`, which matches the default of
   every endpoint that understands the key and would otherwise be an unknown
   top-level field for strict OpenAI-compatible endpoints.
7. Give the composer and inspector a provider-neutral presentation so a valid
   remote target is ready without local start, resume, wake, or model-attachment
   actions.
8. Declare local networking at the packaged-App boundary because Remote
   Provider URLs may intentionally target localhost, LAN, or tailnet endpoints
   by IP address. Keep public-hostname ATS protections enabled, keep the
   selected URL explicit in the inspector, and do not silently rewrite
   transport security. Include the required user-facing local-network usage
   description for direct unicast connections.

## Performance Probes And Success Metrics

- Provider selection and request construction remain O(provider count +
  messages).
- Focused state, view, and request-routing tests must pass.
- Changed-line coverage for the touched Swift scope must be at least 95 percent
  before commit.
- The real macOS App must show the configured `LAY2 DeepSeek V4` target in the
  Chat provider picker.
- A prompt submitted through the real UI must produce non-empty assistant text
  with `finish_reason = stop` before the configured 120-second timeout.
- With Thinking enabled, the real App must render a separate non-empty Reasoning
  entry; with Thinking disabled, the same endpoint must render no Reasoning
  entry.
- The packaged `Info.plist` must include the deliberate ATS allowance, and its
  packaging tests must lock that contract.
- Warm UI requests should remain within the previously observed remote CLI
  latency envelope unless direct endpoint probes show a corresponding service
  regression.
- No raw API key may appear in visible state, screenshots, diffs, or logs.

## Delivery Slices

- [x] Create the focused runtime walkthrough and decision note.
- [x] Add failing tests for generic Chat provider binding and remote request
      construction.
- [x] Add failing view tests for local and remote provider picker entries and
      remote-ready composer behavior.
- [x] Implement provider-neutral Chat selection, readiness, identity, and
      dispatch.
- [x] Add packaged-App local-network declaration, privacy usage coverage, and
      an explicit build-time insecure-host allowlist for trusted cleartext
      Remote Providers.
- [x] Run focused Swift tests and changed-line coverage.
- [x] Rebuild and launch the real macOS App with isolated runtime state.
- [x] Select the remote provider and complete a real UI Chat request.
- [x] Record final UI evidence, metrics, and remaining gaps.
- [x] Add a failing remote SSE regression test for `reasoning_content`.
- [x] Preserve remote reasoning deltas through the control-plane Chat stream.
- [x] Re-run focused tests and changed-line coverage.
- [x] Rebuild the local acceptance App and run live Thinking on/off requests
      through its bundled control plane.
- [ ] Capture final native UI Thinking on/off evidence. Computer Use failed to
      start twice during the follow-up acceptance, so no post-fix screenshot is
      recorded as evidence.

## Acceptance Record

- The real native Chat picker exposed `Remote Providers` and
  `LAY2 DeepSeek V4`.
- The real App selected canonical model `deepseek-v4-flash`, sent
  `Reply with exactly MELIX_UI_REMOTE_OK` with Thinking disabled, and displayed
  `MELIX_UI_REMOTE_OK`.
- Evidence:
  `.runtime/evidence/remote-ui-chat.jpeg`.
- The full macOS menu-bar suite passed 882 tests in 25 suites. The final
  changed-line coverage run passed 622 focused tests in four suites.
- Changed-line coverage for the touched Swift Chat scope was 96.08 percent
  (319 of 332 changed executable lines).
- The focused App-bundle and packaging-script regression run passed all
  119 tests after adding the explicit ATS host allowlist and host validation
  edge-case coverage.
- The final packaging smoke run passed all 153 tests and its three packaging
  profiles reported the expected shared identity and isolation receipts.
- Changed-line coverage for the Python packaging scope was 100 percent
  (37 of 37 executable changed lines).

### Dependency And Main Synchronization

- The final task branch is based on `origin/main` at `9ff3fd82a`.
- This slice changes neither dependencies nor protobuf schemas. All SwiftPM
  lockfiles match `origin/main` and are absent from the task diff.
- The two upstream commits incorporated during final synchronization optimize
  integration binary lookup and Hub repository validation. Their surrounding
  changes were inspected and do not alter the Remote Provider Chat path.

### Remote Thinking Follow-up

- The new SSE regression test first failed because
  `RemoteProviderChatStreamEvent` had no `reasoningDelta` case.
- `RemoteProviderClientTests` passed 22 tests after the fix. The combined
  remote-provider and control-plane mapping coverage run passed 23 tests in two
  suites.
- The desktop remote binding, Thinking policy, and reasoning presentation
  regression run passed three tests.
- Control-plane changed-line coverage was 96.49 percent (55 of 57 executable
  changed lines). `ControlPlaneService.swift` was 100 percent (10 of 10);
  `RemoteProviderClient.swift` was 95.74 percent (45 of 47).
- The rebuilt acceptance App reported `status: ok` from its bundled control
  plane. A live request without a reasoning-disabling override returned
  `MELIX_THINKING_ON_OK` with `finish_reason: stop` in approximately 76
  seconds. The same path with `reasoning_effort: none` returned
  `MELIX_THINKING_OFF_OK` with `finish_reason: stop` in approximately three
  seconds. After the final rebuild, another live request returned
  `MELIX_FINAL_THINKING_OK` with `finish_reason: stop` in approximately three
  seconds.
- The native UI automation service failed to start twice. The earlier
  `.runtime/evidence/remote-ui-chat.jpeg` predates this fix and is not claimed
  as post-fix Thinking-rendering evidence.

## Post-Merge Review Follow-Up

Review feedback on the merged slice identified two remaining defects in the
outbound remote path. Both are fixed as follow-up work:

- `OpenAICompatibleRemoteProviderClient` added `enable_thinking` to every
  outbound body whenever the field was non-nil. Desktop Chat always supplies a
  concrete boolean, so every desktop remote request carried the vendor key,
  including on the default Thinking-enabled path. The client now sends it only
  as an explicit `false` opt-out, so the default remote request carries no
  non-OpenAI top-level field.
- `chatRemoteTarget` validated only the credential and the model, while
  `isSelectedChatProviderReady` also requires the provider kind and the
  endpoint. A profile with an empty endpoint reported as ready and failed later
  with `remote provider base_url is invalid`. Both fields are now validated at
  dispatch time with the same Provider-facing wording as the other missing-field
  cases.

## Packaging Security Boundary

ATS on current macOS versions requires an individual host exception for
cleartext IP-address loads. The acceptance App used an exception scoped to the
operator-configured private IPv4 host without recording that host in the
repository. The checked-in packager now exposes repeatable
`--allow-insecure-http-host HOST` arguments, validates exact IPv4 or DNS hosts,
records them in the packaging-target manifest, and emits only corresponding
`NSExceptionDomains` entries. It does not disable ATS globally. General Remote
Providers should use HTTPS, and public hosts should not be allowlisted merely
to avoid deploying TLS. Host normalization is linear in the total input host
length and runs only while building the App bundle; it adds no Chat request-path
work.
