from __future__ import annotations

from copy import deepcopy

from worker.productization.agentic_multimodal_evaluation_contract import (
    AGENTIC_MULTIMODAL_SAMPLE_FIELD_SCHEMA_VERSION,
    validate_agentic_multimodal_sample_fields,
)


def test_agentic_multimodal_sample_field_contract_accepts_valid_sample() -> None:
    errors = validate_agentic_multimodal_sample_fields(
        _valid_sample(),
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert AGENTIC_MULTIMODAL_SAMPLE_FIELD_SCHEMA_VERSION == (
        "melix.agentic_multimodal_sample_fields.v1"
    )
    assert errors == []


def test_agentic_multimodal_sample_field_contract_requires_question() -> None:
    sample = _valid_sample()
    sample.pop("question")

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert "question must be a non-empty string" in errors


def test_agentic_multimodal_sample_field_contract_requires_question_to_match_input_text() -> None:
    sample = _valid_sample()
    sample["question"] = "Different prompt"

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert "question must match input.text" in errors


def test_agentic_multimodal_sample_field_contract_requires_expected_answer_to_match_target() -> None:
    sample = _valid_sample()
    sample["expected_answer"] = "different answer"

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert "expected_answer must match target" in errors


def test_agentic_multimodal_sample_field_contract_validates_media_refs() -> None:
    sample = _valid_sample()
    sample["media_refs"] = [
        {"id": "", "kind": "image", "uri": "media/card.ppm"},
        {"id": "remote", "kind": "image", "uri": "https://example.test/card.ppm"},
    ]

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert "media_refs[0].id must be a non-empty string" in errors
    assert "media_refs[1].uri must be a package-relative path" in errors


def test_agentic_multimodal_sample_field_contract_maps_evidence_ids_to_known_sources() -> None:
    sample = _valid_sample()
    sample["evidence_ids"] = ["missing-evidence"]

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert "evidence_ids[0] must reference media_refs or tool_fixture_context evidence" in errors


def test_agentic_multimodal_sample_field_contract_rejects_tools_outside_manifest() -> None:
    sample = _valid_sample()
    sample["allowed_tools"] = ["image_crop", "web_search"]

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert "allowed_tools[1] must be declared by manifest allowed_tools" in errors


def test_agentic_multimodal_sample_field_contract_requires_tool_calls_to_be_allowed() -> None:
    sample = _valid_sample()
    sample["allowed_tools"] = ["image_crop"]

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert "tool_calls[1].name must be listed in allowed_tools" in errors


def test_agentic_multimodal_sample_field_contract_reports_missing_required_arrays() -> None:
    sample = _valid_sample()
    sample["input"] = {}
    sample["media_refs"] = []
    sample["evidence_ids"] = []
    sample["allowed_tools"] = []
    sample["tool_calls"] = None

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools={"not": "a list"},
    )

    assert "input.text must be a non-empty string" in errors
    assert "media_refs must be a non-empty array" in errors
    assert "evidence_ids must be a non-empty array" in errors
    assert "allowed_tools must be a non-empty array" in errors
    assert "tool_calls must be a non-empty array" in errors


def test_agentic_multimodal_sample_field_contract_reports_malformed_media_refs() -> None:
    sample = _valid_sample()
    sample["media_refs"] = [
        "bad media ref",
        {"id": "query-card", "kind": "", "uri": ""},
        {"id": "query-card", "kind": "image", "uri": "/tmp/card.ppm"},
        {"id": 17, "kind": "image", "uri": "../card.ppm"},
    ]

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert "media_refs[0] must be an object" in errors
    assert "media_refs[1].kind must be a non-empty string" in errors
    assert "media_refs[1].uri must be a non-empty string" in errors
    assert "media_refs[2].id must be unique" in errors
    assert "media_refs[2].uri must be a package-relative path" in errors
    assert "media_refs[3].id must be a non-empty string" in errors
    assert "media_refs[3].uri must be a package-relative path" in errors


def test_agentic_multimodal_sample_field_contract_reports_malformed_evidence_ids() -> None:
    sample = _valid_sample()
    sample["evidence_ids"] = ["query-card#label", "query-card#label", "", 17]

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert "evidence_ids[1] must be unique" in errors
    assert "evidence_ids[2] must be a non-empty string" in errors
    assert "evidence_ids[3] must be a non-empty string" in errors


def test_agentic_multimodal_sample_field_contract_reports_malformed_allowed_tools() -> None:
    sample = _valid_sample()
    sample["allowed_tools"] = ["image_crop", "image_crop", "", 17]

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert "allowed_tools[1] must be unique" in errors
    assert "allowed_tools[2] must be a non-empty string" in errors
    assert "allowed_tools[3] must be a non-empty string" in errors


def test_agentic_multimodal_sample_field_contract_reports_malformed_tool_calls() -> None:
    sample = _valid_sample()
    sample["tool_calls"] = [
        "bad tool call",
        {"name": ""},
        {"name": 17, "arguments": {"media_ref": "query-card", "region": "label"}},
        {"name": "image_crop", "arguments": "not an object"},
    ]

    errors = validate_agentic_multimodal_sample_fields(
        sample,
        manifest_allowed_tools=["image_crop", "text_search", "visit"],
    )

    assert "tool_calls[0] must be an object" in errors
    assert "tool_calls[1].name must be a non-empty string" in errors
    assert "tool_calls[2].name must be a non-empty string" in errors


def _valid_sample() -> dict[str, object]:
    return deepcopy(
        {
            "id": "sample-1",
            "system": "",
            "input": {
                "text": "Read the image and search the notes for the matching launch window.",
                "image_uri": "media/card.ppm",
            },
            "target": "dawn window",
            "question": "Read the image and search the notes for the matching launch window.",
            "expected_answer": "dawn window",
            "media_refs": [
                {"id": "query-card", "kind": "image", "uri": "media/card.ppm"},
            ],
            "evidence_ids": [
                "query-card#label",
                "launch-note-17",
            ],
            "allowed_tools": [
                "image_crop",
                "text_search",
            ],
            "tool_calls": [
                {
                    "id": "crop-card",
                    "name": "image_crop",
                    "arguments": {
                        "media_ref": "query-card",
                        "region": "label",
                        "purpose": "read the label",
                    },
                },
                {
                    "id": "search-notes",
                    "name": "text_search",
                    "arguments": {
                        "query": "launch window",
                        "corpus_ref": "notes",
                        "max_results": 1,
                    },
                },
            ],
            "tool_fixture_context": {
                "crops": {
                    "query-card#label": {
                        "text": "BAY-17",
                        "evidence_ids": ["query-card#label"],
                    },
                },
                "text_corpus": {
                    "notes": [
                        {
                            "id": "launch-note-17",
                            "text": "BAY-17 launch window is dawn window.",
                        },
                    ],
                },
            },
        }
    )
