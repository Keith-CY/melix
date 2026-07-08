# Issue #2599 Standard Prefix KV Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `PrefixBlockStore` session prefix KV reuse into the standard Python text generation path, not only the native-MTP batch path.

**Architecture:** Keep `PrefixBlockStore` as the worker-local source of cache truth. Extract session cache request parsing into a shared helper, explicitly prefill prompt tokens into a `prompt_cache` before standard `stream_generate`, and pass only the last/suffix token prompt with the restored cache. Store a prompt-only cache snapshot before generation mutates the cache with completion tokens.

**Tech Stack:** Python 3.12, `mlx-lm` `stream_generate(prompt_cache=...)`, `pytest`, existing PR-scoped performance infrastructure.

---

## Context

- Issue: <https://github.com/Keith-CY/melix/issues/2599>
- Existing store: `services/mlx-worker-python/worker/runtime/prefix_block_store.py`
- Existing native-MTP integration: `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
- Existing parser metrics bridge: `services/mlx-worker-python/worker/engine/engine_core.py`
- Existing tests: `services/mlx-worker-python/tests/test_mlx_backend.py`, `services/mlx-worker-python/tests/test_prefix_block_store.py`, `services/mlx-worker-python/tests/test_work_saved_cache_counters.py`

Local `mlx-lm` inspection confirms:

- `stream_generate` accepts `prompt: str | mx.array | list[int]`.
- `stream_generate` forwards `prompt_cache` to `generate_step`.
- `generate_step(prompt_cache=...)` mutates the prompt cache in place.
- Therefore the standard path must clone/store the prompt-only cache before iterating generated responses.

## Files

- Modify `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
  - Add a shared `_SessionPrefixCacheContext` parser.
  - Add a generic `_prefill_prompt_cache` helper and keep `_native_mtp_prefill_prompt_cache` as a compatibility alias.
  - Add standard-path prefix cache preparation and store/update logic.
  - Emit cache receipt fields on terminal standard-path events.
- Modify `services/mlx-worker-python/tests/test_mlx_backend.py`
  - Add standard-path cache assertions for cache miss/store, warm-hit suffix replay, trim-failure fallback, and safe bypasses.
  - Anchor those assertions in existing native-MTP LCP tests that are already selected by the MLX text PR-scoped probes, so the focused coverage gate stays local without changing the global probe registry.
- Modify docs only through this plan unless implementation reveals a canonical spec gap.

## Performance Probes and Metrics

Measurement points:

- `cache_hit_mode`: `none`, `partial`, or `exact` on the terminal event.
- `recovered_prefix_tokens`: token count recovered from `PrefixBlockStore`.
- `cache_fallback_reason`: `no_reusable_prefix`, `prompt_cache_unsupported`, `tokenizer_encode_unavailable`, or restore failure reason.
- `stream_prompt_token_count`: the token count passed to `stream_generate` after cache preparation.

Success metrics:

- Cold session request stores a prompt-only cache snapshot and emits `cache_hit_mode=none`.
- Warm session request with a block-aligned LCP passes a shorter token prompt to `stream_generate` and emits `cache_hit_mode=partial` or `exact`.
- Restore/trim failure releases the acquired store entry, falls back to cold prefill, and emits a fallback receipt.
- No-session, tokenizer-without-`encode`, and stream function without `prompt_cache` keep the raw prompt generation path.

The PR-scoped performance workflow already selects existing `mlx_text_runtime.py` probes for this file. PR evidence must additionally report the focused unit metrics above. The global probe registry should remain unchanged for this issue.

The standard path must not add overhead to no-session requests. Cache `stream_generate(prompt_cache=...)` support at backend initialization/runtime load time, and keep the no-session standard stream path on a raw fast path so the existing stop-kwarg signature-cache probe stays stable.

## Task 1: Red Tests for Standard Prefix Cache Behavior

**Files:**

- Modify: `services/mlx-worker-python/tests/test_mlx_backend.py`

