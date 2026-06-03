from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from worker.productization import (
    AcceptanceRunConfig,
    OpenAICompatibleVisionClient,
    run_swift_vision_real_model_acceptance,
)
from worker.productization import swift_vision_real_model_acceptance as acceptance_module
from worker.productization.swift_vision_real_model_acceptance import (
    SWIFT_VISION_DETERMINISTIC_TEMPERATURE,
    SWIFT_VISION_REAL_MODEL_ACCEPTANCE_MANIFEST_SCHEMA_VERSION,
    _assistant_content,
    _bounded_float,
    _default_transport,
    _frozen_baseline_ready,
    _media_index,
    _mean,
    _read_json,
    _read_jsonl as _module_read_jsonl,
    _resolve_manifest_path,
    _sample_media,
    _target_dicts,
    _target_model_id,
    _validate_manifest_schema,
    main,
)


class FakeVisionClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def generate(self, request: dict[str, object]) -> dict[str, object]:
        self.requests.append(request)
        return {
            "status": "ok",
            "model_answer": "The sign says BAY-17.",
            "route_receipt": {
                "worker_family": "vision",
                "worker_instance_id": "swift-vision-worker-real",
            },
            "runtime_receipts": {
                "vision_payload_receipt": "receipts/vision-payload.jsonl",
            },
            "latency_ms": 12.5,
        }


class FakeJudge:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
        self.requests.append(request)
        return {
            "equivalent": True,
            "confidence": 0.93,
            "reason_code": "same_answer",
            "short_reason": "The answer identifies BAY-17.",
        }


