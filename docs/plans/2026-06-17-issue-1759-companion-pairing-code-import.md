# Issue 1759 Companion Pairing Code Import

## Goal

Let the browser companion status shell import the desktop-generated
`melix-companion:` pairing code or JSON bundle so a trusted local device can
activate status refresh without manually extracting the raw token.

## Best End-State Architecture

The desktop app remains the only issuer of companion read-only tokens. The
gateway serves a static browser shell that can decode an operator-provided
pairing transfer payload locally in the browser, validate that it is a
`melix.companion.pairing.bundle.v1` payload, store only the bearer token in the
existing browser-local storage key, and continue to fetch the existing
companion status endpoint through `x-melix-session`.

The browser import path must not add a gateway mutation route, server-side token
persistence, camera access, or external JavaScript dependency. QR remains a
desktop-rendered transfer medium; this slice makes the transferred code usable
by the browser shell once pasted or scanned by a trusted device tool.

## Slice Boundary

Included:

- Add a pairing import input to `GET /v1/melix/companion`.
- Accept either raw JSON bundle text or compact `melix-companion:` code text.
- Decode URL-safe base64 pairing codes in the browser with no external assets.
- Validate `schema_version = melix.companion.pairing.bundle.v1`.
- Require a non-empty `token` field before storing the token.
- Prefer bundle `status_url` only when it is same-origin; otherwise keep the
  existing relative `/v1/melix/companion/status` status path.
- Update the runbook to describe pasted QR/code or JSON bundle import.

Excluded:

- Camera scanning in the browser.
- Installable PWA metadata or icons.
- Live refresh/push updates.
- Server-side import or token persistence.
- Mutating companion controls.

## Performance Probes and Metrics

- Runtime metric remains `companion.mobile_page_served_count`; this slice does
  not add request-time work to the gateway beyond serving the static page.
- Measurement point: static HTML response size and scoped performance report.
- Success metric: PR-scoped performance report must remain `Status: ok` with
  zero regressions and no selected heavy probes.

## Implementation Plan

1. Add failing gateway test assertions to
   `OpenAIHandlerTests.companionMobileStatusPageServesReadOnlyShellForCompanionTokens`
   proving the static shell contains:
   - an import field labelled for pairing code or JSON bundle;
   - the `melix-companion:` prefix;
   - URL-safe base64 decode logic;
   - `melix.companion.pairing.bundle.v1` schema validation;
   - token extraction and localStorage persistence;
   - same-origin status URL guard.
2. Update the static HTML shell in `OpenAIHandler.swift` with an import panel,
   local decode/parse helpers, same-origin status path handling, and messages
   for invalid/valid imports.
3. Update `docs/runbooks/persistent-sessions.md` so the browser companion page
   flow starts from pasted pairing code or JSON bundle import and still calls
   out token secrecy.
4. Run focused control-plane tests, changed-line coverage for the touched Swift
   files, and a scoped performance report.

## Verification

Focused Swift:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" xcrun swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/companionMobileStatusPageServesReadOnlyShellForCompanionTokens'
```

Changed-line coverage:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" xcrun swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'OpenAIHandlerTests/companionMobileStatusPageServesReadOnlyShellForCompanionTokens'
uv run --python 3.12 python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift
```

Scoped performance:

```bash
UV_PYTHON=3.12 uv run --frozen --project services/mlx-worker-python --extra mlx python - <<'PY'
from pathlib import Path
from scripts.pre_commit_gate import run_performance_report
changed_files = [
    'docs/plans/2026-06-17-issue-1759-companion-pairing-code-import.md',
    'docs/runbooks/persistent-sessions.md',
    'services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift',
    'services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift',
]
outcome = run_performance_report(Path.cwd(), changed_files, base_ref='origin/main')
print(f'PERF_STATUS={outcome.status}')
print(f'PERF_REPORT_DIR={outcome.report_dir}')
print(f'PERF_SELECTED_PROBES={outcome.selected_probe_count}')
raise SystemExit(0 if outcome.status == 'ok' else 1)
PY
```

## Deferred Work

- Browser camera QR scanning.
- Installable PWA metadata and icon assets.
- Live refresh/push updates.
