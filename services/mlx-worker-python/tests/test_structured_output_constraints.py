from __future__ import annotations

import json
import math
import sys

import pytest

from scripts import structured_output_constraint_probe as probe_script
from worker.runtime import structured_output_constraints as constraints
from worker.runtime.structured_output_constraints import (
    StructuredOutputConstraintError,
    build_structured_output_logits_processors,
)


_MISSING = object()


@pytest.fixture
def mx():
    original_mlx = sys.modules.get("mlx", _MISSING)
    original_mlx_core = sys.modules.get("mlx.core", _MISSING)
    fake_core = probe_script._install_fake_mlx_core()
    try:
        yield fake_core
    finally:
        if original_mlx is _MISSING:
            sys.modules.pop("mlx", None)
        else:
            sys.modules["mlx"] = original_mlx
        if original_mlx_core is _MISSING:
            sys.modules.pop("mlx.core", None)
        else:
            sys.modules["mlx.core"] = original_mlx_core


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


class JSONSchemaConstraintTokenizer:
    eos_token_id = 10

    _id_to_text = {
        0: "{",
        1: "}",
        2: '"answer"',
        3: '"other"',
        4: ":",
        5: '"yes"',
        6: '"no"',
        7: '"bad"',
        8: ",",
        9: "0",
        10: "</s>",
    }

    def get_vocab(self) -> dict[str, int]:
        return {text: token_id for token_id, text in self._id_to_text.items()}

    def decode(self, token_ids, skip_special_tokens: bool = False) -> str:
        _ = skip_special_tokens
        return "".join(self._id_to_text[int(token_id)] for token_id in token_ids)


def _schema_ext(schema: dict[str, object]) -> dict[str, str]:
    return {
        "melix.structured_output.mode": "json_schema",
        "melix.structured_output.schema_name": "answer",
        "melix.structured_output.schema_json": json.dumps(schema, separators=(",", ":")),
        "melix.structured_output.strict": "true",
    }


def _compiled_schema_state(schema: dict[str, object]) -> constraints._SchemaPrefixState:
    return constraints._SchemaPrefixState(
        root_node=constraints._compile_json_schema(json.dumps(schema, separators=(",", ":")))
    )


def _schema_accepts_text(schema: dict[str, object], text: str) -> bool:
    state = constraints._schema_transition_text(_compiled_schema_state(schema), text)
    return state is not None and constraints._schema_is_complete(state)


def test_json_object_logits_processor_masks_invalid_prefix_tokens(mx) -> None:
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


def test_json_schema_logits_processor_enforces_required_property_and_enum(mx) -> None:
    schema = {
        "type": "object",
        "required": ["answer"],
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string", "enum": ["yes", "no"]},
        },
    }
    processors = build_structured_output_logits_processors(
        _schema_ext(schema),
        JSONSchemaConstraintTokenizer(),
    )
    assert len(processors) == 1
    processor = processors[0]
    logits = mx.array([[0.0] * len(JSONSchemaConstraintTokenizer._id_to_text)])

    initial = processor(mx.array([99]), logits)
    assert math.isfinite(float(initial[0, 0]))
    assert not math.isfinite(float(initial[0, 2]))

    after_open_object = processor(mx.array([99, 0]), logits)
    assert math.isfinite(float(after_open_object[0, 2]))
    assert not math.isfinite(float(after_open_object[0, 1]))
    assert not math.isfinite(float(after_open_object[0, 3]))

    after_property_key = processor(mx.array([99, 0, 2]), logits)
    assert math.isfinite(float(after_property_key[0, 4]))
    assert not math.isfinite(float(after_property_key[0, 5]))

    after_colon = processor(mx.array([99, 0, 2, 4]), logits)
    assert math.isfinite(float(after_colon[0, 5]))
    assert math.isfinite(float(after_colon[0, 6]))
    assert not math.isfinite(float(after_colon[0, 7]))
    assert not math.isfinite(float(after_colon[0, 9]))

    after_value = processor(mx.array([99, 0, 2, 4, 5]), logits)
    assert math.isfinite(float(after_value[0, 1]))
    assert not math.isfinite(float(after_value[0, 8]))

    after_complete_object = processor(mx.array([99, 0, 2, 4, 5, 1]), logits)
    assert math.isfinite(float(after_complete_object[0, 10]))
    assert not math.isfinite(float(after_complete_object[0, 2]))


