from __future__ import annotations

from worker.engine import code_eval_runner


def test_assert_prescan_regex_preserves_horizontal_spacing_and_unicode_identifier_edges() -> None:
    assert code_eval_runner._may_contain_assert_statement("\t assert value") is True
    assert code_eval_runner._may_contain_assert_statement("asserté = 1") is False


def test_assert_prescan_uses_compiled_regex_search() -> None:
    calls: list[str] = []

    def tracked_search(test_code: str) -> object | None:
        calls.append(test_code)
        return object()

    def fail_isalnum(_value: str) -> bool:  # pragma: no cover - regression-only failure path
        raise AssertionError("compiled regex search owns identifier-boundary checks")

    assert code_eval_runner._may_contain_assert_statement(
        "assert value", _search=tracked_search, _isalnum=fail_isalnum
    )
    assert calls == ["assert value"]


def test_assert_prescan_skips_regex_when_literal_is_absent() -> None:
    calls: list[str] = []

    def tracked_contains(test_code: str, needle: str) -> bool:
        calls.append(f"contains:{needle}:{test_code[:5]}")
        return False

    def fail_search(_test_code: str) -> object | None:  # pragma: no cover - regression-only failure path
        raise AssertionError("literal pre-scan should skip regex for no-assert payloads")

    assert not code_eval_runner._may_contain_assert_statement(
        "value = candidate(1)",
        _contains=tracked_contains,
        _search=fail_search,
    )
    assert calls == ["contains:assert:value"]