class FailingJudge:
    def judge_semantic_equivalence(self, _request: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("judge down")


class ExactVisionClient:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    def generate(self, _request: dict[str, object]) -> dict[str, object]:
        return {
            "status": "ok",
            "model_answer": self.answer,
            "latency_ms": 1.5,
        }


def test_missing_prerequisites_write_blocked_acceptance_artifacts(tmp_path: Path) -> None:
    missing_model_path = tmp_path / "missing_gemma4"
    manifest_path = _write_manifest(
        tmp_path,
        baseline_path="baselines/gemma4-image.json",
        media_path="media/missing.ppm",
        model_path=str(missing_model_path),
        judge_required=True,
    )
    samples_path = _write_samples(tmp_path)
    output_dir = tmp_path / "run"

    result = run_swift_vision_real_model_acceptance(
        AcceptanceRunConfig(
            manifest_path=manifest_path,
            samples_path=samples_path,
            output_dir=output_dir,
            repo_root=tmp_path,
            swift_vision_base_url="",
            judge_remote_server_id="",
            judge_model_id="",
            repo_git_sha="abc123",
        )
    )

    assert result.status == "blocked"
    assert result.blocked_count == 1
    assert result.summary_path == output_dir / "summary.json"
    assert result.blocked_artifact_paths == (
        output_dir / "blocked" / "gemma4_vlm.native_video__image.json",
    )
    blocked = json.loads(result.blocked_artifact_paths[0].read_text())
    assert blocked["status"] == "blocked"
    assert blocked["gate"] == "real_model_vision_acceptance"
    assert blocked["family_id"] == "gemma4_vlm.native_video"
    assert blocked["modality_suite"] == "image"
    assert blocked["model_id"] == "unsloth/gemma-4-E4B-it-MLX-8bit"
    assert blocked["repo_git_sha"] == "abc123"
    assert blocked["fixture_manifest_hash"].startswith("sha256:")
    assert set(blocked["missing_prerequisites"]) == {
        "model_weights",
        "judge_target",
        "fixture_media",
        "frozen_python_baseline",
        "swift_vision_endpoint",
    }
    assert blocked["expected_paths_or_ids"]["model_weights"] == str(missing_model_path)
    assert blocked["detected_paths_or_ids"]["model_weights"] == ""
    assert "Provide local model weights" in blocked["remediation_hint"]

    summary = json.loads(result.summary_path.read_text())
    assert summary["status"] == "blocked"
    assert summary["blocked_count"] == 1
    assert summary["passed_count"] == 0
    assert summary["schema_version"] == "melix.swift_vision_real_model_acceptance.summary.v1"


def test_swift_vision_real_model_acceptance_exports_public_productization_entrypoints() -> None:
    assert AcceptanceRunConfig.__name__ == "AcceptanceRunConfig"
    assert OpenAICompatibleVisionClient.__name__ == "OpenAICompatibleVisionClient"
    assert callable(run_swift_vision_real_model_acceptance)
    config = AcceptanceRunConfig(
        manifest_path=Path("manifest.json"),
        samples_path=Path("samples.jsonl"),
        output_dir=Path("run"),
        repo_root=Path("."),
        swift_vision_base_url="http://127.0.0.1:12436/v1",
        swift_vision_api_key="swift-secret",
        judge_api_key="judge-secret",
    )
    assert "swift-secret" not in repr(config)
    assert "judge-secret" not in repr(config)


def test_judge_backed_semantic_acceptance_persists_prompt_audit_summary_and_cache(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "models" / "gemma4"
    model_dir.mkdir(parents=True)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "card.ppm").write_bytes(b"P6\n1 1\n255\n\x00\x00\x00")
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    (baseline_dir / "gemma4-image.json").write_text(
        json.dumps(
            {
                "status": "frozen",
                "python_worker_git_sha": "py-sha",
                "model_id": "unsloth/gemma-4-E4B-it-MLX-8bit",
                "scores": {
                    "gemma4_vlm.native_video": {
                        "image": 0.91,
                    },
                },
            }
        )
    )
    manifest_path = _write_manifest(
        tmp_path,
        baseline_path="baselines/gemma4-image.json",
        media_path="media/card.ppm",
        model_path=str(model_dir),
        judge_required=True,
    )
    samples_path = _write_samples(tmp_path, duplicate=True)
    output_dir = tmp_path / "run"
    vision = FakeVisionClient()
    judge = FakeJudge()

    result = run_swift_vision_real_model_acceptance(
        AcceptanceRunConfig(
            manifest_path=manifest_path,
            samples_path=samples_path,
            output_dir=output_dir,
            repo_root=tmp_path,
            swift_vision_base_url="http://127.0.0.1:12436/v1",
            judge_remote_server_id="judge-local",
            judge_model_id="judge-model",
            repo_git_sha="abc123",
        ),
        vision_client=vision,
        judge=judge,
    )

    assert result.status == "passed"
    assert result.passed_count == 1
    assert result.blocked_count == 0
    assert len(vision.requests) == 2
    assert len(judge.requests) == 1

    summary = json.loads(result.summary_path.read_text())
    assert summary["status"] == "passed"
    assert summary["families"]["gemma4_vlm.native_video"]["image"]["swift_score"] == 1.0
    assert summary["families"]["gemma4_vlm.native_video"]["image"]["python_baseline_score"] == 0.91
    assert summary["semantic_judge"]["calls"] == 1
    assert summary["semantic_judge"]["cache_hits"] == 1
    assert summary["artifacts"]["judge_prompt_snapshots"] == "judge/prompt-snapshots.jsonl"
    assert summary["artifacts"]["judge_audit"] == "judge/audit.jsonl"
    assert summary["artifacts"]["sample_scores"] == "scores/sample-scores.jsonl"

    prompt_snapshots = _read_jsonl(output_dir / "judge" / "prompt-snapshots.jsonl")
    assert len(prompt_snapshots) == 1
    assert prompt_snapshots[0]["judge_remote_server_id"] == "judge-local"
    assert prompt_snapshots[0]["judge_model_id"] == "judge-model"
    assert prompt_snapshots[0]["prompt_hash"].startswith("sha256:")

    audit_rows = _read_jsonl(output_dir / "judge" / "audit.jsonl")
    assert [row["source"] for row in audit_rows] == ["judge", "cache"]
    assert audit_rows[0]["sample_id"] == "gemma4-image-1"
    assert audit_rows[0]["typed_score"] == 1.0
    assert audit_rows[1]["judge_source"] == "cache"

    sample_scores = _read_jsonl(output_dir / "scores" / "sample-scores.jsonl")
    assert len(sample_scores) == 2
    assert all(row["passed"] is True for row in sample_scores)
    assert sample_scores[0]["route_receipt"]["worker_family"] == "vision"


def test_empty_media_path_or_checksum_blocks_fixture_media(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "gemma4"
    model_dir.mkdir(parents=True)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "card.ppm").write_bytes(b"P6\n1 1\n255\n\x00\x00\x00")
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    (baseline_dir / "gemma4-image.json").write_text(
        json.dumps(
            {
                "status": "frozen",
                "python_worker_git_sha": "py-sha",
                "scores": {"gemma4_vlm.native_video": {"image": 0.91}},
            }
        )
    )
    samples_path = _write_samples(tmp_path)

    empty_path_manifest = _write_manifest(
        tmp_path / "empty-path",
        baseline_path="../baselines/gemma4-image.json",
        media_path="",
        model_path=str(model_dir),
        judge_required=False,
    )
    empty_path_result = run_swift_vision_real_model_acceptance(
        AcceptanceRunConfig(
            manifest_path=empty_path_manifest,
            samples_path=samples_path,
            output_dir=tmp_path / "run-empty-path",
            repo_root=tmp_path,
            swift_vision_base_url="http://127.0.0.1:12436/v1",
            repo_git_sha="abc123",
        )
    )
    assert empty_path_result.status == "blocked"
    empty_path_blocked = json.loads(empty_path_result.blocked_artifact_paths[0].read_text())
    assert empty_path_blocked["missing_prerequisites"] == ["fixture_media"]

    empty_sha_manifest = _write_manifest(
        tmp_path / "empty-sha",
        baseline_path="../baselines/gemma4-image.json",
        media_path="../media/card.ppm",
        media_sha256="",
        model_path=str(model_dir),
        judge_required=False,
    )
    empty_sha_result = run_swift_vision_real_model_acceptance(
        AcceptanceRunConfig(
            manifest_path=empty_sha_manifest,
            samples_path=samples_path,
            output_dir=tmp_path / "run-empty-sha",
            repo_root=tmp_path,
            swift_vision_base_url="http://127.0.0.1:12436/v1",
            repo_git_sha="abc123",
        )
    )
    assert empty_sha_result.status == "blocked"
    empty_sha_blocked = json.loads(empty_sha_result.blocked_artifact_paths[0].read_text())
    assert empty_sha_blocked["missing_prerequisites"] == ["fixture_media"]


def test_openai_compatible_vision_client_builds_multimodal_request_and_parses_response() -> None:
    captured: dict[str, object] = {}

    def transport(url: str, body: bytes, headers: dict[str, str], timeout_seconds: float) -> dict[str, object]:
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout_seconds"] = timeout_seconds
        captured["body"] = json.loads(body)
        return {
            "choices": [
                {
                    "message": {
                        "content": "A black pixel.",
                    },
                }
            ],
            "usage": {"prompt_tokens": 7, "completion_tokens": 4},
        }

    client = OpenAICompatibleVisionClient(
        base_url="http://127.0.0.1:12436/v1/",
        api_key="local-key",
        timeout_seconds=9.0,
        temperature=0.2,
        transport=transport,
    )
    response = client.generate(
        {
            "sample_id": "sample-1",
            "model_id": "melix-dev-vlm",
            "prompt": "Describe the media.",
            "media": [
                {
                    "media_id": "image-1",
                    "kind": "image",
                    "path": "/tmp/image.ppm",
                    "mime_type": "image/x-portable-pixmap",
                },
                {
                    "media_id": "video-1",
                    "kind": "video",
                    "path": "/tmp/clip.mp4",
                    "mime_type": "video/mp4",
                    "frame_budget": 4,
                },
            ],
        }
    )

    assert captured["url"] == "http://127.0.0.1:12436/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer local-key"
    body = captured["body"]
    assert body["model"] == "melix-dev-vlm"
    assert body["temperature"] == 0.2
    content = body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "Describe the media."}
    assert content[1]["type"] == "input_image"
    assert content[1]["input_image"]["url"] == "/tmp/image.ppm"
    assert content[2]["type"] == "input_video"
    assert content[2]["input_video"]["url"] == "/tmp/clip.mp4"
    assert content[2]["input_video"]["frame_budget"] == 4
    assert response["status"] == "ok"
    assert response["model_answer"] == "A black pixel."
    assert response["usage"] == {"prompt_tokens": 7, "completion_tokens": 4}

    default_client = OpenAICompatibleVisionClient(
        base_url="http://127.0.0.1:12436/v1",
        transport=transport,
    )
    default_client.generate({"model_id": "melix-dev-vlm", "prompt": "Describe the media."})
    assert captured["body"]["temperature"] == SWIFT_VISION_DETERMINISTIC_TEMPERATURE