- [x] **Step 1: Add test helper for standard-path cache backend**

Add a helper near the native-MTP LCP tests that builds an `AutoMLXBackend` with:

```python
def _build_standard_cache_backend(monkeypatch, *, store, encode_tokens, stream_calls, prefill_calls):
    from worker.runtime import prefix_block_store as _pbs

    monkeypatch.setattr(_pbs, "get_store", lambda *a, **kw: store)
    monkeypatch.setattr(mlx_text_runtime_module, "_get_prefix_store", lambda *a, **kw: store)
    monkeypatch.setattr(
        mlx_text_runtime_module,
        "_clone_cache_snapshot",
        lambda cache: [SimpleNamespace(state=[])] if cache is not None else None,
    )
    monkeypatch.setattr(mlx_text_runtime_module, "_estimate_cache_bytes", lambda cache: 128)

    def fake_prefill(model, tokens, *, prefill_step_size, stream, restore_cache=None, restore_token_count=0):
        prefill_calls.append(
            {
                "tokens": list(tokens),
                "restore_cache": restore_cache,
                "restore_token_count": restore_token_count,
            }
        )
        cache = restore_cache if restore_cache is not None else [SimpleNamespace(state=[])]
        return cache, [int(tokens[-1])], list(tokens[:-1])

    monkeypatch.setattr(mlx_text_runtime_module, "_prefill_prompt_cache", fake_prefill)

    class FakeTokenizer:
        bos_token = None
        eos_token = "</s>"
        eos_token_id = 2

        def encode(self, prompt, add_special_tokens=True):
            return list(encode_tokens)

    def fake_load(model_source: str, **kwargs):
        return SimpleNamespace(), FakeTokenizer()

    def fake_stream_generate(model, tokenizer, prompt, *, max_tokens, sampler, prompt_cache=None, **kwargs):
        stream_calls.append(
            {
                "prompt": list(prompt) if isinstance(prompt, list) else prompt,
                "prompt_cache": prompt_cache,
                "max_tokens": max_tokens,
            }
        )
        yield SimpleNamespace(
            text="x",
            raw_text="x",
            token=101,
            logprobs=None,
            prompt_tokens=len(prompt) if isinstance(prompt, list) else len(str(prompt)),
            generation_tokens=1,
            prompt_tps=1.0,
            generation_tps=1.0,
            peak_memory=0.0,
            finish_reason="stop",
        )

    backend = mlx_text_runtime_module.AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=fake_stream_generate,
        sampler_factory=lambda **kw: "sampler",
    )
    model_spec = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "x"})
    loaded = backend.load_model(model_spec)
    loaded[mlx_text_runtime_module._NATIVE_MTP_TEXT_ACTIVE_FIELD] = False
    return backend, loaded
```

- [x] **Step 2: Add cold miss/store assertion helper**

Add:

```python
def test_generate_standard_path_session_cache_miss_prefills_and_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    from worker.runtime.prefix_block_store import PrefixBlockStore

    store = PrefixBlockStore()
    stream_calls: list[dict] = []
    prefill_calls: list[dict] = []
    backend, loaded = _build_standard_cache_backend(
        monkeypatch,
        store=store,
        encode_tokens=[10, 20, 30, 40, 50, 60, 70, 80],
        stream_calls=stream_calls,
        prefill_calls=prefill_calls,
    )

    events = list(backend.generate_tokens(
        loaded,
        "hello world",
        common_pb2.SamplingConfig(max_output_tokens=2),
        Event(),
        execution_ext={
            "_melix.session_id": "standard-cold",
            "_melix.model_id": "test-model",
            "_melix.model_revision": "v1",
            "_melix.block_size": "4",
        },
    ))

    assert prefill_calls[0]["restore_cache"] is None
    assert stream_calls[0]["prompt"] == [80]
    assert stream_calls[0]["prompt_cache"] is not None
    assert events[-1].cache_hit_mode == "none"
    assert events[-1].recovered_prefix_tokens == 0
    assert events[-1].cache_fallback_reason == "no_reusable_prefix"
    lcp = store.find_lcp([10, 20, 30, 40, 50, 60, 70, 80], "test-model", "v1", 4)
    assert lcp.mode == "exact"
    assert lcp.recovered_prefix_tokens == 8
    assert lcp.entry is not None
    store.release(lcp.entry)
```

