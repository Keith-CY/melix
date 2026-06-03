from __future__ import annotations

from functools import lru_cache

_ASCII_WHITESPACE = frozenset(" \t\n\r\v\f")


@lru_cache(maxsize=512)
def whitespace_token_count(
    text: str,
    *,
    _ascii_whitespace: frozenset[str] = _ASCII_WHITESPACE,
    _is_space=str.isspace,
) -> int:
    token_count = 0
    in_token = False
    if text.isascii():
        for character in text:
            if character in _ascii_whitespace:
                in_token = False
            elif not in_token:
                token_count += 1
                in_token = True
        return token_count

    for character in text:
        if _is_space(character):
            in_token = False
        elif not in_token:
            token_count += 1
            in_token = True
    return token_count
