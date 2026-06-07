from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import re
import xml.etree.ElementTree as ElementTree

BRACKET_TOOL_OPEN = "[TOOL_CALL]"
BRACKET_TOOL_CLOSE = "[/TOOL_CALL]"
FENCE_OPEN = "```"
TOOL_CODE_OPEN = "<tool_code>"
TOOL_CODE_CLOSE = "</tool_code>"
XML_INVOKE_OPEN = "<invoke"
XML_INVOKE_CLOSE = "</invoke>"
WRONG_ENVELOPE_PYTHON_FENCE_ERROR_CODE = "tool_call_wrong_envelope_python_fence"
WRONG_ENVELOPE_PYTHON_FENCE_ERROR_MESSAGE = (
    "Move the JSON tool call into an accepted tool-call envelope such as "
    "<tool_call>...</tool_call>, [TOOL_CALL]...[/TOOL_CALL], or a json/tool_call fence."
)
RESCUE_START_CHARS = frozenset({"[", "`", "<"})
NON_ANGLE_RESCUE_START_CHARS = frozenset({"[", "`"})
FENCED_TOOL_LABELS = frozenset({"json", "tool", "tools", "tool_call", "tool_calls"})
WRONG_ENVELOPE_FENCED_TOOL_LABELS = frozenset({"python", "py"})
FENCED_RESCUE_LABELS = FENCED_TOOL_LABELS | WRONG_ENVELOPE_FENCED_TOOL_LABELS
ACCEPTED_WIRE_FORMATS = (
    "qwen_xml_tool_call",
    "pipe_tool_call",
    "fenced_json_tool_call",
    "bracket_tool_call",
    "xml_invoke_tool_call",
    "minimax_tool_code",
    "deepseek_normalized_xml_tool_call",
)
ACCEPTED_WIRE_FORMATS_JSON = json.dumps(list(ACCEPTED_WIRE_FORMATS), separators=(",", ":"))
STANDARD_WIRE_FORMATS = ("qwen_xml_tool_call", "pipe_tool_call")
STANDARD_WIRE_FORMATS_JSON = json.dumps(list(STANDARD_WIRE_FORMATS), separators=(",", ":"))
MISSING_ARGUMENTS = object()
PIPE_CALL_RE = re.compile(
    r"^\s*call:(?P<name>[A-Za-z0-9_.:/-]+)\s*(?P<args>\{.*\}|\(\s*\))\s*$",
    re.DOTALL,
)

_TOOL_NAME_ALIASES = {
    "browse": "visit",
    "browser": "visit",
    "browser_visit": "visit",
    "open_url": "visit",
    "visit_url": "visit",
    "search": "text_search",
    "textsearch": "text_search",
    "web_search": "text_search",
    "browser_search": "text_search",
    "calculator": "local_compute",
    "calculate": "local_compute",
    "code_interpreter": "local_compute",
    "python": "local_compute",
    "python_exec": "local_compute",
    "image_lookup": "image_search",
    "crop_image": "image_crop",
    "parse_layout": "layout_parse",
}
_PARTIAL_RESCUE_MARKERS = (
    BRACKET_TOOL_OPEN,
    XML_INVOKE_OPEN,
    TOOL_CODE_OPEN,
    FENCE_OPEN + "json",
    FENCE_OPEN + "tool_call",
    FENCE_OPEN + "tools",
    FENCE_OPEN + "tool",
    FENCE_OPEN + "python",
    FENCE_OPEN + "py",
)


@dataclass(frozen=True, slots=True)
class RescueEnvelope:
    fragment: str
    consumed_until: int
    visible_fallback: str = ""
    incomplete_prefix: str = ""
    label: str = ""


def has_non_angle_rescue_marker(text: str) -> bool:
    return "[" in text or "`" in text


def has_rescue_marker_start(text: str) -> bool:
    return "<" in text or "[" in text or "`" in text


