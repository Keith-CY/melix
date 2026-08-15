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

    assert code_eval_runner._may_contain_assert_statement("assert value", _search=tracked_search)
    assert calls == ["assert value"]
