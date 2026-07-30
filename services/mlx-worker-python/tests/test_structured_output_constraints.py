from __future__ import annotations

from decimal import Decimal
import json
import math
import sys
from time import monotonic
from types import SimpleNamespace

import pytest

from scripts import structured_output_constraint_probe as probe_script
from scripts import structured_output_real_model_probe as real_model_probe
from worker.runtime import structured_output_constraints as constraints
from worker.runtime import tool_wire_constraints as tool_constraints
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


def _tool_ext(
    *,
    choice: str = "required",
    parser_mode: str = "qwen",
    parallel: bool = False,
) -> dict[str, str]:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "weather",
                "description": "Read weather",
                "parameters": {
                    "type": "object",
                    "required": ["count", "unit"],
                    "additionalProperties": False,
                    "properties": {
                        "count": {"type": "integer", "minimum": 1, "maximum": 5},
                        "meta": {
                            "type": "object",
                            "additionalProperties": {"type": "boolean"},
                        },
                        "note": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "unit": {"type": "string", "enum": ["c", "f"]},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search",
                "parameters": {
                    "type": "object",
                    "required": ["query"],
                    "additionalProperties": False,
                    "properties": {"query": {"type": "string"}},
                },
            },
        },
    ]
    return {
        "melix.compat.tool_choice_resolved": choice,
        "melix.compat.reasoning_mode": "disabled",
        "melix.tool_parser.mode": parser_mode,
        "melix.tool_config.parallel_policy": "enabled" if parallel else "disabled",
        "melix.tool_config.tools_json": json.dumps(tools, separators=(",", ":")),
    }


def _tool_accepts_text(execution_ext: dict[str, str], text: str) -> bool:
    tools, _, descriptor, parallel = tool_constraints._compile_tool_constraint(execution_ext)
    trie = tool_constraints._tool_prefix_trie(tools, descriptor)
    state = tool_constraints._tool_transition_text(
        tool_constraints._ToolPrefixState(phase="prefix", trie=trie),
        text,
        descriptor=descriptor,
        tools=tools,
        choice_trie=trie,
        parallel=parallel,
    )
    return state is not None and tool_constraints._tool_state_complete(state)


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


def test_json_schema_const_and_enum_use_json_schema_numeric_equality() -> None:
    schema = {
        "type": "object",
        "required": ["answer"],
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "integer", "enum": [1.0, 2], "const": 1},
        },
    }

    assert _schema_accepts_text(schema, '{"answer":1}')
    assert not _schema_accepts_text(schema, '{"answer":1.0}')
    assert constraints._schema_json_value_matches_type("1.0", "integer")
    assert constraints._schema_json_values_equal({"x": [1]}, {"x": [1.0]})
    assert not constraints._schema_json_values_equal(True, 1)


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
        '{"\\u0061rr":[1],"count":0,"flag":true,"maybe":null,"extra":{}}',
    ]

    for text in examples:
        state = constraints._schema_transition_text(_compiled_schema_state(schema), text)
        assert state is not None, text
        assert constraints._schema_is_complete(state), text
        assert constraints._schema_transition_char(state, " ") is not None
        assert constraints._schema_transition_char(state, "x") is None


def test_json_schema_prefix_decodes_unicode_escape_keys() -> None:
    schema = {
        "type": "object",
        "required": ["aA"],
        "additionalProperties": False,
        "properties": {
            "aA": {"type": "string"},
        },
    }

    state = constraints._schema_transition_text(
        _compiled_schema_state(schema),
        '{"a\\u0041":"x"}',
    )

    assert state is not None
    assert constraints._schema_is_complete(state)
    assert constraints._schema_transition_text(
        _compiled_schema_state({"type": "object", "additionalProperties": {"type": "string"}}),
        '{"aA":"x","a\\u0041":"y"}',
    ) is None


def test_json_schema_prefix_does_not_retain_unconstrained_string_values() -> None:
    string_node = constraints._SchemaNode(types=("string",))
    state = constraints._SchemaPrefixState(
        root_node=string_node,
        mode="string",
        string_role="value",
        value_node=string_node,
    )

    for char in "\\u0041":
        next_state = constraints._schema_transition_char(state, char)
        assert next_state is not None
        state = next_state

    assert state.mode == "string"
    assert state.string_text == ""


