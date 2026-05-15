# Issue 621 Local Serving Hardening Slice

## Goal

Close the current local-server hardening gap for issue #621 by separating public
liveness from authenticated operator diagnostics and by rejecting risky HTTP
request framing before route handlers run.

## Governing Context

Issue #621 tracks local serving and tool-integration trust boundaries. Existing
Melix code already covers the shared gateway auth policy across generation,
compatibility, cache, and session routes, and accepts documented `x-api-key` and
`Authorization: Bearer` credential forms in shared API-key mode.

The immediate gap is the follow-up local-serving hardening slice:

- unauthenticated `/health` must expose liveness only
- authenticated diagnostics must carry route/model readiness
- oversized declared request bodies must return `413` before route handling
- unsupported chunked uploads must return a typed refusal before route handling
- unsafe forwarded prefixes must not be reflected into route or discovery output

## Work Plan

1. Change `GET /health` to a minimal liveness payload.
2. Add authenticated `GET /v1/melix/health` for the existing route/model health
   diagnostics.
3. Move bootstrap HTTP request parsing into the core gateway module so it can be
   unit tested without live sockets.
4. Add parser refusals for oversized `Content-Length`, chunked transfer
   encoding, and unsafe forwarded prefixes.
5. Update runbooks and integration smoke expectations to consume the
   authenticated health diagnostics path when they need route details.

## Verification

```bash
make swift-test
make py-test
make integration-test
swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'HTTPGatewayRequestParserTests|OpenAIHandlerTests|MCPToolCatalogTests|ControlPlaneServiceTests'
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

## Metrics

- Public liveness latency: `operator.health_latency_ms`.
- Authenticated diagnostics latency: `operator.health_diagnostics_latency_ms`.
- Request parser refusals: `http.request_body_rejected_count` and
  `http.forwarded_prefix_rejected_count`.
