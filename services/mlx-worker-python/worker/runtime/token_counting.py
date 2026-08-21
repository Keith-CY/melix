from __future__ import annotations

from functools import lru_cache


_ASCII_WHITESPACE = frozenset(" \t\n\r\v\f")


@lru_cache(maxsize=512)
def whitespace_token_count(text: str) -> int:
    """Count whitespace-delimited tokens, the shared deterministic estimator."""
    if text and text.isascii() and text[0] > " " and text[-1] > " ":
        if (
            "  " not in text
            and "\t" not in text
            and "\n" not in text
            and "\r" not in text
            and "\v" not in text
            and "\f" not in text
        ):
            return text.count(" ") + 1
    token_count = 0
    in_token = False
    if text.isascii():
        ascii_whitespace = _ASCII_WHITESPACE
        for character in text:
            if character in ascii_whitespace:
                in_token = False
            elif not in_token:
                token_count += 1
                in_token = True
        return token_count
    for character in text:
        if character.isspace():
            in_token = False
        elif not in_token:
            token_count += 1
            in_token = True
    return token_count