def test_json_schema_prefix_combines_unicode_surrogate_pair_keys() -> None:
    schema = {
        "type": "object",
        "required": ["emoji😀"],
        "additionalProperties": False,
        "properties": {"emoji😀": {"type": "string"}},
    }
    escaped = json.dumps({"emoji😀": "ok"}, ensure_ascii=True, separators=(",", ":"))

    assert _schema_accepts_text(schema, escaped)
    assert not _schema_accepts_text(schema, '{"emoji\\ud83d":"ok"}')
    assert not _schema_accepts_text(schema, '{"emoji\\ud83d\\u0041":"ok"}')
    assert not _schema_accepts_text(schema, '{"emoji\\ude00":"ok"}')


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


def test_json_schema_numeric_prefixes_keep_a_valid_bounded_completion() -> None:
    bounded_integer = {
        "type": "object",
        "required": ["n"],
        "additionalProperties": False,
        "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 5}},
    }
    value_state = constraints._schema_transition_text(
        _compiled_schema_state(bounded_integer),
        '{"n":',
    )
    assert value_state is not None
    assert constraints._schema_transition_char(value_state, "0") is None
    assert constraints._schema_transition_char(value_state, "9") is None
    assert constraints._schema_transition_char(value_state, "3") is not None

    expandable_integer = {
        "type": "object",
        "required": ["n"],
        "additionalProperties": False,
        "properties": {"n": {"type": "integer", "minimum": 100, "maximum": 100}},
    }
    assert _schema_accepts_text(expandable_integer, '{"n":100}')
    assert _schema_accepts_text(expandable_integer, '{"n":1e2}')
    assert not _schema_accepts_text(expandable_integer, '{"n":1e1}')


def test_json_schema_numeric_prefixes_reject_non_ascii_digits() -> None:
    schema = {
        "type": "object",
        "required": ["n"],
        "additionalProperties": False,
        "properties": {"n": {"type": "number"}},
    }

    assert not _schema_accepts_text(schema, '{"n":1٢}')


def test_json_schema_numeric_prefix_at_length_limit_cannot_become_a_dead_end() -> None:
    prefix = "1" * constraints._MAX_SCHEMA_NUMBER_CHARS
    target = Decimal(f"{prefix}0")
    node = constraints._SchemaNode(
        types=("integer",),
        minimum=target,
        maximum=target,
    )

    assert not constraints._schema_number_prefix_viable(node, prefix, "int")


def test_json_schema_numeric_helpers_cover_range_and_exponent_edges() -> None:
    integer_node = constraints._SchemaNode(
        types=("integer",),
        minimum=Decimal(1),
        maximum=Decimal(100),
    )

    assert constraints._schema_number_prefix_viable(None, "", "unknown")
    assert not constraints._schema_number_prefix_viable(
        integer_node,
        "1" * (constraints._MAX_SCHEMA_NUMBER_CHARS + 1),
        "int",
    )
    assert constraints._schema_number_prefix_viable(integer_node, "1", "unknown")
    assert not constraints._schema_number_prefix_viable(integer_node, "x", "int")
    assert not constraints._schema_exponent_prefix_viable(integer_node, "1", "exp")
    assert not constraints._schema_exponent_prefix_viable(integer_node, "xe1", "exp")
    assert not constraints._schema_exponent_prefix_viable(
        constraints._SchemaNode(types=("integer",), maximum=Decimal(-1)),
        "1e",
        "exp_start",
    )
    assert constraints._schema_exponent_prefix_viable(integer_node, "1e-", "exp_sign")
    assert constraints._schema_exponent_prefix_viable(
        constraints._SchemaNode(
            types=("number",),
            minimum=Decimal("0.01"),
            maximum=Decimal("0.1"),
        ),
        "1e-1",
        "exp",
    )
    assert constraints._schema_allowed_exponent_range(
        integer_node,
        Decimal("Infinity"),
    ) is None
    assert constraints._schema_allowed_exponent_range(
        constraints._SchemaNode(types=("number",), minimum=Decimal(0)),
        Decimal(-1),
    ) is None

    assert constraints._decimal_scale_ceiling(Decimal(9), Decimal(99)) == 2
    assert constraints._decimal_scale_floor(Decimal(11), Decimal(10)) == -1
    assert not constraints._unsigned_integer_prefix_intersects("1", 20, 10)
    assert constraints._unsigned_integer_prefix_intersects("1", 10, 19)

    number_node = constraints._SchemaNode(types=("number",))
    assert not constraints._schema_direct_decimal_prefix_intersects(number_node, "x", "int")
    assert constraints._schema_direct_decimal_prefix_intersects(
        constraints._SchemaNode(
            types=("number",),
            minimum=Decimal("-0.5"),
            maximum=Decimal("-0.2"),
        ),
        "-0",
        "zero",
    )
    assert constraints._schema_direct_decimal_prefix_intersects(
        constraints._SchemaNode(
            types=("number",),
            minimum=Decimal("-1.9"),
            maximum=Decimal("-1.5"),
        ),
        "-1",
        "int",
    )
    assert constraints._schema_direct_decimal_prefix_intersects(
        constraints._SchemaNode(
            types=("number",),
            minimum=Decimal("-1.25"),
            maximum=Decimal("-1.21"),
        ),
        "-1.2",
        "frac",
    )
    assert not constraints._schema_integer_digit_prefix_intersects(integer_node, "0")
    assert constraints._schema_integer_digit_prefix_intersects(
        constraints._SchemaNode(
            types=("integer",),
            minimum=Decimal(-10),
            maximum=Decimal(-10),
        ),
        "-1",
    )
    assert not constraints._schema_integer_digit_prefix_intersects(
        constraints._SchemaNode(types=("integer",), minimum=Decimal(-5)),
        "-1",
    )
    assert constraints._schema_integer_digit_prefix_intersects(
        constraints._SchemaNode(
            types=("integer",),
            minimum=Decimal(1_000),
            maximum=Decimal(1_000),
        ),
        "1",
    )
    assert constraints._schema_range_intersects(
        constraints._SchemaNode(types=("number",), maximum=Decimal(5)),
        Decimal(0),
        Decimal(10),
    )
    assert not constraints._schema_range_intersects(
        number_node,
        Decimal(1),
        Decimal(1),
        lower_open=True,
    )