def next_rescue_tag(text: str, *, start: int = 0) -> tuple[str, int] | None:
    if start >= len(text):
        return None
    candidates: list[tuple[str, int]] = []
    bracket_index = text.find(BRACKET_TOOL_OPEN, start)
    if bracket_index >= 0:
        candidates.append((BRACKET_TOOL_OPEN, bracket_index))
    fence_index = find_fenced_rescue_open(text, start=start)
    if fence_index >= 0:
        candidates.append((FENCE_OPEN, fence_index))
    invoke_index = find_xml_invoke_open(text, start=start)
    if invoke_index >= 0:
        candidates.append((XML_INVOKE_OPEN, invoke_index))
    tool_code_index = text.find(TOOL_CODE_OPEN, start)
    if tool_code_index >= 0:
        candidates.append((TOOL_CODE_OPEN, tool_code_index))
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate[1])


def find_fenced_tool_open(text: str, *, start: int = 0) -> int:
    return _find_fenced_open(text, labels=FENCED_TOOL_LABELS, start=start)


def find_fenced_rescue_open(text: str, *, start: int = 0) -> int:
    return _find_fenced_open(text, labels=FENCED_RESCUE_LABELS, start=start)


def _find_fenced_open(text: str, *, labels: frozenset[str], start: int = 0) -> int:
    index = text.find(FENCE_OPEN, start)
    while index >= 0:
        label_start = index + len(FENCE_OPEN)
        line_end = text.find("\n", label_start)
        if line_end < 0:
            label = text[label_start:].strip().casefold()
            if not label and index > 0 and text[index - 1] == "\n":
                return -1
            return index if partial_fenced_label(label, labels=labels) else -1
        label = text[label_start:line_end].strip().casefold()
        if label in labels:
            return index
        index = text.find(FENCE_OPEN, label_start)
    return -1


def partial_fenced_tool_label(label: str) -> bool:
    return partial_fenced_label(label, labels=FENCED_TOOL_LABELS)


def partial_fenced_label(label: str, *, labels: frozenset[str]) -> bool:
    if not label:
        return True
    return any(candidate.startswith(label) for candidate in labels)


def is_wrong_envelope_fence_label(label: str) -> bool:
    return label.strip().casefold() in WRONG_ENVELOPE_FENCED_TOOL_LABELS


def find_xml_invoke_open(text: str, *, start: int = 0) -> int:
    index = text.find(XML_INVOKE_OPEN, start)
    while index >= 0:
        next_index = index + len(XML_INVOKE_OPEN)
        next_char = text[next_index : next_index + 1]
        if not next_char or next_char.isspace() or next_char == ">":
            return index
        index = text.find(XML_INVOKE_OPEN, next_index)
    return -1


def partial_rescue_tag_suffix(text: str) -> str:
    if not has_rescue_marker_start(text):
        return ""

    start_index = max(text.rfind(char) for char in RESCUE_START_CHARS)
    if start_index < 0:
        return ""
    suffix = text[start_index:]
    if len(suffix) <= 1:
        return ""
    for marker in _PARTIAL_RESCUE_MARKERS:
        if len(suffix) < len(marker) and marker.startswith(suffix):
            return suffix
    return ""


def extract_rescue_envelope(text: str, tag: str, *, final: bool) -> RescueEnvelope | None:
    if tag == BRACKET_TOOL_OPEN:
        close_index = text.find(BRACKET_TOOL_CLOSE, len(tag))
        if close_index < 0:
            return RescueEnvelope("", 0) if final else None
        return RescueEnvelope(
            fragment=text[len(tag) : close_index],
            consumed_until=close_index + len(BRACKET_TOOL_CLOSE),
        )
    if tag == FENCE_OPEN:
        label_start = len(tag)
        open_end = text.find("\n", label_start)
        if open_end < 0:
            if final:
                return RescueEnvelope("", 0)
            return RescueEnvelope("", 0, incomplete_prefix=text)
        label = text[label_start:open_end].strip().casefold()
        close_index = text.find(FENCE_OPEN, open_end + 1)
        if close_index < 0:
            return RescueEnvelope("", 0) if final else None
        consumed_until = close_index + len(FENCE_OPEN)
        return RescueEnvelope(
            fragment=text[open_end + 1 : close_index],
            consumed_until=consumed_until,
            visible_fallback=text[:consumed_until],
            label=label,
        )
    if tag == XML_INVOKE_OPEN:
        open_end = text.find(">", len(tag))
        if open_end < 0:
            if final:
                return RescueEnvelope("", 0)
            return RescueEnvelope("", 0, incomplete_prefix=text)
        close_index = text.find(XML_INVOKE_CLOSE, open_end + 1)
        if close_index < 0:
            return RescueEnvelope("", 0) if final else None
        consumed_until = close_index + len(XML_INVOKE_CLOSE)
        return RescueEnvelope(fragment=text[:consumed_until], consumed_until=consumed_until)
    if tag == TOOL_CODE_OPEN:
        close_index = text.find(TOOL_CODE_CLOSE, len(tag))
        if close_index < 0:
            return RescueEnvelope("", 0) if final else None
        return RescueEnvelope(
            fragment=text[len(tag) : close_index],
            consumed_until=close_index + len(TOOL_CODE_CLOSE),
        )
    return RescueEnvelope("", 0)


