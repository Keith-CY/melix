from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from worker.model_ops.errors import ModelOperationError
from worker.productization.evaluation_final_result import (
    EvaluationFieldMapping,
    HFEvaluationDatasetSource,
    EvaluationMaterializationRequest,
    EvaluationProfileDefinition,
    extract_final_result,
    materialize_hf_evaluation_dataset,
    materialize_local_evaluation_dataset,
    score_final_result,
)


def test_extract_final_result_prefers_last_fenced_json_block() -> None:
    outcome = extract_final_result(
        raw_response=(
            "Reasoning...\n"
            "```json\n"
            "{\"answer\":\"wrong\"}\n"
            "```\n"
            "Final payload follows.\n"
            "```json\n"
            "{\"answer\":\"Paris\"}\n"
            "```"
        ),
        result_kind="json",
        extraction_mode="heuristic_final",
    )

    assert outcome.extraction_status == "extracted"
    assert json.loads(outcome.extracted_result) == {"answer": "Paris"}
    assert outcome.failure_reason == ""


def test_extract_final_result_marks_ambiguous_text_answer_prefixes_as_failure() -> None:
    outcome = extract_final_result(
        raw_response="Answer: Paris\nAnswer: Lyon",
        result_kind="text",
        extraction_mode="heuristic_final",
    )

    assert outcome.extraction_status == "ambiguous_extraction"
    assert outcome.extracted_result == ""
    assert outcome.failure_reason == "multiple_answer_prefix_candidates"


def test_score_final_result_validates_json_schema_and_ignores_default_paths() -> None:
    score = score_final_result(
        extracted_result=json.dumps(
            {
                "verdict": "supported",
                "evidence": ["citation-a"],
                "confidence": 0.88,
            }
        ),
        target=json.dumps(
            {
                "verdict": "supported",
                "evidence": ["citation-b"],
            }
        ),
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="json",
            extraction_mode="heuristic_final",
            scoring_mode="json_field_match",
            threshold=1.0,
            output_schema={
                "type": "object",
                "required": ["verdict"],
                "properties": {
                    "verdict": {"type": "string"},
                    "evidence": {"type": "array"},
                    "confidence": {"type": "number"},
                },
            },
            ignored_paths=("confidence",),
        ),
    )

    assert score.validation_status == "validated"
    assert score.failure_reason == ""
    assert score.typed_score == 1.0


def test_score_final_result_rejects_invalid_json_shape_before_scoring() -> None:
    score = score_final_result(
        extracted_result=json.dumps([{"label": "A"}]),
        target=json.dumps({"label": "A"}),
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="json",
            extraction_mode="strict_full_response",
            scoring_mode="json_field_match",
            threshold=1.0,
            output_schema={
                "type": "object",
                "required": ["label"],
                "properties": {"label": {"type": "string"}},
            },
        ),
    )

    assert score.validation_status == "schema_failed"
    assert score.failure_reason == "root_type_mismatch"
    assert score.typed_score == 0.0