def test_json_schema_enum_values_intersect_numeric_bounds() -> None:
    schema = {
        "type": "object",
        "required": ["n"],
        "additionalProperties": False,
        "properties": {
            "n": {"type": "integer", "enum": [1, 9], "minimum": 0, "maximum": 5},
        },
    }

    assert _schema_accepts_text(schema, '{"n":1}')
    assert not _schema_accepts_text(schema, '{"n":9}')


def test_json_schema_closed_empty_object_never_opens_a_key_dead_end() -> None:
    state = constraints._schema_transition_text(
        _compiled_schema_state({"type": "object", "additionalProperties": False}),
        "{",
    )

    assert state is not None
    assert constraints._schema_transition_char(state, '"') is None
    closed = constraints._schema_transition_char(state, "}")
    assert closed is not None
    assert constraints._schema_is_complete(closed)


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
        ({}, "json_schema_root_not_object", ""),
        (True, "json_schema_root_not_object", ""),
        ({"type": ["object", "string"]}, "json_schema_root_not_object", ""),
        ({"type": []}, "json_schema_invalid", "type"),
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
            {
                "type": "object",
                "properties": {"x": {"type": "number", "minimum": 10, "maximum": 5}},
            },
            "json_schema_unsatisfiable",
            "minimum",
        ),
        (
            {
                "type": "object",
                "properties": {"x": {"type": "number", "minimum": float("nan")}},
            },
            "json_schema_invalid",
            "",
        ),
        (
            {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "enum": [9], "minimum": 0, "maximum": 5},
                },
            },
            "json_schema_unsatisfiable",
            "enum",
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


def test_json_schema_compiler_enforces_depth_and_collection_limits() -> None:
    nested: dict[str, object] = {"type": "string"}
    for _ in range(constraints._MAX_SCHEMA_DEPTH + 1):
        nested = {"type": "array", "items": nested}
    schema = {"type": "object", "properties": {"value": nested}}

    with pytest.raises(StructuredOutputConstraintError) as depth_error:
        constraints._compile_json_schema(json.dumps(schema, separators=(",", ":")))
    assert depth_error.value.details["reason"] == "json_schema_too_complex"
    assert depth_error.value.details["limit"] == "max_depth"

    too_many_properties = {
        "type": "object",
        "properties": {
            f"p{index}": {"type": "string"}
            for index in range(constraints._MAX_SCHEMA_PROPERTIES + 1)
        },
    }
    with pytest.raises(StructuredOutputConstraintError) as property_error:
        constraints._compile_json_schema(json.dumps(too_many_properties, separators=(",", ":")))
    assert property_error.value.details["reason"] == "json_schema_too_complex"
    assert property_error.value.details["limit"] == "max_properties"

    too_many_enum_values = {
        "type": "object",
        "properties": {
            "value": {
                "type": "integer",
                "enum": list(range(constraints._MAX_SCHEMA_ENUM_VALUES + 1)),
            },
        },
    }
    with pytest.raises(StructuredOutputConstraintError) as enum_error:
        constraints._compile_json_schema(json.dumps(too_many_enum_values, separators=(",", ":")))
    assert enum_error.value.details["reason"] == "json_schema_too_complex"
    assert enum_error.value.details["limit"] == "max_enum_values"

    too_many_required = {
        "type": "object",
        "required": [f"p{index}" for index in range(constraints._MAX_SCHEMA_REQUIRED + 1)],
    }
    with pytest.raises(StructuredOutputConstraintError) as required_error:
        constraints._compile_json_schema(json.dumps(too_many_required, separators=(",", ":")))
    assert required_error.value.details["limit"] == "max_required"

    oversized_enum_text = {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "enum": ["x" * 1_000 + str(index) for index in range(33)],
            },
        },
    }
    with pytest.raises(StructuredOutputConstraintError) as enum_text_error:
        constraints._compile_json_schema(json.dumps(oversized_enum_text, separators=(",", ":")))
    assert enum_text_error.value.details["limit"] == "max_enum_text_bytes"

    with pytest.raises(StructuredOutputConstraintError) as byte_error:
        constraints._compile_json_schema(" " * (constraints._MAX_SCHEMA_JSON_BYTES + 1))
    assert byte_error.value.details["limit"] == "max_schema_bytes"

    with pytest.raises(StructuredOutputConstraintError) as node_error:
        constraints._compile_schema_node(
            {},
            pointer="",
            budget=constraints._SchemaCompileBudget(node_count=constraints._MAX_SCHEMA_NODES),
        )
    assert node_error.value.details["limit"] == "max_nodes"


