from __future__ import annotations

import re
from urllib.parse import SplitResult, urlsplit, urlunsplit


_URL_PATTERN = re.compile(r"\bhttps?://[^\s<>'\"]+")
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+\b"
)
_HF_TOKEN_PATTERN = re.compile(r"\bhf_[A-Za-z0-9][A-Za-z0-9_\-=]{5,}")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b([A-Za-z0-9_]*(?:"
    r"HF_TOKEN|HUGGINGFACE_HUB_TOKEN|MELIX_HF_TOKEN|MELIX_HUGGINGFACE_TOKEN|"
    r"MELIX_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|"
    r"API_KEY|ACCESS_TOKEN|AUTH_TOKEN|BEARER_TOKEN|SECRET_KEY|CLIENT_SECRET|"
    r"PASSWORD"
    r"))=([^\s]+)",
    flags=re.IGNORECASE,
)


class LogPrivacyRedactor:
    """Canonical redactor for operator-facing log excerpts."""

    def redact(self, value: str) -> str:
        text = str(value)
        if _has_no_sensitive_markers(text):
            return text
        if "://" in text:
            text = _URL_PATTERN.sub(_redact_url_match, text)
        if "=" in text:
            text = _SECRET_ASSIGNMENT_PATTERN.sub(r"\1=[REDACTED]", text)
        if "hf_" in text:
            text = _HF_TOKEN_PATTERN.sub("[REDACTED]", text)
        if "@" in text:
            text = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
        return text


_DEFAULT_REDACTOR = LogPrivacyRedactor()


def redact_log_text(value: str) -> str:
    """Redact secrets from operator-facing log excerpts without mutating logs."""

    return _DEFAULT_REDACTOR.redact(value)


def _has_no_sensitive_markers(text: str) -> bool:
    return "://" not in text and "=" not in text and "hf_" not in text and "@" not in text


def _redact_url_match(match: re.Match[str]) -> str:
    raw_url = match.group(0)
    suffix = ""
    while raw_url and raw_url[-1] in ".,);]":
        suffix = raw_url[-1] + suffix
        raw_url = raw_url[:-1]
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return "[REDACTED_URL]" + suffix
    if not parsed.scheme or not parsed.netloc:
        return match.group(0)
    netloc = _redacted_netloc(parsed.netloc)
    query = "[REDACTED]" if parsed.query else ""
    fragment = "[REDACTED]" if parsed.fragment else ""
    redacted = SplitResult(
        parsed.scheme,
        netloc,
        parsed.path,
        query,
        fragment,
    )
    return urlunsplit(redacted) + suffix


def _redacted_netloc(netloc: str) -> str:
    if "@" not in netloc:
        return netloc
    _, host_port = netloc.rsplit("@", 1)
    if not host_port:
        return "[REDACTED]"
    return f"[REDACTED]@{host_port}"
