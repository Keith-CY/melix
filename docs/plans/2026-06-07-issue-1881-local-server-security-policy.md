# Issue 1881 Local Server Security Policy

## Goal

Harden browser-reachable local Melix HTTP services against Host-header abuse and cross-origin browser requests while preserving same-host server-to-server workflows.

## Best End-State Architecture

Melix should have one shared local-server security policy that every HTTP helper service uses before request routing. The policy should compute a loopback-safe Host allowlist from the effective bind address and explicit operator overrides, default-deny browser CORS unless an origin is explicitly allowlisted, and emit an operator-visible receipt that can be shown in diagnostics without secrets or private paths.

The long-term surface should expose operator controls through server-session configuration and CLI flags such as `--allowed-host` and `--allowed-origin`. Environment variables remain useful for packaged/bootstrap paths, but they should not become a second source of truth for product configuration. Every helper HTTP surface should report the same receipt shape: effective hosts, effective origins, default-deny CORS state, bind host, and rejection counters.

## First Slice

This PR implements the shared policy and wires it into the Swift OpenAI-compatible HTTP gateway, which owns the stable local service surface for `/v1/...`, discovery, and health routes. It intentionally does not migrate every auxiliary helper in the repository in one change.

The slice covers:

- a typed policy helper for Host and Origin admission;
- raw HTTP/1.1 parser rejection for requests that omit `Host`;
- default loopback Host allowlists and default-deny browser Origin handling;
- allowlist overrides from `MELIX_ALLOWED_HOSTS` and `MELIX_ALLOWED_ORIGINS`, with browser origins normalized to scheme, host, and optional port;
- handler-level rejection before auth, rate limits, or route execution;
- exact CORS response headers only for an explicitly allowlisted origin;
- `OPTIONS` preflight support for explicitly allowlisted browser origins before API-key auth;
- a `local_server_security` receipt in `/v1/melix/health`;
- operator runbook updates for Host and browser Origin configuration;
- unit and handler regression tests for host rejection, origin rejection, explicit opt-in, preflight, and server-to-server requests with no `Origin`.

## Performance Probes and Metrics

The policy path runs once per HTTP request and uses small normalized sets built at handler initialization. Success criteria for this slice:

- no request reaches model/auth/routing logic after a Host or Origin rejection;
- raw HTTP/1.1 requests without `Host` fail during parsing before route handling;
- no response emits wildcard `Access-Control-Allow-Origin`;
- explicit Origin opt-in adds only exact `Access-Control-Allow-Origin` and `Vary: Origin`;
- browser preflight uses `OPTIONS` with exact CORS headers and no auth failure;
- diagnostics expose the effective policy without credentials or local paths;
- local test coverage for touched Swift gateway logic stays at or above the repository threshold.

## Verification

Targeted verification:

```bash
HOME="$PWD/.swift-home" \
CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift --filter 'LocalServerSecurityPolicyTests|OpenAIHandlerTests|HTTPGatewayRequestParserTests'
```

Changed-scope coverage:

```bash
python3 scripts/swift_changed_line_coverage.py \
  --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests \
  --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata \
  services/control-plane-swift/Sources/HTTPGateway/OpenAI/LocalServerSecurityPolicy.swift \
  services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift \
  services/control-plane-swift/Sources/HTTPGateway/HTTPGatewayRequestParser.swift \
  services/control-plane-swift/Sources/Bootstrap/main.swift \
  services/control-plane-swift/Tests/HTTPGatewayTests/LocalServerSecurityPolicyTests.swift \
  services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift \
  services/control-plane-swift/Tests/HTTPGatewayTests/HTTPGatewayRequestParserTests.swift
```

Before commit and PR, run the repository pre-commit hook so the full local test gate and scoped performance report are produced by the versioned tooling.