def test_json_schema_const_and_enum_intersect_allowed_values(mx) -> None:
    schema = {
        "type": "object",
        "required": ["answer"],
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string", "enum": ["yes", "no"], "const": "yes"},
        },
    }
    processors = build_structured_output_logits_processors(
        _schema_ext(schema),
        JSONSchemaConstraintTokenizer(),
    )
    processor = processors[0]
    logits = mx.array([[0.0] * len(JSONSchemaConstraintTokenizer._id_to_text)])

    processor(mx.array([99]), logits)
    processor(mx.array([99, 0]), logits)
    processor(mx.array([99, 0, 2]), logits)
    after_colon = processor(mx.array([99, 0, 2, 4]), logits)

    assert math.isfinite(float(after_colon[0, 5]))
    assert not math.isfinite(float(after_colon[0, 6]))


def test_json_schema_unsupported_keywords_fail_closed() -> None:
    schema = {
        "type": "object",
        "patternProperties": {"^x-": {"type": "string"}},
    }

    with pytest.raises(StructuredOutputConstraintError) as error:
        build_structured_output_logits_processors(
            _schema_ext(schema),
            JSONSchemaConstraintTokenizer(),
        )

    assert error.value.details == {
        "mode": "json_schema",
        "enforcement": "sampler",
        "reason": "json_schema_unsupported_keyword",
        "keyword": "patternProperties",
    }


def test_json_schema_prefix_accepts_supported_complex_shapes() -> None:
    schema = {
        "type": "object",
        "required": ["arr", "count", "flag", "maybe", "extra"],
        "additionalProperties": False,
        "properties": {
            "arr": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 10},
                "minItems": 1,
                "maxItems": 2,
            },
            "count": {"type": "number", "minimum": -2.5, "maximum": 3.5},
            "flag": {"type": "boolean"},
            "maybe": {"type": ["null", "string"]},
            "extra": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
        },
    }

    examples = [
        ' { "arr" : [ 1 , 2 ] , "count" : -1.2e+0 , "flag" : true , '
        '"maybe" : null , "extra" : { "x" : "a\\n" } } \n',
        '{"arr":[0],"count":3,"flag":false,"maybe":"a\\u0041","extra":{}}',
    ]

    for text in examples:
        state = constraints._schema_transition_text(_compiled_schema_state(schema), text)
        assert state is not None, text
        assert constraints._schema_is_complete(state), text
        assert constraints._schema_transition_char(state, " ") is not None
        assert constraints._schema_transition_char(state, "x") is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "[]",
        '{"arr":[],"count":0,"flag":true,"maybe":null,"extra":{}}',
        '{"arr":[1,2,3],"count":0,"flag":true,"maybe":null,"extra":{}}',
        '{"arr":[1.5],"count":0,"flag":true,"maybe":null,"extra":{}}',
        '{"arr":[11],"count":0,"flag":true,"maybe":null,"extra":{}}',
        '{"arr":[-1],"count":0,"flag":true,"maybe":null,"extra":{}}',
        '{"arr":[1],"count":4,"flag":true,"maybe":null,"extra":{}}',
        '{"arr":[1],"count":0,"flag":truX,"maybe":null,"extra":{}}',
        '{"arr":[1],"count":0,"flag":true,"maybe":null,"extra":{},"bad":0}',
        '{"arr":[1],"arr":[2],"count":0,"flag":true,"maybe":null,"extra":{}}',
        '{"\\u0061rr":[1],"count":0,"flag":true,"maybe":null,"extra":{}}',
    ],
)
def test_json_schema_prefix_rejects_invalid_complex_shapes(text: str) -> None:
    schema = {
        "type": "object",
        "required": ["arr", "count", "flag", "maybe", "extra"],
        "additionalProperties": False,
        "properties": {
            "arr": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 10},
                "minItems": 1,
                "maxItems": 2,
            },
            "count": {"type": "number", "minimum": -2.5, "maximum": 3.5},
            "flag": {"type": "boolean"},
            "maybe": {"type": ["null", "string"]},
            "extra": {"type": "object", "additionalProperties": {"type": "string"}},
        },
    }

    assert constraints._schema_transition_text(_compiled_schema_state(schema), text) is None