def test_json_schema_compiler_converts_low_level_failures_to_typed_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(StructuredOutputConstraintError) as utf8_error:
        constraints._compile_json_schema(f'"{chr(0xD800)}"')
    assert utf8_error.value.details["reason"] == "json_schema_invalid"

    constraints._compile_json_schema.cache_clear()
    monkeypatch.setattr(
        constraints,
        "_compile_schema_node",
        lambda *args, **kwargs: (_ for _ in ()).throw(RecursionError()),
    )
    with pytest.raises(StructuredOutputConstraintError) as recursion_error:
        constraints._compile_json_schema("{}")
    assert recursion_error.value.details["limit"] == "max_depth"


def test_json_schema_internal_defensive_bounds_are_typed() -> None:
    assert constraints._compile_schema_node({}, pointer="").types == constraints._ANY_SCHEMA_TYPES

    with pytest.raises(StructuredOutputConstraintError) as number_size_error:
        constraints._schema_number_bound(
            {"minimum": 10**constraints._MAX_SCHEMA_NUMBER_CHARS},
            "minimum",
            pointer="",
        )
    assert number_size_error.value.details["limit"] == "max_number_chars"

    with pytest.raises(StructuredOutputConstraintError) as nonfinite_error:
        constraints._schema_number_bound(
            {"minimum": float("inf")},
            "minimum",
            pointer="",
        )
    assert nonfinite_error.value.details["reason"] == "json_schema_invalid"

    state = constraints._SchemaPrefixState()
    assert constraints._schema_enter_fixed_value(state, constraints._SchemaNode(), "x") is None
    assert constraints._schema_consume_fixed_char(state, "x") is None


def test_json_schema_compiler_converts_recursive_json_failure_to_typed_error() -> None:
    depth = 2_000
    schema_json = '{"type":"array","items":' * depth + '{"type":"string"}' + "}" * depth

    with pytest.raises(StructuredOutputConstraintError) as error:
        constraints._compile_json_schema(schema_json)

    assert error.value.details["reason"] in {"json_schema_invalid", "json_schema_too_complex"}


def test_json_schema_processor_bounds_request_owned_mask_cache(mx) -> None:
    processor = build_structured_output_logits_processors(
        _schema_ext(
            {
                "type": "object",
                "properties": {"value": {"type": "string"}},
            }
        ),
        JSONSchemaConstraintTokenizer(),
    )[0]
    logits = mx.array([[0.0] * len(JSONSchemaConstraintTokenizer._id_to_text)])

    for index in range(constraints._MAX_MASK_CACHE_ENTRIES + 5):
        state = constraints._JSONPrefixState(literal_target=str(index))
        processor._mask_for_state(state, len(JSONSchemaConstraintTokenizer._id_to_text), logits)

    assert len(processor._mask_cache) == constraints._MAX_MASK_CACHE_ENTRIES
    assert len(processor._mask_templates) == constraints._MAX_MASK_TEMPLATE_CACHE_ENTRIES
    assert (
        processor._mask_template_cache.estimated_bytes
        <= constraints._MAX_MASK_TEMPLATE_CACHE_ESTIMATED_BYTES
    )


