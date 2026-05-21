from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worker.productization.agentic_multimodal_evaluation_contract import (
    validate_agentic_multimodal_sample_fields,
)
from worker.runtime.agentic_tools import execute_agentic_tool_calls


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures/evaluation"
)

EXPECTED_PACKAGES = {
    "agentic-multihop-qa.dev.v1": {
        "suite_id": "agentic_multihop_qa",
        "fixture_kind": "image_grounded_multi_hop_qa",
        "modalities": {"text", "image"},
        "required_tools": {"image_crop", "text_search"},
    },
    "agentic-visual-retrieval-qa.dev.v1": {
        "suite_id": "agentic_visual_retrieval_qa",
        "fixture_kind": "visual_retrieval_qa",
        "modalities": {"text", "image"},
        "required_tools": {"image_crop", "image_search", "visit"},
    },
    "agentic-document-lookup-qa.dev.v1": {
        "suite_id": "agentic_document_lookup_qa",
        "fixture_kind": "document_lookup_qa",
        "modalities": {"text", "document"},
        "required_tools": {"visit", "layout_parse", "text_search"},
    },
}


def test_agentic_multimodal_fixture_packages_cover_required_taxonomy() -> None:
    seen_fixture_kinds: set[str] = set()
    seen_suite_ids: set[str] = set()

    for package_id, expected in EXPECTED_PACKAGES.items():
        manifest, samples, _package_root = _load_fixture_package(package_id)
        seen_fixture_kinds.add(str(manifest.get("agentic_fixture_kind", "")))
        seen_suite_ids.add(str(manifest["suite_id"]))

        assert manifest["schema_version"] == "melix.evaluation_dataset_package.v2"
        assert manifest["dataset_id"] == package_id
        assert manifest["suite_id"] == expected["suite_id"]
        assert manifest["agentic_fixture_kind"] == expected["fixture_kind"]
        assert manifest["agentic_suite_family"] == "melix.agentic_multimodal_evaluation.dev.v1"
        assert manifest["toolset_version"] == "melix.agentic_tools.builtin.v1"
        assert manifest["trajectory_schema_version"] == "melix.agentic_tool_trace.v1"
        assert manifest["profile_type"] == "final_result"
        assert manifest["result_kind"] == "text"
        assert manifest["extraction_mode"] == "heuristic_final"
        assert manifest["scoring_mode"] == "normalized_exact_match"
        assert manifest["threshold"] == 1.0
        assert set(manifest["input_modalities"]) == expected["modalities"]
        assert manifest["sample_count"] == len(samples) == 1

    assert seen_fixture_kinds == {
        "image_grounded_multi_hop_qa",
        "visual_retrieval_qa",
        "document_lookup_qa",
    }
    assert seen_suite_ids == {
        "agentic_multihop_qa",
        "agentic_visual_retrieval_qa",
        "agentic_document_lookup_qa",
    }


def test_agentic_multimodal_fixture_samples_reference_local_assets_and_tools() -> None:
    for package_id, expected in EXPECTED_PACKAGES.items():
        manifest, samples, package_root = _load_fixture_package(package_id)

        for sample in samples:
            contract_errors = validate_agentic_multimodal_sample_fields(
                sample,
                manifest_allowed_tools=manifest["allowed_tools"],
            )
            assert contract_errors == []
            assert sample["id"].strip()
            assert sample["system"] == ""
            assert sample["question"] == sample["input"]["text"]
            assert sample["target"] == sample["expected_answer"]
            assert sample["evidence_ids"]
            assert sample["media_refs"]
            assert sample["allowed_tools"]
            assert sample["tool_calls"]
            assert sample["tool_fixture_context"]
            assert set(sample["allowed_tools"]).issubset(set(manifest["allowed_tools"]))
            assert expected["required_tools"].issubset(set(sample["allowed_tools"]))

            called_tools = {str(call["name"]) for call in sample["tool_calls"]}
            assert called_tools.issubset(set(sample["allowed_tools"]))
            assert expected["required_tools"].issubset(called_tools)

            for media_ref in sample["media_refs"]:
                assert media_ref["id"].strip()
                assert media_ref["kind"].strip()
                path = package_root / str(media_ref["uri"])
                assert path.is_file(), f"{package_id} missing media asset {path}"


def test_agentic_multimodal_fixture_samples_replay_with_deterministic_tools() -> None:
    for package_id in EXPECTED_PACKAGES:
        _manifest, samples, _package_root = _load_fixture_package(package_id)

        for sample in samples:
            run = execute_agentic_tool_calls(
                sample["tool_calls"],
                fixture_context=sample["tool_fixture_context"],
            )
            observations_json = json.dumps(run.observations, sort_keys=True)

            assert run.registry_receipt["toolset_version"] == "melix.agentic_tools.builtin.v1"
            assert run.metrics["agentic_tool.call_count"] == float(len(sample["tool_calls"]))
            assert run.metrics["agentic_tool.failed_count"] == 0.0
            assert run.metrics["agentic_tool.timeout_count"] == 0.0
            assert run.metrics["agentic_tool.completed_count"] == float(len(sample["tool_calls"]))
            for token in str(sample["expected_answer"]).split():
                assert token in observations_json, f"{package_id} tool observations missing answer token {token!r}"


def _load_fixture_package(package_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], Path]:
    package_root = FIXTURE_ROOT / package_id
    assert package_root.is_dir(), f"missing fixture package {package_id}"

    manifest = json.loads((package_root / "manifest.json").read_text(encoding="utf-8"))
    samples = [
        json.loads(line)
        for line in (package_root / "samples.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return manifest, samples, package_root