def test_materialize_local_evaluation_dataset_requires_explicit_mapping_for_jsonl(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.jsonl"
    source_path.write_text(json.dumps({"prompt": "Question", "answer": "Paris"}) + "\n", encoding="utf-8")

    with pytest.raises(ModelOperationError) as excinfo:
        materialize_local_evaluation_dataset(
            request=EvaluationMaterializationRequest(
                source_kind="jsonl",
                source_path=source_path,
                profile=EvaluationProfileDefinition(
                    profile_type="final_result",
                    result_kind="text",
                    extraction_mode="heuristic_final",
                    scoring_mode="normalized_exact_match",
                    threshold=1.0,
                ),
                field_mapping=EvaluationFieldMapping(),
            ),
            cache_root=tmp_path / "cache",
        )

    assert excinfo.value.code == "invalid_evaluation_source"


def test_materialize_local_evaluation_dataset_builds_final_result_package_from_csv(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.csv"
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sys", "question", "gold"])
        writer.writeheader()
        writer.writerow(
            {
                "sys": "Return the final answer only.",
                "question": "Capital of France?",
                "gold": "Paris",
            }
        )

    materialized = materialize_local_evaluation_dataset(
        request=EvaluationMaterializationRequest(
            source_kind="csv",
            source_path=source_path,
            profile=EvaluationProfileDefinition(
                profile_type="final_result",
                result_kind="text",
                extraction_mode="heuristic_final",
                scoring_mode="normalized_exact_match",
                threshold=1.0,
            ),
            field_mapping=EvaluationFieldMapping(
                system_path="sys",
                input_text_path="question",
                target_path="gold",
            ),
            dataset_id="capital.dev.v1",
            suite_id="capital",
        ),
        cache_root=tmp_path / "cache",
    )

    manifest = json.loads((materialized.package_path / "manifest.json").read_text(encoding="utf-8"))
    sample = json.loads((materialized.package_path / "samples.jsonl").read_text(encoding="utf-8").strip())

    assert manifest["profile_type"] == "final_result"
    assert manifest["result_kind"] == "text"
    assert manifest["source_kind"] == "csv"
    assert sample["system"] == "Return the final answer only."
    assert sample["input"]["text"] == "Capital of France?"
    assert sample["target"] == "Paris"


def test_materialize_local_evaluation_dataset_invalidates_cache_when_local_source_changes(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.csv"
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sys", "question", "gold"])
        writer.writeheader()
        writer.writerow(
            {
                "sys": "Return the final answer only.",
                "question": "Capital of France?",
                "gold": "Paris",
            }
        )

    request = EvaluationMaterializationRequest(
        source_kind="csv",
        source_path=source_path,
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="text",
            extraction_mode="heuristic_final",
            scoring_mode="normalized_exact_match",
            threshold=1.0,
        ),
        field_mapping=EvaluationFieldMapping(
            system_path="sys",
            input_text_path="question",
            target_path="gold",
        ),
        dataset_id="capital.dev.v1",
        suite_id="capital",
    )

    first = materialize_local_evaluation_dataset(
        request=request,
        cache_root=tmp_path / "cache",
    )

    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sys", "question", "gold"])
        writer.writeheader()
        writer.writerow(
            {
                "sys": "Return the final answer only.",
                "question": "Capital of Italy?",
                "gold": "Rome",
            }
        )

    second = materialize_local_evaluation_dataset(
        request=request,
        cache_root=tmp_path / "cache",
    )

    sample = json.loads((second.package_path / "samples.jsonl").read_text(encoding="utf-8").strip())

    assert first.cache_hit is False
    assert second.cache_hit is False
    assert second.cache_key != first.cache_key
    assert second.package_path != first.package_path
    assert sample["input"]["text"] == "Capital of Italy?"
    assert sample["target"] == "Rome"


def test_materialize_hf_evaluation_dataset_invalidates_cache_when_rows_change(
    tmp_path: Path,
) -> None:
    class ChangingFetcher:
        def __init__(self) -> None:
            self._rows_calls = 0

        def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
            if endpoint != "rows":
                raise AssertionError(f"Unexpected endpoint: {endpoint}")
            self._rows_calls += 1
            if self._rows_calls == 1:
                row = {
                    "system_prompt": "Return only the final answer.",
                    "question": "Capital of France?",
                    "gold_answer": "Paris",
                    "sample_key": "capital-1",
                }
            else:
                row = {
                    "system_prompt": "Return only the final answer.",
                    "question": "Capital of Italy?",
                    "gold_answer": "Rome",
                    "sample_key": "capital-1",
                }
            return {"rows": [{"row": row}]}

    fetcher = ChangingFetcher()
    source = HFEvaluationDatasetSource(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        split="train",
    )

    first = materialize_hf_evaluation_dataset(
        source=source,
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="text",
            extraction_mode="heuristic_final",
            scoring_mode="normalized_exact_match",
            threshold=1.0,
        ),
        field_mapping=EvaluationFieldMapping(
            system_path="system_prompt",
            input_text_path="question",
            target_path="gold_answer",
            sample_id_path="sample_key",
        ),
        dataset_id="capital.dev.v1",
        suite_id="capital",
        cache_root=tmp_path / "cache",
        fetch_json=fetcher,
    )

    second = materialize_hf_evaluation_dataset(
        source=source,
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="text",
            extraction_mode="heuristic_final",
            scoring_mode="normalized_exact_match",
            threshold=1.0,
        ),
        field_mapping=EvaluationFieldMapping(
            system_path="system_prompt",
            input_text_path="question",
            target_path="gold_answer",
            sample_id_path="sample_key",
        ),
        dataset_id="capital.dev.v1",
        suite_id="capital",
        cache_root=tmp_path / "cache",
        fetch_json=fetcher,
    )

    sample = json.loads((second.package_path / "samples.jsonl").read_text(encoding="utf-8").strip())

    assert first.cache_hit is False
    assert second.cache_hit is False
    assert second.cache_key != first.cache_key
    assert second.package_path != first.package_path
    assert sample["input"]["text"] == "Capital of Italy?"
    assert sample["target"] == "Rome"