def test_json_schema_prefix_handles_ambiguous_fixed_values_and_additional_keys() -> None:
    schema = {
        "type": "object",
        "required": ["x"],
        "properties": {
            "x": {"type": "integer", "enum": [1, 10]},
        },
    }

    assert _schema_accepts_text(schema, '{"x":1}')
    assert _schema_accepts_text(schema, '{"x":10}')
    assert _schema_accepts_text(schema, '{"\\u0061":"free","x":10}')
    assert not _schema_accepts_text(schema, '{"x":11}')


def test_json_schema_compiler_infers_types_and_accepts_supported_defaults() -> None:
    schema = {
        "type": "object",
        "properties": None,
        "required": None,
        "additionalProperties": {
            "enum": [{"a": 1}, [1], 1.5, True, None],
        },
    }

    node = constraints._compile_json_schema(json.dumps(schema, separators=(",", ":")))

    assert "object" in node.types
    assert node.properties == ()
    assert node.required == frozenset()
    assert node.additional is not None
    assert node.additional.types == ("object", "array", "number", "boolean", "null")
    assert constraints._schema_json_value_matches_type("1", "integer")
    assert not constraints._schema_json_value_matches_type("true", "integer")
    assert not constraints._schema_json_value_matches_type("{}", "unknown")


def test_json_schema_compiler_covers_inferred_object_array_and_true_schema() -> None:
    schema = {
        "type": "object",
        "properties": {
            "any": True,
            "inferredObject": {"properties": {"x": {"type": "string"}}},
            "inferredArray": {"items": {"type": "integer"}},
        },
    }

    node = constraints._compile_json_schema(json.dumps(schema, separators=(",", ":")))
    by_name = {prop.name: prop.node for prop in node.properties}

    assert by_name["any"] == constraints._ANY_SCHEMA_NODE
    assert by_name["inferredObject"].types == ("object",)
    assert by_name["inferredArray"].types == ("array",)


def test_json_schema_prefix_covers_array_and_number_state_edges() -> None:
    array_schema = {
        "type": "object",
        "required": ["values"],
        "additionalProperties": False,
        "properties": {
            "values": {"type": "array", "items": {"type": "integer"}, "maxItems": 0},
        },
    }
    number_schema = {
        "type": "object",
        "required": ["n"],
        "additionalProperties": False,
        "properties": {"n": {"type": "number"}},
    }
    integer_schema = {
        "type": "object",
        "required": ["n"],
        "additionalProperties": False,
        "properties": {"n": {"type": "integer"}},
    }

    assert _schema_accepts_text(array_schema, '{"values":[]}')
    assert not _schema_accepts_text(array_schema, '{"values":[1]}')
    for text in ('{"n":-0}', '{"n":0.5}', '{"n":0e1}', '{"n":1e+23}'):
        assert _schema_accepts_text(number_schema, text)
    for text in ('{"n":-x}', '{"n":1eX}', '{"n":1.2x}', '{"n":1.5}'):
        assert not _schema_accepts_text(integer_schema, text)

    assert constraints._schema_number_satisfies_node(None, "not-a-number")
    assert not constraints._schema_number_satisfies_node(
        constraints._SchemaNode(types=("number",)),
        "not-a-number",
    )


