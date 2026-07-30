# Issue 2607 KV-Quant Prefix Cache Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let active-KV-quantized text sessions use Melix prefix KV reuse when the stored snapshot and incoming request declare the same active KV quantization profile, while preserving precise fallback receipts for missing or mismatched profiles.

**Architecture:** Reuse remains owned by the Python text worker `PrefixBlockStore`; active-KV entries become profile-keyed instead of blanket-excluded. The worker engine forwards `AccelerationPolicy.active_kv_quant_profile` into runtime ext metadata, and both hot and opt-in cold tiers persist that profile as part of entry identity.

**Tech Stack:** Python 3.12, `pytest`, existing MLX worker prefix-cache tests, generated worker protobufs already present.

---

## Governing Context

- Issue: `https://github.com/Keith-CY/melix/issues/2607`
- Runbook: `docs/runbooks/text-prefix-cache-tiering.md`
- Decision: `docs/decisions/2026-03-28-product-scope-and-runtime-priorities.md`
- Baseline before edits:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_prefix_block_store.py services/mlx-worker-python/tests/test_prefix_cache_cold_tier.py services/mlx-worker-python/tests/test_text_session_prompt_cache.py`
  -> `78 passed in 1.06s`

## File Structure

- Modify `services/mlx-worker-python/worker/runtime/prefix_block_store.py`
  - Add `kv_quant_profile` metadata to hot entries and cold sidecars.
  - Replace active-KV blanket exclusion with profile-keyed compatibility.
  - Emit `kv_quant_profile_missing` and `kv_quant_profile_mismatch` fallback reasons.
- Modify `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
  - Parse `_melix.active_kv_quant_profile` into `_SessionPrefixCacheContext`.
  - Pass the profile into `find_lcp()` and `put()` from standard and native-MTP text paths.
- Modify `services/mlx-worker-python/worker/engine/engine_core.py`
  - Forward `execution.acceleration.active_kv_quant_profile` into `_melix.active_kv_quant_profile`.
- Modify tests:
  - `services/mlx-worker-python/tests/test_prefix_block_store.py`
  - `services/mlx-worker-python/tests/test_prefix_cache_cold_tier.py`
  - `services/mlx-worker-python/tests/test_generate_stream.py`
  - `services/mlx-worker-python/tests/test_text_session_prompt_cache.py`
- Modify docs:
  - `docs/runbooks/text-prefix-cache-tiering.md`

## Task 1: Hot-Tier Profile-Keyed Active KV Matching

**Files:**
- Modify: `services/mlx-worker-python/tests/test_prefix_block_store.py`
- Modify: `services/mlx-worker-python/worker/runtime/prefix_block_store.py`

- [x] **Step 1: Write the failing hot-tier test**

Add this test near the existing `find_lcp — exclusion gates` section:

```python
def test_find_lcp_active_kv_hits_when_quant_profiles_match() -> None:
    store = PrefixBlockStore()
    store.put(
        session_id="s1",
        token_ids=[1, 2, 3, 4, 5, 6, 7, 8],
        cache_snapshot=_make_snapshot(),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        total_bytes=1024,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )

    result = store.find_lcp(
        [1, 2, 3, 4, 5, 6, 7, 8],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )

    assert result.mode == "exact"
    assert result.recovered_prefix_tokens == 8
    assert result.fallback_reason == ""
    assert result.tier == "hot"
    assert result.entry is not None
    store.release(result.entry)
```

