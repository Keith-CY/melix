# Remote Provider Generation Control Parity Plan

## Goal

Make direct Remote Server Chat preserve the request-level generation controls
that Melix already exposes on `ControlPlaneChatRequest`, so an
OpenAI-compatible reasoning model can be bounded or have reasoning disabled
without bypassing Melix.

## Governing Contracts

- `CONTEXT.md` defines OpenAI Compatibility Conformance to include per-request
  sampling-field passthrough.
- `CONTEXT.md` defines Proxy Parity as equivalent request translation and
  response shape between local and configured remote Server Profiles.
- `docs/plans/2026-04-27-remote-server-direct-target.md` defines Remote Server
  as a direct Chat target.

## Reproduction Evidence

The operator-configured private IPv4 OpenAI-compatible endpoint used for
acceptance advertises `reasoning_effort` and `max_tokens`. Its host is omitted
from the repository so task-specific network addressing is not published.

- A Melix `remote-server test` request omitted both controls and timed out after
  the configured 120 seconds.
- The equivalent direct request with `reasoning_effort: "none"` and
  `max_tokens: 128` returned `OK.` with `finish_reason: "stop"` in 1.7 seconds.
- The current `ControlPlaneService.startRemoteChat` builds
  `RemoteProviderChatRequest` without copying the generation controls already
  present on `ControlPlaneChatRequest`.

## Architecture

Keep the fix at the existing Swift control-plane remote-provider boundary:

1. Extend `RemoteProviderChatRequest` with optional request-level controls.
2. Copy those controls from `ControlPlaneChatRequest` in
   `ControlPlaneService.startRemoteChat`.
3. Add only non-empty or positive OpenAI-compatible fields to the outbound
   JSON, preserving compatibility for providers that reject unknown fields.
4. Expose the same controls on `melix chat run` and
   `melix remote-server test` so the CLI can produce operator evidence.

This slice does not change protobuf schemas, Remote Server persistence, provider
defaults, or desktop UI controls.

## Performance Probes And Success Metrics

The changed path performs a bounded number of optional-field checks while
building one outbound JSON object.

- Focused remote-provider and CLI parser tests must pass.
- Changed-line coverage for the touched Swift scope must be at least 95 percent
  before commit.
- A live Melix CLI request using `reasoning_effort=none` must complete within
  the configured 120-second timeout and return non-empty assistant text.
- No raw credential may appear in CLI JSON, debug output, or committed files.
- Metrics report: request construction remains O(messages + optional fields);
  no benchmark is required because the change adds no loop, I/O, or hot-path
  allocation proportional to model output.

## Tasks

- [x] Add a failing request-body test for remote generation-control passthrough.
- [x] Add failing CLI parser tests for `--reasoning-effort`,
      `--max-tokens`, `--temperature`, and `--top-p`.
- [x] Implement conditional outbound-field construction and control-plane
      forwarding.
- [x] Implement CLI option parsing and command execution forwarding.
- [x] Run focused Swift tests and changed-line coverage.
- [x] Re-run the live Remote Server test and a real Chat request through Melix.
- [x] Record final verification and metrics in this plan.

## Verification And Metrics

Verified on 2026-07-31 from the isolated task worktree and isolated
`MELIX_HOME`.

- `GET /v1/models` returned HTTP 200 and advertised
  `deepseek-v4-flash` and `deepseek-v4-pro`.
- The focused root Swift test run passed 3 tests covering CLI parsing, command
  encoding, and runner forwarding.
- The focused control-plane Swift test run passed 2 tests covering
  control-plane forwarding and outbound OpenAI-compatible JSON construction.
- The final root CLI changed-line coverage run passed 365 tests in three suites
  and covered 100 percent (81 of 81) of the changed executable lines.
- The final control-plane changed-line coverage run passed three tests in two
  suites and covered 96.49 percent (55 of 57) of the changed executable lines.
- `melix remote-server test` returned `ok: true` and
  `finish_reason: stop` within the configured 120-second timeout.
- A real `melix chat run` returned non-empty assistant text with
  `finish_reason: stop` in 2.4 seconds.
- A second `melix chat run` returned the exact sentinel
  `MELIX_REMOTE_OK` with `finish_reason: stop` in 1.9 seconds.
- Request construction remains O(messages + optional fields). No dedicated
  microbenchmark was added because the change adds a fixed five conditional
  checks and no output-proportional work.

The live configuration uses a non-secret placeholder API-key value because the
current Remote Server store requires a non-empty value while this endpoint does
not require authentication. Desktop UI controls are outside this slice; the
verified operator surface is the Melix CLI Remote Server direct target.