def test_exact_match_acceptance_can_fail_critical_sentinel_and_records_failed_summary(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "models" / "gemma4"
    model_dir.mkdir(parents=True)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "card.ppm").write_bytes(b"P6\n1 1\n255\n\x00\x00\x00")
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    (baseline_dir / "gemma4-image.json").write_text(
        json.dumps(
            {
                "status": "frozen",
                "python_worker_git_sha": "py-sha",
                "scores": {"gemma4_vlm.native_video": {"image": 0.9}},
            }
        )
    )
    manifest_path = _write_manifest(
        tmp_path,
        baseline_path="baselines/gemma4-image.json",
        media_path="media/card.ppm",
        model_path=str(model_dir),
        judge_required=False,
        scoring_mode="normalized_exact_match",
    )
    samples_path = _write_samples(
        tmp_path,
        scoring_mode="normalized_exact_match",
        critical_sentinel=True,
        prompt_field="question",
        include_model_id=False,
    )

    result = run_swift_vision_real_model_acceptance(
        AcceptanceRunConfig(
            manifest_path=manifest_path,
            samples_path=samples_path,
            output_dir=tmp_path / "run",
            repo_root=tmp_path,
            swift_vision_base_url="http://127.0.0.1:12436/v1",
            repo_git_sha="abc123",
        ),
        vision_client=ExactVisionClient("wrong answer"),
    )

    assert result.status == "failed"
    assert result.failed_count == 1
    summary = json.loads(result.summary_path.read_text())
    suite = summary["families"]["gemma4_vlm.native_video"]["image"]
    assert suite["status"] == "failed"
    assert suite["critical_failures"] == 1
    assert suite["swift_score"] == 0.0
    sample_scores = _read_jsonl(tmp_path / "run" / "scores" / "sample-scores.jsonl")
    assert sample_scores[0]["judge_decision"]["reason_code"] == "no_exact_match"