def test_json_schema_prefix_covers_defensive_state_edges() -> None:
    string_node = constraints._SchemaNode(types=("string",))
    object_node = constraints._SchemaNode(
        types=("object",),
        properties=(constraints._SchemaProperty(name="x", node=string_node),),
        additional=None,
    )
    base = constraints._SchemaPrefixState(root_node=object_node)
    open_state = constraints._schema_transition_text(base, "{")
    assert open_state is not None

    assert constraints._schema_replace_top(base, "key") is None
    assert constraints._schema_close_container(base) is None
    assert constraints._schema_complete_value(
        constraints._SchemaPrefixState(
            root_node=object_node,
            stack=(constraints._SchemaFrame(kind="object", node=object_node, expect="key"),),
        )
    ) is None
    assert (
        constraints._schema_transition_char(
            constraints._SchemaPrefixState(
                root_node=object_node,
                stack=(constraints._SchemaFrame(kind="unknown", node=object_node, expect="value"),),
            ),
            "x",
        )
        is None
    )

    duplicate_key_state = constraints._SchemaPrefixState(
        root_node=object_node,
        stack=(
            constraints._SchemaFrame(
                kind="object",
                node=object_node,
                expect="key",
                seen=frozenset(("x",)),
            ),
        ),
        mode="string",
        string_role="key",
        string_text="x",
    )
    assert constraints._schema_complete_key_string(duplicate_key_state) is None

    unknown_key_state = constraints._SchemaPrefixState(
        root_node=object_node,
        stack=(constraints._SchemaFrame(kind="object", node=object_node, expect="key"),),
        mode="string",
        string_role="key",
        string_text="missing",
    )
    assert constraints._schema_complete_key_string(unknown_key_state) is None

    value_string_state = constraints._SchemaPrefixState(
        root_node=object_node,
        mode="string",
        string_role="value",
        value_node=constraints._SchemaNode(types=("integer",)),
    )
    assert constraints._schema_transition_char(value_string_state, '"') is None
    assert constraints._schema_transition_char(value_string_state, "\x01") is None

    key_escape_state = constraints._SchemaPrefixState(
        root_node=object_node,
        stack=(constraints._SchemaFrame(kind="object", node=object_node, expect="key"),),
        mode="escape",
        string_role="key",
        string_text="z",
    )
    assert constraints._schema_transition_char(key_escape_state, "q") is None
    assert constraints._schema_transition_char(key_escape_state, "n") is None

    unicode_state = constraints._SchemaPrefixState(
        root_node=object_node,
        stack=(constraints._SchemaFrame(kind="object", node=object_node, expect="key"),),
        mode="unicode",
        string_role="key",
        unicode_remaining=4,
    )
    assert constraints._schema_transition_char(unicode_state, "x") is None


@pytest.mark.parametrize(
    ("schema", "reason", "keyword"),
    [
        ({"type": "array"}, "json_schema_root_not_object", ""),
        (False, "json_schema_unsupported_keyword", "false_schema"),
        ([], "json_schema_invalid", ""),
        ({"type": "object", "patternProperties": {}}, "json_schema_unsupported_keyword", "patternProperties"),
        ({"type": "object", "properties": {"x": False}}, "json_schema_unsupported_keyword", "false_schema"),
        ({"type": "object", "properties": {"x": []}}, "json_schema_invalid", ""),
        (
            {
                "type": "object",
                "properties": {"x": {"type": "array", "minItems": 2, "maxItems": 1}},
            },
            "json_schema_invalid",
            "",
        ),
        (
            {"type": "object", "properties": {"x": {"type": "string", "required": ["y"]}}},
            "json_schema_invalid",
            "",
        ),
        (
            {
                "type": "object",
                "required": ["missing"],
                "additionalProperties": False,
                "properties": {},
            },
            "json_schema_invalid",
            "missing",
        ),
        (
            {"type": "object", "properties": {"x": {"type": "string", "items": {}}}},
            "json_schema_invalid",
            "",
        ),
        (
            {"type": "object", "properties": {"x": {"type": "object", "minItems": 1}}},
            "json_schema_invalid",
            "",
        ),
        (
            {"type": "object", "properties": {"x": {"type": "string", "minimum": 1}}},
            "json_schema_invalid",
            "",
        ),
        ({"type": "object", "properties": {"x": {"enum": []}}}, "json_schema_invalid", "enum"),
        (
            {"type": "object", "properties": {"x": {"enum": ["yes"], "const": "no"}}},
            "json_schema_unsatisfiable",
            "const",
        ),
        (
            {"type": "object", "properties": {"x": {"type": "string", "enum": [1]}}},
            "json_schema_unsatisfiable",
            "enum",
        ),
        (
            {"type": "object", "properties": {"x": {"type": "date"}}},
            "json_schema_unsupported_type",
            "date",
        ),
        ({"type": "object", "properties": []}, "json_schema_invalid", "properties"),
        ({"type": "object", "required": ["x", 1]}, "json_schema_invalid", "required"),
        (
            {"type": "object", "additionalProperties": "no"},
            "json_schema_invalid",
            "additionalProperties",
        ),
        (
            {"type": "object", "properties": {"x": {"type": "array", "items": []}}},
            "json_schema_unsupported_keyword",
            "items[]",
        ),
        (
            {"type": "object", "properties": {"x": {"type": "number", "minimum": True}}},
            "json_schema_invalid",
            "minimum",
        ),
        (
            {"type": "object", "properties": {"x": {"type": "array", "minItems": -1}}},
            "json_schema_invalid",
            "minItems",
        ),
    ],
)
def test_json_schema_compiler_rejects_unsupported_and_invalid_shapes(
    schema: object,
    reason: str,
    keyword: str,
) -> None:
    with pytest.raises(StructuredOutputConstraintError) as error:
        constraints._compile_json_schema(json.dumps(schema, separators=(",", ":")))

    assert error.value.details["reason"] == reason
    if keyword:
        assert error.value.details["keyword"] == keyword


