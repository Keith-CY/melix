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
swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests|HTTPGatewayRequestParserTests'
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest -q tests/integration/test_non_text_endpoints.py::test_health_and_cache_endpoints_return_operator_state tests/test_m13_api_onboarding_smoke.py
git diff --check
```

## Metrics

- Public liveness latency: `operator.health_latency_ms`.
- Authenticated diagnostics latency: `operator.health_diagnostics_latency_ms`.
- Request parser refusals: `http.request_body_rejected_count` and
  `http.forwarded_prefix_rejected_count`.