def test_judge_failure_records_failed_audit_and_failed_summary(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "gemma4"
    model_dir.mkdir(parents=True)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "card.ppm").write_bytes(b"P6\n1 1\n255\n\x00\x00\x00")
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    (baseline_dir / "gemma4-image.json").write_text(
        json.dumps(
            {
                "status": "frozen",
                "python_worker_git_sha": "py-sha",
                "scores": {"gemma4_vlm.native_video": {"image": 0.0}},
            }
        )
    )
    manifest_path = _write_manifest(
        tmp_path,
        baseline_path="baselines/gemma4-image.json",
        media_path="media/card.ppm",
        model_path=str(model_dir),
        judge_required=True,
    )
    samples_path = _write_samples(tmp_path)

    result = run_swift_vision_real_model_acceptance(
        AcceptanceRunConfig(
            manifest_path=manifest_path,
            samples_path=samples_path,
            output_dir=tmp_path / "run",
            repo_root=tmp_path,
            swift_vision_base_url="http://127.0.0.1:12436/v1",
            judge_remote_server_id="judge-local",
            judge_model_id="judge-model",
            repo_git_sha="abc123",
        ),
        vision_client=FakeVisionClient(),
        judge=FailingJudge(),
    )

    assert result.status == "failed"
    audit_rows = _read_jsonl(tmp_path / "run" / "judge" / "audit.jsonl")
    assert audit_rows[0]["status"] == "failed"
    assert audit_rows[0]["reason_code"] == "judge_error"
    assert audit_rows[0]["failure_reason"] == "judge down"


