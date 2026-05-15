# Issue 621 Local Serving And Tool Trust Boundaries

## Goal

Close the remaining trust-boundary gaps for issue #621 by hardening local
serving auth, HTTP request framing, MCP tool discovery, high-risk tool exposure,
rate-limit accounting, and remote media ingress before requests reach worker
execution.

## Governing Context

Issue #621 tracks local serving and tool-integration trust boundaries. The
completed hardening scope must cover:

- unauthenticated `/health` must expose liveness only
- authenticated diagnostics must carry route/model readiness
- oversized declared request bodies must return `413` before route handling
- unsupported chunked uploads must return a typed refusal before route handling
- unsafe forwarded prefixes must not be reflected into route or discovery output
- shared gateway auth must cover generation, compatibility, diagnostics,
  cache, and auth-session routes
- documented compatibility headers in shared API-key mode must share the same
  credential identity for rate-limit accounting
- auth-session revocation must consume a token exactly once, so concurrent or
  repeated sign-out attempts produce one success and then a typed revoked
  session response
- MCP tool configuration discovery must use only explicit operator inputs or
  Melix-owned state, not process current working directory files
- high-risk MCP namespaces must require explicit operator allowlists and expose
  typed refusal receipts
- remote media URLs must pass an admission check before any future fetch or
  worker dispatch path can dereference them

## Work Plan

1. Change `GET /health` to a minimal liveness payload.
2. Add authenticated `GET /v1/melix/health` for the existing route/model health
   diagnostics.
3. Move bootstrap HTTP request parsing into the core gateway module so it can be
   unit tested without live sockets.
4. Add parser refusals for oversized `Content-Length`, chunked transfer
   encoding, and unsafe forwarded prefixes.
5. Add parser refusals for oversized headers and duplicate header names before
   interpreting security-sensitive header values.
6. Enforce the active gateway listener rate limit with a normalized identity
   derived from the accepted API key or session metadata, so `x-api-key` and
   `Authorization: Bearer` for the same configured key share accounting.
7. Make auth-session revocation a single-consumption operation: the first
   revoke succeeds, and repeated/concurrent use of the same token returns a
   typed `revoked_session` failure.
8. Restrict MCP discovery to `MELIX_MCP_CONFIG_PATH` and
   `$MELIX_HOME/config/mcp-tools.json`, and expose a `config-discovery` receipt
   in diagnostics.
9. Keep high-risk MCP namespaces blocked unless
   `MELIX_MCP_HIGH_RISK_ALLOWLIST` names the exact namespace, with requested and
   effective policy fields in snapshots.
10. Add a shared external media URL admission helper for multimodal request
   normalization and image edit URL ingress. Remote media must be HTTPS with a
   public host; local paths and `file:` URLs stay local.
11. Update runbooks and integration smoke expectations to consume the
   authenticated health diagnostics path when they need route details.

## Verification

```bash
make swift-test
make py-test
make integration-test
swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'HTTPGatewayRequestParserTests|OpenAIHandlerTests|MCPToolCatalogTests|MultimodalContractTests|ControlPlaneServiceTests'
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx coverage run --source=scripts,tests -m pytest -q tests/test_m13_api_onboarding_smoke.py tests/test_m9_mcp_smoke.py tests/integration/test_non_text_endpoints.py::test_health_and_cache_endpoints_return_operator_state tests/integration/test_api_onboarding_examples.py::test_api_onboarding_smoke_verifies_the_live_quick_start_examples tests/integration/test_mcp_tool_injection.py::test_responses_endpoint_auto_injects_mcp_tools_from_repo_owned_config
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/m9_mcp_smoke.py --json
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python coverage run --append --source=scripts,tests scripts/phase5_control_plane_metrics.py
git diff --check
```

Full pre-merge commit hook results:

- `make swift-test`: passed.
- `make py-test`: `2593 passed, 14 skipped`.
- `make integration-test`: `113 passed, 1 skipped`.

Post-merge `origin/main` focused results:

- Swift focused coverage tests: `357 tests` passed; changed-line coverage
  `99.20% (497/501)`.
- Python focused coverage tests: `23 passed`; changed-line coverage
  `100.00% (26/26)`.
- MCP smoke: passed with `mcp.configured_tool_count=2`,
  `mcp.refused_tool_count=1`, and `mcp.tool_injection_success_rate=1`.
- Phase 5 metrics smoke: passed with public liveness and authenticated health
  diagnostics metrics recorded.

Code-review follow-up results:

- Swift focused coverage tests: `359 tests` passed after adding header-size and
  duplicate-header refusal coverage.
- Swift changed-line coverage for the parser follow-up:
  `100.00% (111/111)`.

Trust-boundary completion follow-up:

- Swift focused tests for rate-limit identity, image URL admission, MCP
  discovery, multimodal URL receipts, and MCP snapshot discovery receipts
  passed.
- Auth-session revocation tests passed for HTTP duplicate DELETE handling and
  store-level concurrent revoke single-consumption semantics.

## Metrics

- Public liveness latency: `operator.health_latency_ms`.
- Authenticated diagnostics latency: `operator.health_diagnostics_latency_ms`.
- Request parser refusals: `http.request_header_rejected_count`,
  `http.request_body_rejected_count`, and `http.forwarded_prefix_rejected_count`.
- Rate-limit admission: `gateway.rate_limit_per_minute`,
  `gateway.rate_limit_remaining`, `gateway.rate_limit_last_admission`, and
  `gateway.rate_limited_request_count`.
- Auth-session revocation: `persistent_session.sign_out_latency_ms` plus active,
  remembered, expired, and restore-success session metrics.
- MCP policy: `mcp.configured_tool_count`, `mcp.refused_tool_count`,
  `mcp.disabled_tool_source_count`, `mcp.tool_injection_count`, and
  `mcp.tool_injection_success_rate`.
- External media URL admission:
  `external_media.url_admission_count`,
  `external_media.remote_url_admission_count`,
  `external_media.local_url_admission_count`,
  `external_media.url_refusal_count`, and
  `external_media.refusal.<reason>`.
