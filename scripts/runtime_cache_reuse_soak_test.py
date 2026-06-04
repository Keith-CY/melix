#!/usr/bin/env python3
"""10,000-request soak test for prefix cache refcount safety.

Drives the PrefixBlockStore directly (no hardware) through alternating normal
and forced-fallback cycles and asserts zero leaked cache references. The forced
fallback exercises the same release/cleanup path the runtime's
`_test.force_cache_fallback` debug hook triggers in production-shaped flows.

Usage:
    python scripts/runtime_cache_reuse_soak_test.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.prefix_block_store import (
    PrefixBlockStore,
    reset_store,
)

_REQUEST_COUNT = int(os.environ.get("MELIX_SOAK_REQUESTS", "10000"))
_BLOCK_SIZE = 4
_MODEL_ID = "soak-model"
_MODEL_REVISION = "v1"


def _make_snapshot_bytes() -> dict[str, object]:
    return {"data": list(range(16))}


def _run_soak_unit() -> dict[str, object]:
    """Run the soak test using the block store directly — no hardware needed."""
    leaked: list[str] = []
    cleaned: list[str] = []

    def on_cleanup(entry: object) -> None:
        sid = getattr(entry, "session_id", "?")
        cleaned.append(sid)

    store = PrefixBlockStore(
        max_memory_bytes=512 * 1024,
        min_session_count=2,
        on_cleanup=on_cleanup,
    )

    normal_count = 0
    fallback_count = 0
    error_count = 0

    base_tokens = list(range(8))  # 2 blocks of 4

    for i in range(_REQUEST_COUNT):
        session_id = f"session-{i % 50}"  # rotate through 50 sessions
        force_fallback = (i % 2 == 1)

        # Simulate put (cold prefill result)
        try:
            store.put(
                session_id=session_id,
                token_ids=base_tokens + [i % 100],
                cache_snapshot=_make_snapshot_bytes(),
                cache_mode="CACHE_MODE_TIERED",
                model_id=_MODEL_ID,
                model_revision=_MODEL_REVISION,
                block_size=_BLOCK_SIZE,
                total_bytes=256,
            )
        except Exception as exc:
            error_count += 1
            leaked.append(f"put-error-{i}: {exc}")
            continue

        # Simulate LCP lookup
        result = store.find_lcp(
            base_tokens + [(i + 1) % 100],
            _MODEL_ID,
            _MODEL_REVISION,
            _BLOCK_SIZE,
            force_fallback=force_fallback,
        )

        if result.mode == "none":
            fallback_count += 1
        else:
            normal_count += 1

        entry = result.entry
        if entry is not None:
            # Simulate work with the entry, then release
            try:
                pass  # use entry
            finally:
                store.release(entry)

    store.flush_deferred_clear()

    # Check for active ref leaks
    with store._lock:
        for sid, entry in store._sessions.items():
            if entry._active_refs > 0:
                leaked.append(f"leaked active ref: session={sid}, active={entry._active_refs}")

    return {
        "probe": "runtime_cache_reuse_soak",
        "mode": "unit",
        "request_count": _REQUEST_COUNT,
        "normal_count": normal_count,
        "fallback_count": fallback_count,
        "error_count": error_count,
        "leaked_refs": leaked,
        "leaked_count": len(leaked),
        "passed": len(leaked) == 0 and error_count == 0,
    }


def main() -> None:
    result = _run_soak_unit()
    print(json.dumps(result, sort_keys=True, indent=2))

    if not result["passed"]:
        print(
            f"SOAK TEST FAILED: {result['leaked_count']} leaked refs, "
            f"{result['error_count']} errors",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Soak test passed: {result['request_count']} requests, zero leaks.", file=sys.stderr)


if __name__ == "__main__":
    main()
