from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


AGENTIC_MULTIMODAL_SAMPLE_FIELD_SCHEMA_VERSION = "melix.agentic_multimodal_sample_fields.v1"


def validate_agentic_multimodal_sample_fields(
    sample: dict[str, object],
    *,
    manifest_allowed_tools: object,
) -> list[str]:
    errors: list[str] = []
    input_payload = sample.get("input")
    input_text = ""
    if isinstance(input_payload, dict):
        raw_input_text = input_payload.get("text")
        if isinstance(raw_input_text, str):
            input_text = raw_input_text.strip()
    if not input_text:
        errors.append("input.text must be a non-empty string")

    question = _required_text(sample.get("question"), "question", errors)
    if question and input_text and question != input_text:
        errors.append("question must match input.text")

    target = _required_text(sample.get("target"), "target", errors)
    expected_answer = _required_text(sample.get("expected_answer"), "expected_answer", errors)
    if expected_answer and target and expected_answer != target:
        errors.append("expected_answer must match target")

    media_ids = _validate_media_refs(sample.get("media_refs"), errors)
    evidence_sources = set(media_ids)
    evidence_sources.update(_collect_tool_fixture_evidence_ids(sample.get("tool_fixture_context")))
    evidence_sources.update(_media_fragment_ids(media_ids, sample.get("tool_calls")))
    _validate_evidence_ids(sample.get("evidence_ids"), evidence_sources, errors)

    manifest_tools = _text_set(manifest_allowed_tools)
    allowed_tools = _validate_allowed_tools(sample.get("allowed_tools"), manifest_tools, errors)
    _validate_tool_calls(sample.get("tool_calls"), allowed_tools, errors)

    return errors


def _required_text(value: object, field_name: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field_name} must be a non-empty string")
        return ""
    return value.strip()


def _validate_media_refs(value: object, errors: list[str]) -> set[str]:
    if not isinstance(value, list) or not value:
        errors.append("media_refs must be a non-empty array")
        return set()

    media_ids: set[str] = set()
    for index, media_ref in enumerate(value):
        if not isinstance(media_ref, dict):
            errors.append(f"media_refs[{index}] must be an object")
            continue
        media_id = _media_ref_text(media_ref.get("id"))
        if not media_id:
            errors.append(f"media_refs[{index}].id must be a non-empty string")
        elif media_id in media_ids:
            errors.append(f"media_refs[{index}].id must be unique")
        else:
            media_ids.add(media_id)
        if not _media_ref_text(media_ref.get("kind")):
            errors.append(f"media_refs[{index}].kind must be a non-empty string")
        media_uri = _media_ref_text(media_ref.get("uri"))
        if not media_uri:
            errors.append(f"media_refs[{index}].uri must be a non-empty string")
        elif not _is_package_relative_path(media_uri):
            errors.append(f"media_refs[{index}].uri must be a package-relative path")
    return media_ids


def _media_ref_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _is_package_relative_path(value: str) -> bool:
    if "://" in value or value.startswith("/"):
        return False
    path = PurePosixPath(value)
    return ".." not in path.parts and bool(path.parts)


def _validate_evidence_ids(
    value: object,
    evidence_sources: set[str],
    errors: list[str],
) -> None:
    if not isinstance(value, list) or not value:
        errors.append("evidence_ids must be a non-empty array")
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"evidence_ids[{index}] must be a non-empty string")
            continue
        evidence_id = item.strip()
        if evidence_id in seen:
            errors.append(f"evidence_ids[{index}] must be unique")
        seen.add(evidence_id)
        if evidence_id not in evidence_sources:
            errors.append(
                f"evidence_ids[{index}] must reference media_refs or tool_fixture_context evidence"
            )


def _validate_allowed_tools(
    value: object,
    manifest_tools: set[str],
    errors: list[str],
) -> set[str]:
    if not isinstance(value, list) or not value:
        errors.append("allowed_tools must be a non-empty array")
        return set()
    allowed_tools: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"allowed_tools[{index}] must be a non-empty string")
            continue
        tool_name = item.strip()
        if tool_name in allowed_tools:
            errors.append(f"allowed_tools[{index}] must be unique")
        allowed_tools.add(tool_name)
        if manifest_tools and tool_name not in manifest_tools:
            errors.append(f"allowed_tools[{index}] must be declared by manifest allowed_tools")
    return allowed_tools


def _validate_tool_calls(
    value: object,
    allowed_tools: set[str],
    errors: list[str],
) -> None:
    if not isinstance(value, list) or not value:
        errors.append("tool_calls must be a non-empty array")
        return
    for index, tool_call in enumerate(value):
        if not isinstance(tool_call, dict):
            errors.append(f"tool_calls[{index}] must be an object")
            continue
        tool_name = tool_call.get("name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            errors.append(f"tool_calls[{index}].name must be a non-empty string")
            continue
        if tool_name.strip() not in allowed_tools:
            errors.append(f"tool_calls[{index}].name must be listed in allowed_tools")


def _text_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    }


def _collect_tool_fixture_evidence_ids(value: object) -> set[str]:
    evidence_ids: set[str] = set()
    _walk_tool_fixture_context(value, evidence_ids)
    return evidence_ids


def _walk_tool_fixture_context(value: object, evidence_ids: set[str]) -> None:
    if isinstance(value, dict):
        raw_id = value.get("id")
        if isinstance(raw_id, str) and raw_id.strip():
            evidence_ids.add(raw_id.strip())
        raw_evidence_ids = value.get("evidence_ids")
        if isinstance(raw_evidence_ids, list):
            evidence_ids.update(
                item.strip()
                for item in raw_evidence_ids
                if isinstance(item, str) and item.strip()
            )
        for nested in value.values():
            _walk_tool_fixture_context(nested, evidence_ids)
    elif isinstance(value, list):
        for item in value:
            _walk_tool_fixture_context(item, evidence_ids)


def _media_fragment_ids(media_ids: set[str], tool_calls: object) -> set[str]:
    evidence_ids: set[str] = set()
    if not isinstance(tool_calls, list):
        return evidence_ids
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        arguments = tool_call.get("arguments")
        if not isinstance(arguments, dict):
            continue
        media_ref = arguments.get("media_ref")
        region = arguments.get("region")
        if isinstance(media_ref, str) and media_ref.strip() in media_ids:
            if isinstance(region, str) and region.strip():
                evidence_ids.add(f"{media_ref.strip()}#{region.strip()}")
    return evidence_ids