- [x] **Step 3: Add warm partial-hit assertion helper**

Add a test that seeds `PrefixBlockStore` with `[10,20,30,40,50,60,70,80]`, then generates with `[10,20,30,40,99,99,99,99]`. Assert:

```python
assert prefill_calls[0]["restore_cache"] is not None
assert prefill_calls[0]["restore_token_count"] == 4
assert stream_calls[0]["prompt"] == [99]
assert events[-1].cache_hit_mode == "partial"
assert events[-1].recovered_prefix_tokens == 4
```

- [x] **Step 4: Add trim-failure fallback assertion helper**

Seed a partial hit, install `_install_fake_trim(monkeypatch, returns=2)`, and assert:

```python
assert all(call["restore_cache"] is None for call in prefill_calls)
assert events[-1].cache_hit_mode == "none"
assert events[-1].cache_fallback_reason == "cache_restore_failed"
entry = store.acquire("trim-fail-standard")
assert entry is not None
assert entry._active_refs == 1
store.release(entry)
```

- [x] **Step 5: Add safe-bypass assertion helpers**

Use a `fake_stream_generate(model, tokenizer, prompt, *, max_tokens, sampler)` function without `prompt_cache` or `**kwargs`. Assert it receives the original prompt string and no prefill/store work runs:

```python
assert stream_calls[0]["prompt"] == "hello world"
assert prefill_calls == []
assert events[-1].cache_hit_mode == "none"
assert events[-1].cache_fallback_reason == "prompt_cache_unsupported"
```

- [x] **Step 6: Verify red**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_mlx_backend.py -k 'native_mtp_lcp_store_consulted_with_session_id or native_mtp_lcp_warm_path_uses_restored_cache or native_mtp_partial_hit_falls_back_when_trim_incomplete or native_mtp_no_session_reports_no_session_id' -q
```

Expected: selected tests fail because their standard-path assertion helpers exercise unimplemented `PrefixBlockStore` reuse in the standard `generate_tokens` path.

## Task 2: Implement Shared Context and Standard Prefix Cache Path

**Files:**

- Modify: `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`

- [x] **Step 1: Add shared context parser**

Add:

```python
@dataclass(frozen=True, slots=True)
class _SessionPrefixCacheContext:
    session_id: str
    model_id: str
    model_revision: str
    block_size: int
    cache_memory_budget_bytes: int
    acceleration_mode: str
    cache_mode: str
    force_fallback: bool