def test_json_schema_processor_reuses_immutable_tokenizer_mask_templates(mx) -> None:
    tokenizer = JSONSchemaConstraintTokenizer()
    execution_ext = _schema_ext({"type": "object"})
    logits = mx.array([[0.0] * len(tokenizer._id_to_text)])
    first = build_structured_output_logits_processors(execution_ext, tokenizer)[0]
    second = build_structured_output_logits_processors(execution_ext, tokenizer)[0]

    first(mx.array([99]), logits)
    assert second._mask_cache == {}
    second._token_allowed = lambda *_args: pytest.fail("shared template was recomputed")
    second(mx.array([99]), logits)

    assert len(second._mask_cache) == 1
    assert first._mask_cache is not second._mask_cache
    assert first._mask_templates is second._mask_templates


def test_json_schema_mask_template_cache_enforces_estimated_byte_cap() -> None:
    processor = build_structured_output_logits_processors(
        _schema_ext({"type": "object"}),
        JSONSchemaConstraintTokenizer(),
    )[0]
    per_template_bytes = constraints._MAX_MASK_TEMPLATE_CACHE_ESTIMATED_BYTES // 2 + 1
    first = constraints._MaskTemplate(object(), (), per_template_bytes)
    second = constraints._MaskTemplate(object(), (), per_template_bytes)
    state = constraints._JSONPrefixState()

    processor._remember_shared_mask((state, 1, False), first)
    processor._remember_shared_mask((state, 1, False), first)
    processor._remember_shared_mask((state, 2, False), second)

    assert list(processor._mask_templates) == [(state, 2, False)]
    assert processor._mask_template_cache.estimated_bytes == per_template_bytes


def test_json_schema_processor_supports_tokenizers_without_attribute_storage() -> None:
    class SlotTokenizer:
        __slots__ = ()
        eos_token_id = 2

        def get_vocab(self) -> dict[str, int]:
            return {"{": 0, "}": 1, "</s>": 2}

        def decode(self, token_ids, skip_special_tokens: bool = False) -> str:
            _ = skip_special_tokens
            return {0: "{", 1: "}", 2: "</s>"}[int(token_ids[0])]

    processor = build_structured_output_logits_processors(
        {"melix.structured_output.mode": "json_object"},
        SlotTokenizer(),
    )[0]

    assert processor._mask_templates == {}


def test_json_schema_token_count_supports_single_sequence_matrix_and_rejects_batch() -> None:
    class MatrixTokens:
        def __init__(self, values: list[list[int]]) -> None:
            self.values = values
            self.shape = (len(values), len(values[0]))

        def tolist(self) -> list[list[int]]:
            return self.values

    tokens = MatrixTokens([[99, 0, 1]])
    assert constraints._single_sequence_token_count(tokens) == 3
    assert constraints._unapplied_token_ids(
        tokens,
        base_token_count=1,
        applied_generated_count=1,
    ) == (2, [1])

    with pytest.raises(ValueError, match="batch size 1"):
        constraints._single_sequence_token_count(MatrixTokens([[1], [2]]))


def test_json_schema_processor_reads_only_new_token_suffix(mx) -> None:
    tolist_calls: list[tuple[int, ...]] = []

    class TrackingTokens:
        def __init__(self, values: tuple[int, ...]) -> None:
            self.values = values
            self.shape = (len(values),)

        def __getitem__(self, index):
            return TrackingTokens(self.values[index])

        def tolist(self):
            tolist_calls.append(self.values)
            return list(self.values)

    tokenizer = JSONSchemaConstraintTokenizer()
    processor = build_structured_output_logits_processors(
        _schema_ext({"type": "object"}),
        tokenizer,
    )[0]
    logits = mx.array([[0.0] * len(tokenizer._id_to_text)])

    processor(TrackingTokens((99,)), logits)
    processor(TrackingTokens((99, 0)), logits)
    processor(TrackingTokens((99, 0, 1)), logits)

    assert tolist_calls == [(0,), (1,)]


def test_json_schema_properties_reject_non_string_internal_names() -> None:
    with pytest.raises(StructuredOutputConstraintError) as error:
        constraints._schema_properties({"properties": {1: {}, "a": {}}}, pointer="")

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

    with pytest.raises(StructuredOutputConstraintError) as schema_no_vocab_error:
        build_structured_output_logits_processors(
            _schema_ext({"type": "object"}),
            NoVocabularyTokenizer(),
        )
    assert schema_no_vocab_error.value.details["mode"] == "json_schema"
    assert schema_no_vocab_error.value.details["reason"] == "tokenizer_vocab_unavailable"

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


