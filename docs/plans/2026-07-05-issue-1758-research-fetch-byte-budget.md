# Issue 1758 Research Fetch Byte Budget Receipts

## Goal

Add a narrow research/source fetch budget contract for deep-research presets so
URL fetches can be capped, receipted, and cached by effective byte budget before
model-visible truncation happens.

## Context

Issue #1758 tracks operator-facing deep-research presets with scoped tools,
citations, and evidence bundles. The 2026-06-16 watch note identifies a smaller
executable slice: every URL fetch used by future research/web tools must expose
byte-budget receipts, soft truncation, hard pre-buffer refusal, per-call override
clamping, and cache-key separation between truncated and full fetches.

This slice intentionally creates the productization helper and deterministic
mock streaming fixture first. It does not add a full research agent, external
browser integration, or UI.

## Scope

In scope:

- Define a stable research fetch budget receipt schema.
- Resolve requested, default, and hard maximum byte budgets deterministically.
- Soft-truncate text responses at the effective byte budget and attach a
  model-visible partial-content notice.
- Refuse declared bodies above the hard maximum before buffering.
- Treat truncated binary/PDF responses as budget errors rather than parseable
  evidence.
- Include the effective byte budget and truncation state in cache keys so
  partial and full fetches cannot collide.
- Add deterministic tests with a mock streaming source.
- Document the receipt fields and interpretation rules.

Out of scope:

- Real network I/O, DNS, redirects, or SSRF policy; #2188 owns fetch safety
  receipts.
- Full deep-research preset execution, source citation maps, or UI flows.
- Parsing PDF or binary payloads.
- Persisted cache storage.

## Receipt Contract

Research fetch budget receipts use schema version
`melix.research_fetch_budget_receipt.v1` and include:

| Field | Meaning |
| --- | --- |
| `source_id` | Stable caller-provided source identifier. |
| `source_url_hash` | SHA-256 hash of the normalized URL. |
| `requested_max_bytes` | Optional per-call byte budget requested by the caller. |
| `default_max_bytes` | Preset default byte budget used when no override exists. |
| `effective_max_bytes` | Budget after clamping to the hard maximum. |
| `hard_max_bytes` | Absolute maximum allowed before buffering. |
| `fetched_bytes` | Bytes consumed from the stream before completion/refusal. |
| `declared_total_bytes` | Response-declared total bytes when available. |
| `truncated` | Whether the returned content was truncated. |
| `status` | `ok`, `truncated`, or `blocked`. |
| `blocked_reason` | Typed reason when no model-visible content is returned. |
| `content_type` | Normalized content type such as `text/html` or `application/pdf`. |
| `partial_content_notice` | Model-visible notice prepended to truncated text content. |
| `refetch_hint` | Operator-facing hint for retrieving the full source. |
| `cache_key` | Stable key that includes URL, content type, effective budget, and truncation state. |
| `raw_url_included` | Always false; receipts must not contain raw URLs. |

## Implementation Plan

### Task 1: Red Tests

Files:

- Create: `services/mlx-worker-python/tests/test_research_fetch_budget.py`

Steps:

1. Add a mock streaming source helper that yields byte chunks and optional
   declared total bytes.
2. Add failing tests for soft text truncation:
   - effective budget is applied before model-visible output.
   - receipt records requested/default/effective bytes, fetched bytes,
     declared total bytes, `truncated=true`, and a non-empty
     `partial_content_notice`.
   - raw URLs and query parameters do not appear in the serialized receipt.
3. Add failing tests for hard pre-buffer refusal:
   - declared total bytes above `hard_max_bytes` return blocked status before
     consuming stream chunks.
   - `blocked_reason` is `declared_total_exceeds_hard_max`.
4. Add failing tests for per-call override clamping:
   - requested values above the hard max resolve to the hard max.
   - requested values below the hard max are honored.
5. Add failing tests for cache-key separation:
   - a truncated fetch and a full fetch of the same URL produce different keys.
   - two full fetches with the same effective budget produce the same key.
6. Add failing tests for binary/PDF truncation refusal:
   - truncated `application/pdf` or `application/octet-stream` content returns
     blocked status with `blocked_reason=binary_truncation_not_parseable`.

Verification command:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 \
  uv run --project services/mlx-worker-python --extra mlx \
  pytest services/mlx-worker-python/tests/test_research_fetch_budget.py -q
```

Expected red result: import failure for
`worker.productization.research_fetch_budget`.

### Task 2: Research Fetch Budget Helper

Files:

- Create: `services/mlx-worker-python/worker/productization/research_fetch_budget.py`

Steps:

1. Add dataclasses:
   - `ResearchFetchBudgetPolicy`
   - `ResearchFetchBudgetReceipt`
   - `ResearchFetchResult`
2. Add `fetch_stream_with_budget(...)` that consumes an iterable of byte chunks
   and returns a `ResearchFetchResult`.
3. Resolve byte budgets with these rules:
   - default policy values are positive integers.
   - absent or invalid requested values use the default.
   - requested values above the hard max clamp to the hard max.
4. Refuse declared totals above the hard max before reading chunks.
5. Soft-truncate text content at the effective byte budget, decode with UTF-8
   replacement, and prepend a concise partial-content notice.
6. Block truncated binary/PDF content instead of returning parseable evidence.
7. Generate a stable cache key from normalized URL hash, content type,
   effective max bytes, declared total bytes, and truncation state.
8. Ensure `to_dict()` never includes raw URLs or raw content.

### Task 3: Documentation

Files:

- Modify: `docs/runbooks/serving-diagnostics-evidence.md`

Steps:

1. Add a short "Research Fetch Budget Receipts" section.
2. Define when `ok`, `truncated`, and `blocked` receipts are expected.
3. Document that this helper performs no network safety checks and must be
   paired with #2188 fetch policy admission before real URL dereferencing.
4. Document that debug/evidence bundles may include receipts but not raw URLs,
   credentials, or raw truncated query strings.

### Task 4: Verification And PR Evidence

Steps:

1. Run focused tests for the new helper.
2. Run changed-scope coverage for the new module and tests.
3. Run `git diff --check`.
4. Run the repo pre-commit hook through `git commit`.
5. Prepare PR evidence with the exact template headings.
6. Open a PR for #1758 and wait for CI plus PR-scoped performance report.
7. Merge only after all checks pass, the performance report has zero
   regressions, the branch is current with `origin/main`, and review threads are
   resolved.

## Metrics

The changed path is a pure byte-budget helper over caller-provided chunks. It
does not perform network I/O, model inference, PDF parsing, or cache persistence.
Success metrics are deterministic receipt construction, bounded bytes consumed,
and stable cache-key separation in focused tests.