```

and a `_session_prefix_cache_context(execution_ext)` helper that preserves the native-MTP defaults: block size defaults to `64`, unset cache memory budget is `0`, unset cache mode becomes `CACHE_MODE_TIERED`, and `_test.force_cache_fallback` is honored only behind `MELIX_ENABLE_TEST_CACHE_HOOKS`.

- [x] **Step 2: Rename prefill helper with compatibility alias**

Rename the implementation function to `_prefill_prompt_cache(...)` and keep:

```python
_native_mtp_prefill_prompt_cache = _prefill_prompt_cache
```

so existing tests and native-MTP call sites keep working during the slice.

- [x] **Step 3: Use shared parser in native-MTP path**

Replace duplicated `_melix.*` parsing inside `_generate_native_mtp_batch_tokens` with:

```python
_cache_context = _session_prefix_cache_context(execution_ext)
```

and read fields from `_cache_context`.

- [x] **Step 4: Add standard-path prefix cache preparation**

Before the standard `stream_generate` loop, when the stream function accepts `prompt_cache`, the tokenizer has `encode`, and a session id exists:

1. Encode prompt tokens with the same BOS rule used by `stream_generate`.
2. Run `PrefixBlockStore.find_lcp`.
3. Clone and trim restored snapshots for warm hits.
4. Call `_prefill_prompt_cache` to create or replay a prompt cache.
5. Clone/store the prompt-only cache before iterating generation responses.
6. Call `stream_generate` with `prompt=[last_token]`, `prompt_cache=prompt_cache`, and existing sampler/stop kwargs.

Fallbacks must release any acquired store entry and keep generation alive.

- [x] **Step 5: Emit terminal receipt fields in standard path**

Set `cache_hit_mode`, `recovered_prefix_tokens`, and `cache_fallback_reason` only on terminal standard-path `RuntimeTokenEvent`s. Non-terminal events keep those fields `None`.

- [x] **Step 6: Verify green**

Run the red-test command from Task 1. Expected: all selected tests pass.

## Task 3: Focused Regression and Coverage Verification

**Files:**

- Modify only if required by failing tests:
  - `services/mlx-worker-python/tests/test_prefix_block_store.py`
  - `services/mlx-worker-python/tests/test_work_saved_cache_counters.py`

- [x] **Step 1: Run focused runtime tests**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_prefix_block_store.py services/mlx-worker-python/tests/test_work_saved_cache_counters.py -q
```

Expected: pass.

- [x] **Step 2: Run changed-scope coverage**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_prefix_block_store.py services/mlx-worker-python/tests/test_work_saved_cache_counters.py -q
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python scripts/python_changed_line_coverage.py --coverage-json coverage.json --diff-from origin/main services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/tests/test_mlx_backend.py
```

Expected: changed-line coverage for touched Python scope is at least `95%`.

- [x] **Step 3: Run formatting/diff checks**

```bash
git diff --check
git diff origin/main...HEAD --check
```

Expected: both pass.

- [x] **Step 4: Repair PR-scoped focused coverage selection**

After the first pre-commit attempt, the full Swift/Python/integration gate passed but the scoped performance report failed in `verification_failed` state because the new standard-path prefix-cache assertions lived in separate pytest nodeids that the existing MLX text probes did not run. Move those assertions under existing native-MTP LCP tests already selected by both MLX text probes, keeping `infra/perf/pr_scoped_probes.json` unchanged.

Also cache `stream_generate(prompt_cache=...)` support on `AutoMLXBackend` and keep no-session requests on the raw stream path so the standard path does not add per-request signature inspection or cache lifecycle overhead to the stop-kwarg probe.

Verification:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_mlx_backend.py -k 'standard_path or auto_backend_reuses_cached_stop_kwarg_signature or native_mtp' -q
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_mlx_backend.py -k 'native_mtp_lcp_store_consulted_with_session_id or native_mtp_lcp_warm_path_uses_restored_cache or native_mtp_partial_hit_falls_back_when_trim_incomplete or native_mtp_no_session_reports_no_session_id' -q
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_pr_scoped_performance.py -k 'mlx_text_stop or registered_probes_expose_focused_commands' -q
```

Expected: pass.

Scoped performance result:

```text
Melix PR Scoped Performance Report
Status: ok
Changed files: 3
Selected probes: 2
Regressions: 0
Verification failures: 0
```

## Task 4: PR Evidence, Full Gate, and Issue Closure

- [ ] **Step 1: Commit**

```bash
git add docs/plans/2026-07-08-issue-2599-standard-prefix-kv-reuse.md services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/tests/test_mlx_backend.py
git commit -m "feat: reuse standard text prefix cache"
```

Expected: the versioned pre-commit hook runs or reports a justified skip. On this host it should run the full local gate.

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin codex/issue-2599-standard-prefix-kv-reuse-20260708
```

Open a PR with the repository template headings and `Closes #2599`.

- [ ] **Step 3: Monitor PR to terminal state**

Wait for code review, CI, and PR-scoped performance report. Merge only when:

- review threads are resolved,
- required checks are green,
- performance report status is `ok` with `Regressions: 0`,
- branch is current with latest `origin/main`.