def test_required_and_named_json_tool_choices_are_sampler_enforced_from_token_zero() -> None:
    required = _tool_ext()
    weather = '<tool_call>{"name":"weather","arguments":{"count":2,"unit":"c"}}</tool_call>'
    search = '<tool_call>{"name":"search","arguments":{"query":"forecast"}}</tool_call>'

    assert _tool_accepts_text(required, weather)
    assert _tool_accepts_text(required, search)
    assert not _tool_accepts_text(required, f"I will call a tool. {weather}")
    assert not _tool_accepts_text(required, '<tool_call>{"name":"weather","arguments":{"unit":"x"}}</tool_call>')

    named = _tool_ext(
        choice='{"function":{"name":"weather"},"type":"function"}'
    )
    assert _tool_accepts_text(named, weather)
    assert not _tool_accepts_text(named, search)


def test_json_tool_argument_schema_covers_nested_optional_scalar_object_and_array_values() -> None:
    text = (
        '<tool_call>{"name":"weather","arguments":{'
        '"count":3,"meta":{"rain":false},"note":"a<b",'
        '"tags":["x","y"],"unit":"f"}}</tool_call>'
    )

    assert _tool_accepts_text(_tool_ext(), text)
    assert not _tool_accepts_text(_tool_ext(), text.replace('"count":3', '"count":8'))


def test_xml_parameter_tool_grammar_round_trips_and_only_full_value_boundary_closes() -> None:
    execution_ext = _tool_ext(parser_mode="xml")
    text = (
        "<tool_call><function=weather>"
        '<parameter=count>2</parameter>'
        '<parameter=meta>{"rain":true}</parameter>'
        '<parameter=note>"a<z and </parameter> text"</parameter>'
        '<parameter=tags>["x"]</parameter>'
        '<parameter=unit>"c"</parameter>'
        "</function></tool_call>"
    )

    assert _tool_accepts_text(execution_ext, text)
    parsed = __import__(
        "worker.runtime.tool_call_rescue",
        fromlist=["parse_tool_body"],
    ).parse_tool_body(text)
    assert parsed == {
        "name": "weather",
        "arguments": {
            "count": 2,
            "meta": {"rain": True},
            "note": "a<z and </parameter> text",
            "tags": ["x"],
            "unit": "c",
        },
    }

    optional_omitted = (
        "<tool_call><function=weather>"
        '<parameter=count>1</parameter><parameter=unit>"f"</parameter>'
        "</function></tool_call>"
    )
    assert _tool_accepts_text(execution_ext, optional_omitted)


def test_parallel_tool_calls_preserve_whitespace_separators() -> None:
    execution_ext = _tool_ext(parallel=True)
    weather = '<tool_call>{"name":"weather","arguments":{"count":2,"unit":"c"}}</tool_call>'
    search = '<tool_call>{"name":"search","arguments":{"query":"forecast"}}</tool_call>'

    assert _tool_accepts_text(execution_ext, f"{weather} \n\t{search}")
    assert not _tool_accepts_text(execution_ext, f"{weather} prose {search}")


def test_parallel_tool_mask_cache_restores_packed_mask_when_prefix_state_repeats(mx) -> None:
    weather = '<tool_call>{"name":"weather","arguments":{"count":2,"unit":"c"}}</tool_call>'
    search = '<tool_call>{"name":"search","arguments":{"query":"forecast"}}</tool_call>'

    class SplitParallelWireTokenizer:
        eos_token_id = 4
        _id_to_text = {
            0: "<",
            1: weather[1:],
            2: " ",
            3: search[1:],
            4: "</s>",
        }

        def get_vocab(self) -> dict[str, int]:
            return {text: token_id for token_id, text in self._id_to_text.items()}

        def decode(self, token_ids, skip_special_tokens: bool = False) -> str:
            _ = skip_special_tokens
            return "".join(self._id_to_text[int(token_id)] for token_id in token_ids)

    processor = build_structured_output_logits_processors(
        _tool_ext(parallel=True),
        SplitParallelWireTokenizer(),
    )[0]
    logits = mx.array([[0.0] * 5])
    processor(mx.array([99]), logits)
    processor(mx.array([99, 0]), logits)
    prefix_packed = processor.packed_allow_token_mask
    processor(mx.array([99, 0, 1]), logits)
    processor(mx.array([99, 0, 1, 2]), logits)
    separator_packed = processor.packed_allow_token_mask
    assert separator_packed != prefix_packed

    processor(mx.array([99, 0, 1, 2, 0]), logits)

    assert processor.packed_allow_token_mask == prefix_packed