def parse_tool_body(body: str) -> dict[str, object] | list[object] | None:
    stripped = body.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    parsed = parse_xml_tool_body(stripped)
    if parsed is not None:
        return parsed
    parsed = parse_pipe_tool_body(stripped)
    if parsed is not None:
        return parsed
    return parse_function_tool_body(stripped)


def looks_like_tool_payload(body: str) -> bool:
    stripped = body.strip()
    if not stripped:
        return False
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return (
            stripped.startswith("<")
            or PIPE_CALL_RE.match(stripped) is not None
            or function_call_syntax(stripped)
        )
    if isinstance(payload, dict):
        return bool(
            tool_payload_name(payload)
            or any(key in payload for key in ("arguments", "args", "parameters", "function"))
        )
    if isinstance(payload, list):
        return any(isinstance(item, dict) and tool_payload_name(item) for item in payload)
    return False


def function_call_syntax(body: str) -> bool:
    try:
        expression = ast.parse(body, mode="eval").body
    except (SyntaxError, ValueError, RecursionError):
        return False
    return isinstance(expression, ast.Call)


def parse_pipe_tool_body(body: str) -> dict[str, object] | None:
    match = PIPE_CALL_RE.match(body)
    if match is None:
        return None
    if match.group("args").startswith("("):
        return {"name": match.group("name"), "arguments": {}}
    try:
        arguments = json.loads(match.group("args"))
    except json.JSONDecodeError:
        arguments = parse_relaxed_object_arguments(match.group("args"))
        if arguments is None:
            return None
    if not isinstance(arguments, dict):
        return None
    return {"name": match.group("name"), "arguments": arguments}


def parse_xml_tool_body(body: str) -> dict[str, object] | None:
    if not body.startswith("<"):
        return None
    xml_body = body
    if body.startswith("<name") or body.startswith("<tool_name"):
        xml_body = f"<tool_call>{body}</tool_call>"
    try:
        root = ElementTree.fromstring(xml_body)
    except ElementTree.ParseError:
        return None
    tag = local_xml_tag(root.tag)
    if tag == "invoke":
        name = str(root.attrib.get("name") or root.attrib.get("tool") or "").strip()
        arguments_text = str(root.attrib.get("arguments") or root.attrib.get("args") or "").strip()
        if not name:
            name = xml_child_text(root, "name") or xml_child_text(root, "tool_name")
        if not arguments_text:
            arguments_text = (
                xml_child_text(root, "arguments")
                or xml_child_text(root, "args")
                or (root.text or "").strip()
            )
        return {"name": name, "arguments": parse_xml_arguments(arguments_text)}
    if tag == "tool_call":
        name = xml_child_text(root, "name") or xml_child_text(root, "tool_name")
        arguments_text = xml_child_text(root, "arguments") or xml_child_text(root, "args")
        if not name and root.text:
            return parse_tool_body(root.text)
        return {"name": name, "arguments": parse_xml_arguments(arguments_text)}
    return None


def parse_function_tool_body(body: str) -> dict[str, object] | None:
    try:
        expression = ast.parse(body, mode="eval").body
    except (SyntaxError, ValueError, RecursionError):
        return None
    if not isinstance(expression, ast.Call):
        return None
    name = ast_call_name(expression.func)
    if not name:
        return None
    arguments: dict[str, object] = {}
    if expression.args:
        if len(expression.args) != 1:
            return None
        try:
            positional = ast.literal_eval(expression.args[0])
        except (ValueError, SyntaxError, TypeError, RecursionError):
            return None
        if not isinstance(positional, dict):
            return None
        arguments.update(positional)
    for keyword in expression.keywords:
        if keyword.arg is None:
            return None
        try:
            arguments[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, SyntaxError, TypeError, RecursionError):
            return None
    return {"name": name, "arguments": arguments}