def test_manifest_loader_ignores_unsupported_suites_and_empty_shapes(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        baseline_path="baselines/missing.json",
        media_path="media/missing.ppm",
        model_path="",
        judge_required=False,
        unsupported_suite=True,
    )
    _write_samples(tmp_path)

    result = run_swift_vision_real_model_acceptance(
        AcceptanceRunConfig(
            manifest_path=manifest_path,
            samples_path=tmp_path / "samples.jsonl",
            output_dir=tmp_path / "run",
            repo_root=tmp_path,
            swift_vision_base_url="",
            repo_git_sha="abc123",
        )
    )

    assert result.status == "passed"
    assert result.passed_count == 0
    assert _target_dicts({"model_family_targets": "bad"}) == []
    assert _target_model_id({"model_id": "fallback-model"}) == "fallback-model"
    assert _media_index({"media_artifacts": "bad"}, base_dir=tmp_path) == {}
    assert _sample_media({"media_ids": "bad"}, {}) == []


def test_main_returns_success_for_passing_run_and_constructs_remote_judge(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        baseline_path="baselines/missing.json",
        media_path="media/missing.ppm",
        model_path="",
        judge_required=False,
        unsupported_suite=True,
    )
    _write_samples(tmp_path)
    observed: dict[str, object] = {}

    class MainJudge(FakeJudge):
        pass

    def fake_make_semantic_judge_client(target):
        observed["target"] = target
        return MainJudge()

    monkeypatch.setattr(acceptance_module, "make_semantic_judge_client", fake_make_semantic_judge_client)

    rc = main(
        [
            "--manifest",
            str(manifest_path),
            "--samples",
            str(tmp_path / "samples.jsonl"),
            "--output-dir",
            str(tmp_path / "run"),
            "--repo-root",
            str(tmp_path),
            "--swift-vision-base-url",
            "http://127.0.0.1:12436/v1",
            "--swift-vision-api-key",
            "local-key",
            "--timeout-seconds",
            "7",
            "--judge-remote-server-id",
            "judge-local",
            "--judge-model-id",
            "judge-model",
            "--judge-base-url",
            "http://judge.local/v1",
            "--judge-api-key",
            "judge-key",
            "--judge-timeout-seconds",
            "11",
            "--judge-rate-limit-per-minute",
            "3",
        ]
    )

    assert rc == 0
    target = observed["target"]
    assert target.base_url == "http://judge.local/v1"
    assert target.model_id == "judge-model"
    assert target.timeout_seconds == 11
    assert target.rate_limit_per_minute == 3


def test_openai_client_and_transport_cover_error_and_fallback_branches(monkeypatch) -> None:
    client = OpenAICompatibleVisionClient(base_url="")
    try:
        client.generate({"model_id": "m", "prompt": ""})
    except ValueError as exc:
        assert "base_url is empty" in str(exc)
    else:
        raise AssertionError("expected empty base url to fail")

    assert _assistant_content({"choices": []}) == ""
    assert _assistant_content({"choices": ["bad"]}) == ""
    assert _assistant_content({"choices": [{"message": {"content": [{"text": "A"}, {"text": "B"}]}}]}) == "AB"
    assert _assistant_content({"choices": [{"text": "fallback"}]}) == "fallback"

    class FakeHTTPError(HTTPError):
        def read(self) -> bytes:
            return b"bad request"

    def raise_http(_request, timeout):
        raise FakeHTTPError("http://x", 400, "bad", {}, None)

    monkeypatch.setattr(acceptance_module, "urlopen", raise_http)
    try:
        _default_transport("http://x", b"{}", {}, 1.0)
    except RuntimeError as exc:
        assert "HTTP 400" in str(exc)
    else:
        raise AssertionError("expected HTTPError to be wrapped")

    def raise_url(_request, timeout):
        raise URLError("offline")

    monkeypatch.setattr(acceptance_module, "urlopen", raise_url)
    try:
        _default_transport("http://x", b"{}", {}, 1.0)
    except RuntimeError as exc:
        assert "offline" in str(exc)
    else:
        raise AssertionError("expected URLError to be wrapped")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            return False

        def read(self) -> bytes:
            return b"[]"

    monkeypatch.setattr(acceptance_module, "urlopen", lambda _request, timeout: FakeResponse())
    try:
        _default_transport("http://x", b"{}", {}, 1.0)
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("expected non-object response to fail")