- [x] **Step 2: Run the hot-tier RED test**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_prefix_block_store.py::test_find_lcp_active_kv_hits_when_quant_profiles_match
```

Expected: fail because `PrefixBlockStore.put()` and `find_lcp()` do not accept `kv_quant_profile` yet, or because the active-KV blanket exclusion still prevents the match.

- [x] **Step 3: Implement minimal hot-tier metadata and compatibility**

Add `kv_quant_profile: str = ""` to `_BlockEntry`; add optional `kv_quant_profile` parameters to `PrefixBlockStore.put()` and `find_lcp()`. For active-KV requests, require a non-empty normalized profile; for active-KV entries, match only entries with the same normalized profile. Non-active requests must not reuse active-KV entries.

- [x] **Step 4: Run the hot-tier GREEN test**

Run the same single-test command. Expected: pass.

- [x] **Step 5: Add mismatch and missing-profile tests**

Add tests proving:

```python
def test_find_lcp_active_kv_profile_mismatch_returns_precise_reason() -> None:
    store = PrefixBlockStore()
    store.put(
        session_id="s1",
        token_ids=[1, 2, 3, 4, 5, 6, 7, 8],
        cache_snapshot=_make_snapshot(),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        total_bytes=1024,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )
    result = store.find_lcp(
        [1, 2, 3, 4, 5, 6, 7, 8],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q8:g64",
    )
    assert result.mode == "none"
    assert result.fallback_reason == "kv_quant_profile_mismatch"

def test_find_lcp_active_kv_missing_profile_returns_precise_reason() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8])
    result = store.find_lcp(
        [1, 2, 3, 4, 5, 6, 7, 8],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
    )
    assert result.mode == "none"
    assert result.fallback_reason == "kv_quant_profile_missing"
```

- [x] **Step 6: Run prefix store tests**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_prefix_block_store.py
```

Expected: all pass.

## Task 2: Cold-Tier Active KV Persistence

**Files:**
- Modify: `services/mlx-worker-python/tests/test_prefix_cache_cold_tier.py`
- Modify: `services/mlx-worker-python/worker/runtime/prefix_block_store.py`

- [x] **Step 1: Write the failing cold-tier tests**

Add tests proving active-KV cold entries are accepted only with a profile and match only identical profiles:

```python
def test_cold_store_allows_active_kv_when_quant_profile_present(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    ok = cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot(),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )
    assert ok
    assert cold.entry_count() == 1

def test_cold_match_isolates_active_kv_quant_profiles(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    assert cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )
    mismatch, mismatch_len = cold.match(
        [1, 2, 3, 4],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q8:g64",
    )
    assert mismatch is None
    assert mismatch_len == 0
    match, recovered = cold.match(
        [1, 2, 3, 4],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )
    assert match is not None
    assert recovered == 4
```

- [x] **Step 2: Run the cold-tier RED tests**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_prefix_cache_cold_tier.py::test_cold_store_allows_active_kv_when_quant_profile_present services/mlx-worker-python/tests/test_prefix_cache_cold_tier.py::test_cold_match_isolates_active_kv_quant_profiles
```

Expected: fail because cold store rejects active-KV entries and lacks profile metadata.

- [x] **Step 3: Implement cold metadata and sidecar persistence**

Add `kv_quant_profile` to `ColdEntryMeta`, `ColdPrefixStore.store()`, `match()`, sidecar JSON write, and sidecar load. Update demotion and promotion to carry the profile.

- [x] **Step 4: Run cold-tier tests**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_prefix_cache_cold_tier.py
```

Expected: all pass.

## Task 3: Runtime/Engine Profile Propagation

**Files:**
- Modify: `services/mlx-worker-python/tests/test_generate_stream.py`
- Modify: `services/mlx-worker-python/tests/test_text_session_prompt_cache.py`
- Modify: `services/mlx-worker-python/worker/engine/engine_core.py`
- Modify: `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`

- [x] **Step 1: Write the failing engine propagation test**

Extend the existing session-routing test in `test_generate_stream.py` so a request with:

```python
request.execution.acceleration.mode = common_pb2.ACCELERATION_MODE_ACTIVE_KV_QUANTIZED
request.execution.acceleration.active_kv_quant_profile = "q4:g64"
```

expects runtime ext to contain:

```python
"_melix.active_kv_quant_profile": "q4:g64"
```

- [x] **Step 2: Run the engine RED test**

Run the single test. Expected: fail because `EngineCore.generate()` does not forward the field.

- [x] **Step 3: Forward and parse the profile**

In `EngineCore.generate()`, when `execution.acceleration.active_kv_quant_profile` is non-empty, set `_routing_ext["_melix.active_kv_quant_profile"]`. In `_SessionPrefixCacheContext`, add `active_kv_quant_profile`; parse `_melix.active_kv_quant_profile`; pass it to store `find_lcp()` and `put()` calls in both standard and native-MTP text paths.

