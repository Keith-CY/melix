from __future__ import annotations

import math

import mlx.core as mx
import pytest

from worker.runtime import structured_output_constraints as constraints
from worker.runtime.structured_output_constraints import (
    StructuredOutputConstraintError,
    build_structured_output_logits_processors,
)


class JSONConstraintTokenizer:
    eos_token_id = 5

    _id_to_text = {
        0: "{",
        1: "}",
        2: '"a"',
        3: ":",
        4: "0",
        5: "</s>",
    }

    def __init__(self) -> None:
        self.decode_call_count = 0

    def get_vocab(self) -> dict[str, int]:
        return {text: token_id for token_id, text in self._id_to_text.items()}

    def decode(self, token_ids, skip_special_tokens: bool = False) -> str:
        _ = skip_special_tokens
        self.decode_call_count += 1
        return "".join(self._id_to_text[int(token_id)] for token_id in token_ids)


def test_json_object_logits_processor_masks_invalid_prefix_tokens() -> None:
    processors = build_structured_output_logits_processors(
        {"melix.structured_output.mode": "json_object"},
        JSONConstraintTokenizer(),
    )
    assert len(processors) == 1
    processor = processors[0]
    logits = mx.array([[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]])

    initial = processor(mx.array([99]), logits)
    assert math.isfinite(float(initial[0, 0]))
    assert not math.isfinite(float(initial[0, 2]))

    after_open_object = processor(mx.array([99, 0]), logits)
    assert math.isfinite(float(after_open_object[0, 1]))
    assert math.isfinite(float(after_open_object[0, 2]))
    assert not math.isfinite(float(after_open_object[0, 3]))

    after_complete_object = processor(mx.array([99, 0, 1]), logits)
    assert math.isfinite(float(after_complete_object[0, 5]))
    assert not math.isfinite(float(after_complete_object[0, 2]))


def test_json_object_logits_processor_reuses_tokenizer_vocabulary_cache() -> None:
    tokenizer = JSONConstraintTokenizer()

    first_processors = build_structured_output_logits_processors(
        {"melix.structured_output.mode": "json_object"},
        tokenizer,
    )
    assert len(first_processors) == 1
    assert tokenizer.decode_call_count == len(tokenizer._id_to_text)

    second_processors = build_structured_output_logits_processors(
        {"melix.structured_output.mode": "json_object"},
        tokenizer,
    )

    assert len(second_processors) == 1
    assert tokenizer.decode_call_count == len(tokenizer._id_to_text)


def test_plain_text_mode_does_not_build_processors() -> None:
    tokenizer = JSONConstraintTokenizer()

    processors = build_structured_output_logits_processors(
        {"melix.structured_output.mode": "plain_text"},
        tokenizer,
    )

    assert processors == []
    assert tokenizer.decode_call_count == 0


def test_mode_normalization_and_json_schema_errors() -> None:
    assert constraints.normalize_structured_output_mode(
        {"melix.structured_output.mode": "json"}
    ) == "json_object"
    assert constraints.normalize_structured_output_mode(
        {"melix.structured_output.mode": "none"}
    ) == "text"
    assert constraints.normalize_structured_output_mode(None) == ""
    assert constraints.normalize_structured_output_mode(object()) == ""
    assert constraints.json_schema_constraint_error(
        {"melix.structured_output.mode": "json_schema"}
    ) is None
    assert build_structured_output_logits_processors(
        {"melix.structured_output.mode": "json_schema"},
        JSONConstraintTokenizer(),
    ) == []

    with pytest.raises(StructuredOutputConstraintError) as schema_error:
        build_structured_output_logits_processors(
            {
                "melix.structured_output.mode": "json_schema",
                "melix.structured_output.schema_json": '{"type":"object"}',
            },
            JSONConstraintTokenizer(),
        )
    assert schema_error.value.details["reason"] == "json_schema_grammar_unavailable"

    with pytest.raises(StructuredOutputConstraintError) as unsupported_error:
        build_structured_output_logits_processors(
            {"melix.structured_output.mode": "xml"},
            JSONConstraintTokenizer(),
        )
    assert unsupported_error.value.details["reason"] == "unsupported_mode"


def test_json_prefix_accepts_nested_json_object_shapes() -> None:
    examples = [
        "{}",
        ' { "a" : [ true , false , null , -1.2e+3 , 0 ] } \n',
        '{"a":{"b":"x\\n\\u0041"}}',
        '{"a":[1,2.3,4E-5]}',
        '{"a":[]}',
        '{"a":1,"b":2}',
    ]

    for text in examples:
        state = constraints._transition_text(constraints._INITIAL_JSON_OBJECT_STATE, text)
        assert state is not None, text
        assert constraints._is_complete(state), text


