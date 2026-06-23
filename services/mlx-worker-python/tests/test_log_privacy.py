from __future__ import annotations

from worker.productization.log_privacy import LogPrivacyRedactor, redact_log_text


def test_redact_log_text_returns_same_string_when_no_sensitive_markers() -> None:
    text = "fatal error: control plane crashed"

    assert redact_log_text(text) is text
    assert LogPrivacyRedactor().redact(text) is text


def test_redact_log_text_removes_credential_url_parts_and_emails() -> None:
    redacted = redact_log_text(
        "POST https://alice:secret@example.test:8443/v1/models?api_key=sk-live#frag "
        "failed for owner@example.test"
    )

    assert redacted == (
        "POST https://[REDACTED]@example.test:8443/v1/models?[REDACTED]#[REDACTED] "
        "failed for [REDACTED_EMAIL]"
    )
    assert "alice" not in redacted
    assert "secret" not in redacted
    assert "api_key" not in redacted
    assert "sk-live" not in redacted
    assert "frag" not in redacted
    assert "owner@example.test" not in redacted


def test_redact_log_text_removes_common_token_assignments_and_hf_tokens() -> None:
    redacted = redact_log_text(
        "HF_TOKEN=hf_secret_abcdef MELIX_API_KEY=sk-local-123 "
        "url=https://example.test/download?token=hf_query_abcdef bare=hf_bare_abcdef"
    )

    assert redacted == (
        "HF_TOKEN=[REDACTED] MELIX_API_KEY=[REDACTED] "
        "url=https://example.test/download?[REDACTED] bare=[REDACTED]"
    )
    assert "hf_secret" not in redacted
    assert "sk-local" not in redacted
    assert "hf_query" not in redacted
    assert "hf_bare" not in redacted


def test_redact_log_text_preserves_safe_url_shape_and_trailing_punctuation() -> None:
    redacted = redact_log_text("GET https://example.test/v1/models.)")

    assert redacted == "GET https://example.test/v1/models.)"


def test_redact_log_text_preserves_ipv6_host_shape() -> None:
    redacted = redact_log_text("GET http://user:pass@[::1]:12436/path?token=sk#frag")

    assert redacted == "GET http://[REDACTED]@[::1]:12436/path?[REDACTED]#[REDACTED]"
    assert "user" not in redacted
    assert "pass" not in redacted
    assert "token" not in redacted
    assert "frag" not in redacted


def test_redact_log_text_handles_unparseable_or_empty_host_urls() -> None:
    redacted = redact_log_text(
        "bad https://[broken.example.test/path and https://user@/path and https:///local/path"
    )

    assert redacted == "bad [REDACTED_URL] and https://[REDACTED]/path and https:///local/path"