def test_json_schema_properties_reject_non_string_internal_names() -> None:
    with pytest.raises(StructuredOutputConstraintError) as error:
        constraints._schema_properties({"properties": {1: {}}}, pointer="")

    assert error.value.details["reason"] == "json_schema_invalid"
    assert error.value.details["keyword"] == "properties"


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
    assert not constraints.structured_output_requested(None)
    assert not constraints.structured_output_requested({})
    assert not constraints.structured_output_requested({"_melix.session_id": "probe"})
    assert not constraints.structured_output_requested(
        {"melix.structured_output.mode": "plain_text"}
    )
    assert constraints.structured_output_requested({"melix.structured_output.mode": "json"})
    assert constraints.structured_output_requested(
        {"melix.structured_output.mode": "json_schema"}
    )
    assert constraints.json_schema_constraint_error(
        {"melix.structured_output.mode": "json_schema"}
    ) is None
    assert build_structured_output_logits_processors(
        {"melix.structured_output.mode": "json_schema"},
        JSONConstraintTokenizer(),
    ) == []

    schema_processors = build_structured_output_logits_processors(
        {
            "melix.structured_output.mode": "json_schema",
            "melix.structured_output.schema_json": '{"type":"object"}',
        },
        JSONConstraintTokenizer(),
    )
    assert len(schema_processors) == 1

    with pytest.raises(StructuredOutputConstraintError) as malformed_schema_error:
        build_structured_output_logits_processors(
            {
                "melix.structured_output.mode": "json_schema",
                "melix.structured_output.schema_json": '{"type":"object"',
            },
            JSONConstraintTokenizer(),
        )
    assert malformed_schema_error.value.details["reason"] == "json_schema_invalid"

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


def test_json_object_logits_processor_masks_invalid_state_and_1d_logits(mx) -> None:
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


def test_json_object_logits_processor_accepts_eos_after_complete_object(mx) -> None:
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
    assert constraints._token_ids([[1, 2]]) == [1, 2]
    with pytest.raises(ValueError, match="single-sequence"):
        constraints._token_ids([[1, 2], [3, 4]])
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

    class EOSTokenFallbackTokenizer:
        eos_token = "</s>"

        def get_vocab(self) -> dict[str, int]:
            return {"{": 0, "}": 1, "</s>": 5}

        def decode(self, token_ids, skip_special_tokens: bool = False) -> str:
            _ = skip_special_tokens
            return {0: "{", 1: "}", 5: "</s>"}.get(int(token_ids[0]), "")

    eos_fallback_processors = build_structured_output_logits_processors(
        {"melix.structured_output.mode": "json_object"},
        EOSTokenFallbackTokenizer(),
    )
    assert eos_fallback_processors[0]._eos_token_ids == frozenset({5})

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