def test_tool_constraint_reasoning_policy_and_pathological_inputs_fail_closed_before_generation() -> None:
    reasoning = _tool_ext()
    reasoning["melix.compat.reasoning_mode"] = "enabled"

    error = tool_constraints.tool_constraint_preflight_error(reasoning)
    assert error is not None
    assert error.code == "tool_constraint_reasoning_unsupported"
    assert error.details["reason"] == "tool_constraint_reasoning_unsupported"

    oversized = _tool_ext()
    oversized["melix.tool_config.tools_json"] = " " * (constraints._MAX_SCHEMA_JSON_BYTES + 1)
    started = monotonic()
    error = tool_constraints.tool_constraint_preflight_error(oversized)
    elapsed_ms = (monotonic() - started) * 1_000
    assert error is not None
    assert error.details["reason"] == "tool_schema_too_complex"
    assert error.details["limit"] == "max_schema_bytes"
    assert elapsed_ms < 50


def test_sampler_constraint_receipt_exposes_packed_mask_and_typed_acceleration_fallback(mx) -> None:
    wire = '<tool_call>{"name":"search","arguments":{"query":"forecast"}}</tool_call>'

    class WholeWireTokenizer:
        eos_token_id = 1
        vocab_size = 2

        def decode(self, token_ids, skip_special_tokens: bool = False) -> str:
            _ = skip_special_tokens
            return wire if int(token_ids[0]) == 0 else "</s>"

    execution_ext = _tool_ext(
        choice='{"function":{"name":"search"},"type":"function"}'
    )
    processor = build_structured_output_logits_processors(execution_ext, WholeWireTokenizer())[0]
    assert isinstance(processor, constraints.SamplerLogitsConstraint)
    masked = processor(mx.array([99]), mx.array([[0.0, 0.0]]))

    assert math.isfinite(float(masked[0, 0]))
    assert not math.isfinite(float(masked[0, 1]))
    assert processor.packed_allow_token_mask == (1,)
    complete_mask = processor(mx.array([99, 0]), mx.array([[0.0, 0.0]]))
    assert not math.isfinite(float(complete_mask[0, 0]))
    assert math.isfinite(float(complete_mask[0, 1]))
    cached_complete_mask = processor(mx.array([99, 0]), mx.array([[0.0, 0.0]]))
    assert math.isfinite(float(cached_complete_mask[0, 1]))
    eos_mask = processor(mx.array([99, 0, 1]), mx.array([[0.0, 0.0]]))
    assert math.isfinite(float(eos_mask[0, 1]))
    assert processor.acceleration_receipt == {
        "constraint_kind": "tool_choice_named",
        "mask_vocab_words": 1,
        "fast_path_used": False,
        "fallback_reason": "structured_output_acceleration_unsupported",
    }
    assert execution_ext["melix.constraint.constraint_kind"] == "tool_choice_named"
    assert execution_ext["melix.constraint.mask_vocab_words"] == "1"
    assert execution_ext["melix.constraint.fast_path_used"] == "false"
    assert (
        execution_ext["melix.constraint.fallback_reason"]
        == "structured_output_acceleration_unsupported"
    )
    assert tool_constraints.build_tool_choice_logits_processors({}, WholeWireTokenizer()) == []


def test_tool_schema_compilation_is_cached_but_processor_state_is_request_owned(mx) -> None:
    tool_constraints._compile_tool_definitions.cache_clear()
    execution_ext = _tool_ext()
    first = build_structured_output_logits_processors(execution_ext, JSONConstraintTokenizer())[0]
    second = build_structured_output_logits_processors(execution_ext, JSONConstraintTokenizer())[0]

    cache = tool_constraints._compile_tool_definitions.cache_info()
    assert cache.misses == 1
    assert cache.hits >= 1
    assert first is not second
    assert first._tools is second._tools
    assert first._choice_trie is not second._choice_trie
    assert first._state is not second._state
    assert first._state.phase == second._state.phase == "prefix"

    first(mx.array([99]), mx.array([[0.0] * 6]))
    first(mx.array([99, 0]), mx.array([[0.0] * 6]))
    assert first._state is None
    assert second._state is not None
    assert second._mask_cache == {}


def test_json_constraint_kind_receipt_is_stable_after_invalid_generated_prefix(mx) -> None:
    processor = build_structured_output_logits_processors(
        _schema_ext({"type": "object"}),
        JSONConstraintTokenizer(),
    )[0]

    processor(mx.array([99]), mx.array([[0.0] * 6]))
    processor(mx.array([99, 2]), mx.array([[0.0] * 6]))

    assert processor._state is None
    assert processor.constraint_kind == "json_schema"