def test_validation_and_helper_fallbacks(tmp_path: Path) -> None:
    try:
        _validate_manifest_schema({})
    except ValueError as exc:
        assert "schema mismatch" in str(exc)
    else:
        raise AssertionError("expected schema mismatch")

    non_object = tmp_path / "array.json"
    non_object.write_text("[]")
    try:
        _read_json(non_object)
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("expected JSON object validation")

    jsonl = tmp_path / "rows.jsonl"
    jsonl.write_text("\n[]\n")
    try:
        _module_read_jsonl(jsonl)
    except ValueError as exc:
        assert ":2" in str(exc)
    else:
        raise AssertionError("expected JSONL object validation")

    assert _bounded_float(True) == 0.0
    assert _bounded_float(2.5) == 1.0
    assert _mean([]) == 0.0
    assert _resolve_manifest_path(tmp_path, "") == ""
    absolute_path = str(tmp_path.resolve())
    assert _resolve_manifest_path(tmp_path, absolute_path) == absolute_path
    assert _frozen_baseline_ready(tmp_path / "missing.json") is False
    assert _frozen_baseline_ready(tmp_path) is False
    bad_baseline = tmp_path / "bad-baseline.json"
    bad_baseline.write_text("[]")
    assert _frozen_baseline_ready(bad_baseline) is False


def _write_manifest(
    root: Path,
    *,
    baseline_path: str,
    media_path: str,
    model_path: str,
    judge_required: bool,
    media_sha256: str = "sha256:test",
    scoring_mode: str = "judge_backed_semantic",
    unsupported_suite: bool = False,
) -> Path:
    manifest = {
        "schema_version": SWIFT_VISION_REAL_MODEL_ACCEPTANCE_MANIFEST_SCHEMA_VERSION,
        "fixture_suite_id": "swift-vision-real-model.dev.v1",
        "scoring_policy": {
            "absolute_floor": 0.70,
            "allowed_delta": 0.05,
            "critical_sentinel_score": 1.0,
        },
        "model_family_targets": [
            {
                "family_id": "gemma4_vlm.native_video",
                "accepted_model_ids": ["unsloth/gemma-4-E4B-it-MLX-8bit"],
                "modality_suites": {
                    "image": {
                        "supported": not unsupported_suite,
                        "minimum_acceptance_cases": 1,
                        "scoring_mode": scoring_mode,
                        "judge_required": judge_required,
                        "python_baseline_path": baseline_path,
                    }
                },
                "model_weights_path": model_path,
                "required_runtime_features": ["swift_vision_worker"],
                "required_route": {
                    "worker_family": "vision",
                    "supports_native_video": True,
                },
            }
        ],
        "media_artifacts": [
            {
                "media_id": "query-card",
                "path": media_path,
                "sha256": media_sha256,
                "mime_type": "image/x-portable-pixmap",
            }
        ],
    }
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def _write_samples(
    root: Path,
    *,
    duplicate: bool = False,
    scoring_mode: str = "judge_backed_semantic",
    critical_sentinel: bool = False,
    prompt_field: str = "prompt",
    include_model_id: bool = True,
) -> Path:
    sample = {
        "sample_id": "gemma4-image-1",
        "family_id": "gemma4_vlm.native_video",
        "modality_suite": "image",
        "expected_answer": "BAY-17",
        "rubric": "The answer must identify BAY-17.",
        "media_ids": ["query-card"],
        "scoring_mode": scoring_mode,
    }
    sample[prompt_field] = "Read the card."
    if critical_sentinel:
        sample["critical_sentinel"] = True
    if include_model_id:
        sample["model_id"] = "unsloth/gemma-4-E4B-it-MLX-8bit"
    rows = [sample, dict(sample)] if duplicate else [sample]
    path = root / "samples.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    return path


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]