def ast_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = ast_call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def local_xml_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def xml_child_text(root: ElementTree.Element, name: str) -> str:
    for child in root:
        if local_xml_tag(child.tag) == name:
            return (child.text or "").strip()
    return ""


def parse_xml_arguments(text: str) -> object:
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        relaxed = parse_relaxed_object_arguments(stripped)
        return relaxed if relaxed is not None else stripped


def tool_payload_name(payload: dict[str, object]) -> str:
    function = payload.get("function")
    function_name = ""
    if isinstance(function, dict):
        function_name = str(function.get("name") or "").strip()
    return str(
        payload.get("name")
        or payload.get("tool_name")
        or payload.get("tool")
        or function_name
        or ""
    ).strip()


def tool_payload_arguments(payload: dict[str, object]) -> object:
    for key in ("arguments", "args", "parameters", "input"):
        if key in payload:
            return payload[key]
    function = payload.get("function")
    if isinstance(function, dict):
        for key in ("arguments", "args", "parameters"):
            if key in function:
                return function[key]
    return MISSING_ARGUMENTS


def coerce_tool_arguments(arguments: object) -> dict[str, object] | None:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        stripped = arguments.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = parse_relaxed_object_arguments(stripped)
        return parsed if isinstance(parsed, dict) else None
    return None


def resolve_tool_name(
    name: str,
    *,
    allowed_tool_names: tuple[str, ...],
    allowed_tool_name_set: set[str] | frozenset[str],
    allowed_tool_names_by_casefold: dict[str, str],
    allowed_tool_names_by_prefix: tuple[str, ...],
) -> str | None:
    if not allowed_tool_names:
        return name
    if name in allowed_tool_name_set:
        return name
    declared = allowed_tool_names_by_casefold.get(name.casefold())
    if declared is not None:
        return declared
    alias = _TOOL_NAME_ALIASES.get(name.casefold().replace("-", "_"))
    if alias is not None and alias in allowed_tool_name_set:
        return alias
    for external_name, canonical_name in _TOOL_NAME_ALIASES.items():
        if canonical_name in allowed_tool_name_set and is_action_qualified_tool_name(
            name,
            external_name,
        ):
            return canonical_name
    for declared in allowed_tool_names_by_prefix:
        if is_action_qualified_tool_name(name, declared):
            return declared
    return None


def is_action_qualified_tool_name(name: str, declared: str) -> bool:
    folded_name = name.casefold()
    folded_declared = declared.casefold()
    if len(folded_name) <= len(folded_declared):
        return False
    if not folded_name.startswith(folded_declared):
        return False
    return folded_name[len(folded_declared)] in {".", ":", "/"}


def parse_relaxed_object_arguments(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    content = stripped[1:-1].strip()
    if not content:
        return {}
    values: dict[str, object] = {}
    for item in split_relaxed_object_items(content):
        separator_index = relaxed_key_value_separator(item)
        if separator_index is None:
            return None
        key = item[:separator_index]
        value = item[separator_index + 1 :]
        normalized_key = key.strip().strip("\"'")
        if not normalized_key:
            return None
        values[normalized_key] = parse_relaxed_scalar(value.strip())
    return values


def split_relaxed_object_items(content: str) -> list[str]:
    items: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(content):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char == '"' or char == "'":
            quote = char
            continue
        if char == ",":
            items.append(content[start:index].strip())
            start = index + 1
    items.append(content[start:].strip())
    return items


def relaxed_key_value_separator(item: str) -> int | None:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(item):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char == '"' or char == "'":
            quote = char
            continue
        if char == ":":
            return index
    return None


def parse_relaxed_scalar(value: str) -> object:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return unescape_relaxed_quoted_string(value[1:-1])
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        if any(marker in value for marker in (".", "e", "E")):
            return float(value)
        return int(value)
    except ValueError:
        return value


def unescape_relaxed_quoted_string(value: str) -> str:
    if "\\" not in value:
        return value
    result: list[str] = []
    escaped = False
    escapes = {
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "b": "\b",
        "f": "\f",
    }
    for char in value:
        if escaped:
            result.append(escapes.get(char, char))
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            result.append(char)
    if escaped:
        result.append("\\")
    return "".join(result)