def test_schema_state_space_audit_stops_combinatorial_numeric_frontier_at_hard_budget() -> None:
    schema_json = json.dumps(
        {
            "type": "object",
            "required": ["n"],
            "additionalProperties": False,
            "properties": {
                "n": {"type": "integer", "minimum": 0, "maximum": 10**30},
            },
        },
        separators=(",", ":"),
    )
    started = monotonic()
    with pytest.raises(StructuredOutputConstraintError) as error:
        constraints.audit_schema_state_space(
            schema_json,
            alphabet='{"n":0123456789}',
            max_depth=40,
            max_states=64,
            max_transitions=512,
            deadline_seconds=0.050,
        )
    elapsed_ms = (monotonic() - started) * 1_000

    assert error.value.details["reason"] == "json_schema_too_complex"
    assert error.value.details["limit"] == "state_space_exploration"
    assert int(error.value.details["state_count"]) <= 65
    assert elapsed_ms < 50


def test_real_model_probe_records_external_loader_blocker(tmp_path, monkeypatch) -> None:
    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "config.json").write_text(
        json.dumps(
            {
                "model_type": "gemma4",
                "architectures": ["Gemma4ForConditionalGeneration"],
                "quantization": {"bits": 8, "group_size": 64},
                "text_config": {"num_hidden_layers": 42, "num_kv_shared_layers": 18},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "receipt.json"

    def fail_load(_path: str):
        raise ValueError("Received 126 parameters not in model: \nextra.weight")

    monkeypatch.setattr(real_model_probe, "load", fail_load)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "structured_output_real_model_probe.py",
            "--model-path",
            str(model_path),
            "--output",
            str(output),
        ],
    )

    assert real_model_probe.main() == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "blocked_external_runtime"
    assert report["unexpected_parameter_count"] == 126
    assert report["model_evidence"]["num_kv_shared_layers"] == 18


def test_real_model_probe_runs_bounded_constrained_and_unconstrained_generation(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    constraint = object()

    monkeypatch.setattr(
        real_model_probe,
        "build_structured_output_logits_processors",
        lambda _ext, _tokenizer: [constraint],
    )
    monkeypatch.setattr(real_model_probe, "make_sampler", lambda **_kwargs: "greedy")

    def fake_stream_generate(_model, _tokenizer, prompt: str, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return iter(
            [
                SimpleNamespace(
                    text='{\"a\":',
                    generation_tokens=1,
                    generation_tps=10.0,
                    peak_memory=1.0,
                    finish_reason=None,
                ),
                SimpleNamespace(
                    text='\"x\"}',
                    generation_tokens=2,
                    generation_tps=9.0,
                    peak_memory=1.5,
                    finish_reason="stop",
                ),
            ]
        )

    monkeypatch.setattr(real_model_probe, "stream_generate", fake_stream_generate)
    constrained = real_model_probe._run_once(
        object(), object(), max_tokens=4, constrained=True
    )
    unconstrained = real_model_probe._run_once(
        object(), object(), max_tokens=3, constrained=False
    )

    assert constrained == {
        "text": '{"a":"x"}',
        "valid": True,
        "generation_tokens": 2,
        "generation_tps": 9.0,
        "peak_memory_gb": 1.5,
        "finish_reason": "stop",
    }
    assert unconstrained["valid"] is False
    assert calls[0]["logits_processors"] == [constraint]
    assert calls[0]["sampler"] == "greedy"
    assert calls[0]["max_tokens"] == 4
    assert calls[1]["logits_processors"] is None


def test_real_model_probe_reports_bounded_measured_ratio(tmp_path, monkeypatch) -> None:
    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "config.json").write_text(
        json.dumps({"model_type": "test", "quantization": {"bits": 4}}),
        encoding="utf-8",
    )
    output = tmp_path / "receipt.json"
    calls: list[bool] = []

    monkeypatch.setattr(real_model_probe, "load", lambda _path: (object(), object()))

    def fake_run(_model, _tokenizer, *, max_tokens: int, constrained: bool):
        calls.append(constrained)
        return {
            "text": '{"a":"x"}',
            "valid": constrained,
            "generation_tokens": max_tokens,
            "generation_tps": 9.0 if constrained else 10.0,
            "peak_memory_gb": 1.0,
            "finish_reason": "stop",
        }

    monkeypatch.setattr(real_model_probe, "_run_once", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "structured_output_real_model_probe.py",
            "--model-path",
            str(model_path),
            "--iterations",
            "1",
            "--max-tokens",
            "4",
            "--output",
            str(output),
        ],
    )

    assert real_model_probe.main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert calls == [False, True, False, True]
    assert report["status"] == "measured"
    assert report["throughput_ratio"] == pytest.approx(0.9)
    assert report["constrained_invalid_output_count"] == 0
    assert report["constrained_warmup"]["valid"] is True
