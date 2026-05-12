from __future__ import annotations

import re
from functools import lru_cache

_NON_WHITESPACE_TOKEN_RE = re.compile(r"\S+")


@lru_cache(maxsize=512)
def whitespace_token_count(text: str) -> int:
    return sum(1 for _ in _NON_WHITESPACE_TOKEN_RE.finditer(text))
