# Issue 1881 Local Server Security Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote local Host and browser CORS allowlists from environment-only overrides to durable server-session and CLI controls for the OpenAI-compatible local gateway.

**Architecture:** Extend the control-plane protocol with `allowed_hosts` and `allowed_origins` on gateway config apply and listener summaries, persist normalized values in the Swift gateway config store, and include them in the runtime binding consumed by the OpenAI handler. Add CLI `--allowed-host` and `--allowed-origin` flags to server session create/update and server start so operator intent is stored before the gateway starts. Keep `MELIX_ALLOWED_HOSTS` and `MELIX_ALLOWED_ORIGINS` as bootstrap defaults, not a second long-term configuration surface.

**Tech Stack:** Swift control plane, Swift CLI, Swift protobuf generated artifacts, repository Markdown runbooks.

---

## Scope

This slice completes the operator-control part of issue #1881 for the Swift OpenAI-compatible gateway. It does not add visible macOS menu-bar controls, and it does not migrate additional helper HTTP servers. Desktop callers must still round-trip existing allowlists so a UI save does not erase CLI-configured security policy.

## Files

- Modify `packages/protocol/schema/controlplane/v1/control_plane.proto` to add gateway allowlist fields.
- Regenerate `packages/protocol/descriptors/melix.pb`, `packages/protocol/python/controlplane/v1/control_plane_pb2.py`, and `packages/protocol/swift/controlplane/v1/control_plane.pb.swift` with `make proto`.
- Modify `services/control-plane-swift/Sources/HTTPGateway/OpenAI/LocalServerSecurityPolicy.swift` to accept explicit allowlists in addition to environment defaults.
- Modify `services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayConfigStore.swift` to persist, summarize, and bootstrap gateway allowlists.
- Modify `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift` to build the local-server security policy from the gateway runtime binding.
- Modify `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift` and related service tests so gateway apply requests carry allowlists.
- Modify `Sources/MelixCLICore/MelixCLI.swift`, `Sources/MelixCLICore/MelixCLICommandCodec.swift`, and CLI tests so `server start`, `server session create`, and `server session update` accept repeated `--allowed-host` and `--allowed-origin`.
- Modify `apps/macos-menubar` XPC callers and test doubles only enough to preserve existing allowlists through gateway apply calls.
- Modify `docs/runbooks/shared-access.md` to document the preferred CLI/session controls.

## Metrics And Success Targets

- `LocalServerSecurityPolicy` still uses precomputed `Set` membership for request-path Host and Origin decisions.
- No added request-time parsing of CLI or persisted JSON.
- The scoped changed-line coverage report for touched Swift files must be at least 95 percent before commit.
- The hosted PR performance report must show `Status ok` with zero regressions before merge.

## Tasks

### Task 1: Gateway Store Contract

- [x] Add failing tests in `services/control-plane-swift/Tests/ControlPlaneTests/GatewayConfigStoreTests.swift` proving `ApplyGatewayConfig.allowedHosts` and `allowedOrigins` persist, de-duplicate, appear in `GatewayListenerConfigSummary`, and flow into `GatewayRuntimeBinding`.
- [x] Run:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter GatewayConfigStoreTests
```

Expected RED: compile or assertion failure because the protocol and store do not expose allowlist fields yet.

- [x] Add protocol fields, regenerate with `make proto`, and implement minimal store/runtime binding support.
- [x] Re-run the same command and confirm the new tests pass.

### Task 2: Gateway Enforcement Contract

- [x] Add failing tests in `services/control-plane-swift/Tests/HTTPGatewayTests/LocalServerSecurityPolicyTests.swift` or `OpenAIHandlerTests.swift` proving an explicit host and origin from the runtime binding are accepted without environment variables, while non-matching origins still receive no wildcard CORS exposure.
- [x] Run:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'LocalServerSecurityPolicyTests|OpenAIHandlerTests'
```

Expected RED: explicit binding allowlists are ignored.

- [x] Update `LocalServerSecurityPolicy` and `OpenAIHandler` to consume explicit lists from `GatewayRuntimeBinding`.
- [x] Re-run the same command and confirm the new tests pass.

### Task 3: CLI And Session Contract

- [x] Add failing tests in `tests/MelixCLITests/MelixCLIParserTests.swift` and `tests/MelixCLITests/MelixCLIRunnerTests.swift` proving repeated `--allowed-host` and `--allowed-origin` flags parse for `server start`, `server session create`, and `server session update`, persist on session state, and are sent to `applyServerSessionGatewayConfig`.
- [x] Run:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'
```

Expected RED: the flags are unknown or the captured gateway apply call has empty allowlists.

- [x] Update CLI option structs, parser multi-value options, session state, command codec, and runner apply logic.
- [x] Re-run the same command and confirm the new tests pass.

### Task 4: XPC And Desktop Pass-Through

- [x] Add failing tests in `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift` or existing XPC request tests proving the client request builder writes `allowedHosts` and `allowedOrigins`.
- [x] Run:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter ControlPlaneXPCClientTests
```

Expected RED: generated requests omit the new repeated fields.

- [x] Update XPC client protocol signatures, request construction, macOS menu-bar callers, and test doubles to pass through existing allowlists.
- [x] Re-run the same command and affected menu-bar tests.

### Task 5: Documentation And Evidence

- [x] Update `docs/runbooks/shared-access.md` with examples using `melix server session update --allowed-host ... --allowed-origin ...` and `melix server start ... --allowed-host ... --allowed-origin ...`.
- [x] Run focused verification:

```bash
make proto
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'GatewayConfigStoreTests|LocalServerSecurityPolicyTests|OpenAIHandlerTests|ControlPlaneXPCClientTests'
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'
```

- [x] Run coverage for the changed Swift scope and record the measured result.
- [x] Run the versioned pre-commit hook with the repository-local cache and record the metrics report path:
  `.runtime/pre-commit-performance/20260607-063659-6998a854/report/report.md`.
- [ ] Open a PR with the required evidence headings from `.github/pull_request_template.md`.
- [ ] Monitor review threads, CI, and the hosted performance report. Merge only after the branch is current with `origin/main`, all checks are green, all review threads are resolved, and the performance report has zero regressions.
