from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=512)
def whitespace_token_count(text: str) -> int:
    """Count whitespace-delimited tokens, the shared deterministic estimator."""
    return len(text.split())