@pytest.mark.parametrize(
    "text",
    [
        "",
        "[]",
        '{"a":}',
        '{"a":"\x01"}',
        '{"a":"\\q"}',
        '{"a":"\\u00xz"}',
        '{"a":truX}',
        '{"a":-}',
        '{"a":0a}',
        '{"a":1ea}',
        '{"a":1e+a}',
        '{"a":1.}',
        '{"a":1.2a}',
        '{"a":1e2a}',
        '{"a":,}',
    ],
)
def test_json_prefix_rejects_invalid_json_object_prefixes(text: str) -> None:
    assert constraints._transition_text(constraints._INITIAL_JSON_OBJECT_STATE, text) is None


def test_json_object_logits_processor_masks_invalid_state_and_1d_logits() -> None:
    processors = build_structured_output_logits_processors(
        {"melix.structured_output.mode": "json_object"},
        JSONConstraintTokenizer(),
    )
    processor = processors[0]
    logits = mx.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    initial = processor(mx.array([99]), logits)
    assert math.isfinite(float(initial[0]))

    invalid = processor(mx.array([99, 2]), logits)
    assert all(not math.isfinite(float(value)) for value in invalid.tolist())

    still_invalid = processor(mx.array([99, 2, 0]), logits)
    assert all(not math.isfinite(float(value)) for value in still_invalid.tolist())


def test_json_object_logits_processor_accepts_eos_after_complete_object() -> None:
    processors = build_structured_output_logits_processors(
        {"melix.structured_output.mode": "json_object"},
        JSONConstraintTokenizer(),
    )
    processor = processors[0]
    logits = mx.array([[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]])

    processor(mx.array([99]), logits)
    processor(mx.array([99, 0, 1]), logits)
    after_eos = processor(mx.array([99, 0, 1, 5]), logits)

    assert math.isfinite(float(after_eos[0, 5]))


def test_token_helpers_cover_fallback_shapes() -> None:
    assert constraints._token_ids(7) == [7]
    assert constraints._token_ids([[1, 2], 3]) == [1, 2, 3]
    assert constraints._replace_top(constraints._INITIAL_JSON_OBJECT_STATE, "value") is None
    assert constraints._close_container(constraints._INITIAL_JSON_OBJECT_STATE) is None
    assert constraints._complete_value(
        constraints._JSONPrefixState(
            root="in_progress",
            stack=(constraints._Frame("object", "key"),),
        )
    ) is None


def test_tokenizer_fallbacks_and_errors() -> None:
    class NoVocabularyTokenizer:
        pass

    with pytest.raises(StructuredOutputConstraintError) as no_vocab_error:
        build_structured_output_logits_processors(
            {"melix.structured_output.mode": "json_object"},
            NoVocabularyTokenizer(),
        )
    assert no_vocab_error.value.details["reason"] == "tokenizer_vocab_unavailable"

    class DecodeFallbackTokenizer:
        eos_token_ids = [5, "ignored", 6]

        def get_vocab(self) -> dict[str, int]:
            return {"{": 0, "}": 1, "</s>": 5, "<alt>": 6}

        def decode(self, token_ids, skip_special_tokens: bool = False) -> str:
            if skip_special_tokens is not False:
                raise TypeError("old decode signature")
            return {0: "{", 1: "}", 5: "</s>", 6: "<alt>"}.get(int(token_ids[0]), "")

    processors = build_structured_output_logits_processors(
        {"melix.structured_output.mode": "json_object"},
        DecodeFallbackTokenizer(),
    )
    assert len(processors) == 1

    class LenFallbackTokenizer:
        def get_vocab(self) -> dict[str, int]:
            raise RuntimeError("vocab unavailable")

        def __len__(self) -> int:
            return 2

        def decode(self, token_ids, skip_special_tokens: bool = False) -> str:
            _ = skip_special_tokens
            return "{" if int(token_ids[0]) == 0 else "}"

    assert len(
        build_structured_output_logits_processors(
            {"melix.structured_output.mode": "json_object"},
            LenFallbackTokenizer(),
        )
    ) == 1

    class EmptyLenTokenizer:
        def __len__(self) -> int:
            raise RuntimeError("length unavailable")

        def decode(self, token_ids, skip_special_tokens: bool = False) -> str:
            _ = token_ids, skip_special_tokens
            return ""

    with pytest.raises(StructuredOutputConstraintError):
        build_structured_output_logits_processors(
            {"melix.structured_output.mode": "json_object"},
            EmptyLenTokenizer(),
        )


def test_decode_exceptions_are_skipped_until_vocabulary_is_available() -> None:
    class PartiallyFailingTokenizer:
        vocab_size = 3

        def decode(self, token_ids, skip_special_tokens: bool = False) -> str:
            token_id = int(token_ids[0])
            if token_id == 0 and skip_special_tokens is False:
                raise TypeError("retry without kwargs")
            if token_id == 1:
                raise RuntimeError("bad token")
            return {0: "{", 2: "}"}.get(token_id, "")

    assert len(
        build_structured_output_logits_processors(
            {"melix.structured_output.mode": "json_object"},
            PartiallyFailingTokenizer(),
        )
    ) == 1