- [x] **Step 4: Add runtime reuse and parity tests**

Add standard text session tests proving an active-KV request with matching profile stores and warm-hits on the second call; a mismatched profile returns `kv_quant_profile_mismatch`; and a deterministic greedy continuation from an active-KV warm-hit matches the same prompt decoded through cold prefill.

- [x] **Step 5: Run runtime tests**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_generate_stream.py services/mlx-worker-python/tests/test_text_session_prompt_cache.py
```

Expected: all pass.

## Task 4: Docs, Coverage, Performance, PR

**Files:**
- Modify: `docs/runbooks/text-prefix-cache-tiering.md`
- Modify: `.runtime/pr-bodies/issue-2607-kv-quant-prefix-cache.md`

- [x] **Step 1: Update runbook**

Replace the current boundary saying active-KV-quantized sessions are excluded with the new rule: active-KV-quantized sessions are eligible only when a stable active KV quant profile is present and matches exactly; otherwise receipts use `kv_quant_profile_missing` or `kv_quant_profile_mismatch`.

- [x] **Step 2: Run focused verification**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_prefix_block_store.py services/mlx-worker-python/tests/test_prefix_cache_cold_tier.py services/mlx-worker-python/tests/test_text_session_prompt_cache.py services/mlx-worker-python/tests/test_generate_stream.py services/mlx-worker-python/tests/test_mlx_backend.py
```

Result after the cold-tier mismatch receipt fix: `208 passed, 2 warnings in 2.72s`; warnings are existing MLX/SWIG deprecation warnings from `test_native_mtp_text_patch_adds_qwen35_methods`.

- [x] **Step 3: Run changed-line coverage**

Run coverage over the focused test set and require at least 95% changed-line coverage.

Result after adding active-KV parity, occupancy, and cold-tier mismatch probes: `TOTAL 98.10% 206/210`; production changed lines remain above the 95% gate (`prefix_block_store.py` 98.11% 52/53, `mlx_text_runtime.py` 1/1, `engine_core.py` 3/3). The hot-cache occupancy probe proves the same 2048-byte budget retains 2 fp16-shaped sessions, 4 q8-shaped sessions, and 8 q4-shaped sessions.

- [x] **Step 4: Run local gates and scoped performance**

Run `make swift-test`, `make py-test`, `make integration-test`, then the repository scoped performance report for files changed against `origin/main`. Any regression is blocking unless proven outside scope.

Results:

- `make swift-test` passed: protocol package, text worker package (`245 tests`), control-plane core groups (`533 tests`), control-plane worker clients (`127 tests`), and macOS menubar package (`834 tests`) completed successfully.
- `make py-test` passed: `4828 passed, 14 skipped, 2 warnings in 243.62s`.
- `make integration-test` passed: `123 passed, 1 skipped in 712.47s`.
- Scoped performance report passed after the final cold-tier mismatch receipt fix: `Status: ok`, `Selected probes: 3`, `Regressions: 0`, `Verification failures: 0`; report path `.runtime/pre-commit-performance/20260708-213317-02f93b58/report/report.md`.

- [ ] **Step 5: Open PR and carry it to merge**

Validate PR evidence with `python3 scripts/validate_pr_evidence.py --body-file .runtime/pr-bodies/issue-2607-kv-quant-prefix-cache.md`, open the PR, wait for GitHub CI and `pr-scoped-performance` to pass with zero regressions/verification failures, resolve review threads, re-check `origin/main` ancestry, squash merge, then comment on/close issue #2607 with the merged PR evidence.

## Self-Review

- Spec coverage: hot reuse, cold reuse, profile isolation, runtime propagation, receipts/docs, verification are represented.
- Placeholder scan: this plan uses concrete file paths, test names, commands, and complete code snippets.
- Type consistency: the plan uses `kv_quant_profile` for internal Python store metadata and `_melix.active_kv_quant_profile` for runtime ext to match protobuf field naming.
