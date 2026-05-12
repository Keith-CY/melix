from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=512)
def whitespace_token_count(text: str) -> int:
    token_count = 0
    in_token = False
    for character in text:
        if character.isspace():
            in_token = False
        elif not in_token:
            token_count += 1
            in_token = True
    return token_count
