from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from worker.productization.event_extraction import (
    RemoteSemanticJudgeTarget,
    make_semantic_judge_client,
)


SWIFT_VISION_REAL_MODEL_ACCEPTANCE_MANIFEST_SCHEMA_VERSION = (
    "melix.swift_vision_real_model_acceptance_manifest.v1"
)
SWIFT_VISION_REAL_MODEL_ACCEPTANCE_SUMMARY_SCHEMA_VERSION = (
    "melix.swift_vision_real_model_acceptance.summary.v1"
)
SWIFT_VISION_BLOCKED_ACCEPTANCE_SCHEMA_VERSION = (
    "melix.swift_vision_blocked_acceptance_artifact.v1"
)
SWIFT_VISION_JUDGE_PROMPT_SNAPSHOT_SCHEMA_VERSION = (
    "melix.swift_vision_judge_prompt_snapshot.v1"
)
SWIFT_VISION_JUDGE_AUDIT_SCHEMA_VERSION = "melix.swift_vision_judge_audit.v1"
SWIFT_VISION_SAMPLE_SCORE_SCHEMA_VERSION = "melix.swift_vision_sample_score.v1"
SWIFT_VISION_JUDGE_PROMPT_VERSION = "swift-vision-real-model-acceptance.v1"
SWIFT_VISION_JUDGE_SYSTEM_PROMPT = """You are a semantic judge for Melix Swift Vision real-model acceptance.

Judge whether the model answer satisfies the expected answer or rubric using only
the supplied fixture sample metadata, media references, runtime receipts, and
model answer. Return JSON with equivalent, confidence, reason_code, and
short_reason. Do not use hidden context or external knowledge.
"""
SWIFT_VISION_JUDGE_PROMPT_HASH = (
    f"sha256:{sha256(SWIFT_VISION_JUDGE_SYSTEM_PROMPT.encode('utf-8')).hexdigest()}"
)
SWIFT_VISION_DETERMINISTIC_TEMPERATURE = 0.0
SWIFT_VISION_STRICT_JUDGE_FAILURE_POLICY = True


VisionTransport = Callable[[str, bytes, dict[str, str], float], dict[str, object]]


@dataclass(frozen=True)
class AcceptanceRunConfig:
    manifest_path: Path
    samples_path: Path
    output_dir: Path
    repo_root: Path
    swift_vision_base_url: str
    swift_vision_api_key: str = field(default="", repr=False)
    judge_remote_server_id: str = ""
    judge_model_id: str = ""
    judge_provider_kind: str = "openai-compatible"
    judge_base_url: str = ""
    judge_api_key: str = field(default="", repr=False)
    judge_timeout_seconds: float = 60.0
    judge_rate_limit_per_minute: int = 0
    timeout_seconds: float = 120.0
    repo_git_sha: str = ""


@dataclass(frozen=True)
class AcceptanceRunResult:
    status: str
    summary_path: Path
    passed_count: int
    failed_count: int
    blocked_count: int
    blocked_artifact_paths: tuple[Path, ...]


class OpenAICompatibleVisionClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout_seconds: float = 120.0,
        temperature: float = SWIFT_VISION_DETERMINISTIC_TEMPERATURE,
        transport: VisionTransport | None = None,
    ) -> None:
        self._base_url = base_url.strip().rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._transport = transport or _default_transport

    def generate(self, request: dict[str, object]) -> dict[str, object]:
        if not self._base_url:
            raise ValueError("swift vision base_url is empty")
        body = {
            "model": _required_text(request, "model_id"),
            "stream": False,
            "temperature": self._temperature,
            "messages": [
                {
                    "role": "user",
                    "content": _openai_content_parts(request),
                }
            ],
        }
        encoded = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "OpenAI/Python 1.0.0 Melix/0.1",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        started = time.perf_counter()
        response = self._transport(
            f"{self._base_url}/chat/completions",
            encoded,
            headers,
            self._timeout_seconds,
        )
        latency_ms = (time.perf_counter() - started) * 1_000.0
        return {
            "status": "ok",
            "model_answer": _assistant_content(response),
            "usage": response.get("usage", {}) if isinstance(response.get("usage"), dict) else {},
            "latency_ms": round(latency_ms, 4),
            "raw_response_id": str(response.get("id") or ""),
        }


class _SemanticJudgeRuntime:
    def __init__(
        self,
        *,
        judge: object,
        judge_remote_server_id: str,
        judge_model_id: str,
    ) -> None:
        self.judge = judge
        self.judge_remote_server_id = judge_remote_server_id
        self.judge_model_id = judge_model_id
        self.calls = 0
        self.cache_hits = 0
        self.failures = 0
        self.cache: dict[str, dict[str, object]] = {}
        self.audit_rows: list[dict[str, object]] = []
        self.prompt_snapshots: list[dict[str, object]] = []
        self._prompt_snapshot_keys: set[str] = set()

    def decide(self, request: dict[str, object]) -> dict[str, object]:
        self._record_prompt_snapshot(request)
        cache_key = _semantic_judge_cache_key(request)
        if cache_key in self.cache:
            self.cache_hits += 1
            decision = dict(self.cache[cache_key])
            self.audit_rows.append(
                _judge_audit_row(
                    request=request,
                    decision=decision,
                    cache_key=cache_key,
                    source="cache",
                    status="ok",
                    error_code="",
                    failure_reason="",
                )
            )
            return decision

        self.calls += 1
        try:
            raw_decision = getattr(self.judge, "judge_semantic_equivalence")(request)
            decision = _normalize_judge_decision(raw_decision)
            self.cache[cache_key] = decision
            self.audit_rows.append(
                _judge_audit_row(
                    request=request,
                    decision=decision,
                    cache_key=cache_key,
                    source="judge",
                    status="ok",
                    error_code="",
                    failure_reason="",
                )
            )
            return decision
        except Exception as exc:  # noqa: BLE001
            self.failures += 1
            decision = {
                "equivalent": False,
                "confidence": 0.0,
                "reason_code": str(getattr(exc, "code", "judge_error")),
                "short_reason": _failure_reason(exc),
            }
            self.audit_rows.append(
                _judge_audit_row(
                    request=request,
                    decision=decision,
                    cache_key=cache_key,
                    source="judge",
                    status="failed",
                    error_code=str(getattr(exc, "code", "judge_error")),
                    failure_reason=_failure_reason(exc),
                )
            )
            return decision

    def _record_prompt_snapshot(self, request: dict[str, object]) -> None:
        snapshot_key = str(request.get("sample_id") or "")
        if snapshot_key in self._prompt_snapshot_keys:
            return
        self._prompt_snapshot_keys.add(snapshot_key)
        user_payload = {
            key: request.get(key)
            for key in (
                "sample_id",
                "family_id",
                "modality_suite",
                "model_id",
                "expected_answer",
                "rubric",
                "model_answer",
                "media",
                "route_receipt",
                "runtime_receipts",
            )
        }
        self.prompt_snapshots.append(
            {
                "schema_version": SWIFT_VISION_JUDGE_PROMPT_SNAPSHOT_SCHEMA_VERSION,
                "sample_id": snapshot_key,
                "judge_remote_server_id": self.judge_remote_server_id,
                "judge_model_id": self.judge_model_id,
                "prompt_version": SWIFT_VISION_JUDGE_PROMPT_VERSION,
                "prompt_hash": SWIFT_VISION_JUDGE_PROMPT_HASH,
                "system_prompt_hash": SWIFT_VISION_JUDGE_PROMPT_HASH,
                "user_payload_hash": _hash_payload(user_payload),
            }
        )


def run_swift_vision_real_model_acceptance(
    config: AcceptanceRunConfig,
    *,
    vision_client: object | None = None,
    judge: object | None = None,
) -> AcceptanceRunResult:
    manifest = _read_json(config.manifest_path)
    _validate_manifest_schema(manifest)
    samples = _read_jsonl(config.samples_path)
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_hash = _hash_file(config.manifest_path)
    repo_git_sha = config.repo_git_sha.strip() or _infer_git_sha(config.repo_root)
    media_index = _media_index(manifest, base_dir=config.manifest_path.parent)

    blocked_artifacts: list[Path] = []
    target_results: dict[str, dict[str, dict[str, object]]] = {}
    sample_scores: list[dict[str, object]] = []
    client = vision_client or OpenAICompatibleVisionClient(
        base_url=config.swift_vision_base_url,
        api_key=config.swift_vision_api_key,
        timeout_seconds=config.timeout_seconds,
    )
    judge_runtime = _build_judge_runtime(config, judge=judge)

    for target in _target_dicts(manifest):
        family_id = _required_text(target, "family_id")
        model_id = _target_model_id(target)
        for suite_id, suite in _suite_items(target):
            if not bool(suite.get("supported", False)):
                continue
            missing = _missing_prerequisites(
                config=config,
                target=target,
                suite=suite,
                media_index=media_index,
                samples=_samples_for(samples, family_id=family_id, suite_id=suite_id),
            )
            if missing:
                path = _write_blocked_artifact(
                    output_dir,
                    gate="real_model_vision_acceptance",
                    family_id=family_id,
                    modality_suite=suite_id,
                    model_id=model_id,
                    missing=missing,
                    config=config,
                    target=target,
                    suite=suite,
                    repo_git_sha=repo_git_sha,
                    manifest_hash=manifest_hash,
                )
                blocked_artifacts.append(path)
                _record_target_result(
                    target_results,
                    family_id,
                    suite_id,
                    {
                        "status": "blocked",
                        "model_id": model_id,
                        "missing_prerequisites": missing,
                    },
                )
                continue

            suite_samples = _samples_for(samples, family_id=family_id, suite_id=suite_id)
            suite_scores: list[float] = []
            critical_failures = 0
            for sample in suite_samples:
                sample_media = _sample_media(sample, media_index)
                request = {
                    "sample_id": _required_text(sample, "sample_id"),
                    "family_id": family_id,
                    "modality_suite": suite_id,
                    "model_id": _sample_model_id(sample, model_id),
                    "prompt": _sample_prompt(sample),
                    "media": sample_media,
                }
                runtime_result = getattr(client, "generate")(request)
                scoring_result = _score_sample(
                    sample=sample,
                    family_id=family_id,
                    suite_id=suite_id,
                    runtime_result=runtime_result,
                    media=sample_media,
                    judge_runtime=judge_runtime,
                )
                suite_scores.append(float(scoring_result["score"]))
                if bool(sample.get("critical_sentinel", False)) and not bool(scoring_result["passed"]):
                    critical_failures += 1
                sample_scores.append(scoring_result)

            swift_score = _mean(suite_scores)
            baseline_score = _baseline_score(
                config.manifest_path.parent / _required_text(suite, "python_baseline_path"),
                family_id=family_id,
                suite_id=suite_id,
            )
            absolute_floor = _policy_float(manifest, "absolute_floor", default=0.70)
            allowed_delta = _policy_float(manifest, "allowed_delta", default=0.05)
            judge_failure_free = (
                not SWIFT_VISION_STRICT_JUDGE_FAILURE_POLICY
                or (judge_runtime.failures if judge_runtime else 0) == 0
            )
            passed = (
                swift_score >= absolute_floor
                and swift_score >= baseline_score - allowed_delta
                and critical_failures == 0
                and judge_failure_free
            )
            _record_target_result(
                target_results,
                family_id,
                suite_id,
                {
                    "status": "passed" if passed else "failed",
                    "model_id": model_id,
                    "sample_count": len(suite_samples),
                    "swift_score": round(swift_score, 6),
                    "python_baseline_score": round(baseline_score, 6),
                    "absolute_floor": absolute_floor,
                    "allowed_delta": allowed_delta,
                    "critical_failures": critical_failures,
                },
            )

    _write_jsonl(output_dir / "scores" / "sample-scores.jsonl", sample_scores)
    _write_jsonl(output_dir / "judge" / "prompt-snapshots.jsonl", judge_runtime.prompt_snapshots if judge_runtime else [])
    _write_jsonl(output_dir / "judge" / "audit.jsonl", judge_runtime.audit_rows if judge_runtime else [])

    failed_count = _target_status_count(target_results, "failed")
    passed_count = _target_status_count(target_results, "passed")
    blocked_count = len(blocked_artifacts)
    status = "blocked" if blocked_count else "failed" if failed_count else "passed"
    summary = {
        "schema_version": SWIFT_VISION_REAL_MODEL_ACCEPTANCE_SUMMARY_SCHEMA_VERSION,
        "status": status,
        "fixture_suite_id": str(manifest.get("fixture_suite_id") or ""),
        "manifest_path": str(config.manifest_path),
        "samples_path": str(config.samples_path),
        "fixture_manifest_hash": manifest_hash,
        "repo_git_sha": repo_git_sha,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "families": target_results,
        "semantic_judge": {
            "judge_remote_server_id": config.judge_remote_server_id,
            "judge_model_id": config.judge_model_id,
            "judge_prompt_version": SWIFT_VISION_JUDGE_PROMPT_VERSION,
            "judge_prompt_hash": SWIFT_VISION_JUDGE_PROMPT_HASH,
            "calls": judge_runtime.calls if judge_runtime else 0,
            "cache_hits": judge_runtime.cache_hits if judge_runtime else 0,
            "failures": judge_runtime.failures if judge_runtime else 0,
        },
        "artifacts": {
            "blocked": [str(path.relative_to(output_dir)) for path in blocked_artifacts],
            "sample_scores": "scores/sample-scores.jsonl",
            "judge_prompt_snapshots": "judge/prompt-snapshots.jsonl",
            "judge_audit": "judge/audit.jsonl",
        },
    }
    summary_path = output_dir / "summary.json"
    _write_json(summary_path, summary)
    return AcceptanceRunResult(
        status=status,
        summary_path=summary_path,
        passed_count=passed_count,
        failed_count=failed_count,
        blocked_count=blocked_count,
        blocked_artifact_paths=tuple(blocked_artifacts),
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    judge = None
    if args.judge_base_url:
        judge = make_semantic_judge_client(
            RemoteSemanticJudgeTarget(
                provider_kind=args.judge_provider_kind,
                base_url=args.judge_base_url,
                api_key=args.judge_api_key,
                model_id=args.judge_model_id,
                timeout_seconds=int(args.judge_timeout_seconds),
                rate_limit_per_minute=args.judge_rate_limit_per_minute,
            )
        )
    result = run_swift_vision_real_model_acceptance(
        AcceptanceRunConfig(
            manifest_path=Path(args.manifest),
            samples_path=Path(args.samples),
            output_dir=Path(args.output_dir),
            repo_root=Path(args.repo_root),
            swift_vision_base_url=args.swift_vision_base_url,
            swift_vision_api_key=args.swift_vision_api_key,
            judge_remote_server_id=args.judge_remote_server_id,
            judge_model_id=args.judge_model_id,
            judge_provider_kind=args.judge_provider_kind,
            judge_base_url=args.judge_base_url,
            judge_api_key=args.judge_api_key,
            judge_timeout_seconds=args.judge_timeout_seconds,
            judge_rate_limit_per_minute=args.judge_rate_limit_per_minute,
            timeout_seconds=args.timeout_seconds,
        ),
        judge=judge,
    )
    print(json.dumps({"status": result.status, "summary_path": str(result.summary_path)}, sort_keys=True))
    return 0 if result.status == "passed" else 2


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Swift Vision real-model acceptance fixtures.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--samples", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--swift-vision-base-url", default="")
    parser.add_argument("--swift-vision-api-key", default="")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--judge-remote-server-id", default="")
    parser.add_argument("--judge-model-id", default="")
    parser.add_argument("--judge-provider-kind", default="openai-compatible")
    parser.add_argument("--judge-base-url", default="")
    parser.add_argument("--judge-api-key", default="")
    parser.add_argument("--judge-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--judge-rate-limit-per-minute", type=int, default=0)
    return parser.parse_args(argv)


def _default_transport(
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, object]:
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_bytes = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Swift Vision endpoint returned HTTP {exc.code}: {detail[:240]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Swift Vision endpoint request failed: {exc.reason}") from exc
    parsed = json.loads(response_bytes.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Swift Vision endpoint response must be a JSON object")
    return parsed


def _openai_content_parts(request: dict[str, object]) -> list[dict[str, object]]:
    """Build multimodal content with manifest media paths passed through verbatim.

    The Swift Vision endpoint accepts local paths in the OpenAI-compatible `url`
    field. Callers targeting stricter URL validators must provide `file://` URIs
    in the manifest.
    """
    content: list[dict[str, object]] = []
    prompt = _required_text(request, "prompt")
    if prompt:
        content.append({"type": "text", "text": prompt})
    media = request.get("media")
    if not isinstance(media, list):
        return content
    for item in media:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        payload = {
            "url": _required_text(item, "path"),
            "mime_type": str(item.get("mime_type") or "").strip(),
        }
        filename = str(item.get("filename") or "").strip()
        if filename:
            payload["filename"] = filename
        frame_budget = item.get("frame_budget")
        if isinstance(frame_budget, int) and frame_budget > 0:
            payload["frame_budget"] = frame_budget
        if kind == "image":
            content.append({"type": "input_image", "input_image": payload})
        elif kind == "video":
            content.append({"type": "input_video", "input_video": payload})
    return content


def _assistant_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict)
            ).strip()
    text = first.get("text")
    return str(text or "").strip()


def _validate_manifest_schema(manifest: dict[str, object]) -> None:
    schema = str(manifest.get("schema_version") or "")
    if schema != SWIFT_VISION_REAL_MODEL_ACCEPTANCE_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            "Swift Vision real-model acceptance manifest schema mismatch: "
            f"{schema or '<missing>'}"
        )


def _target_dicts(manifest: dict[str, object]) -> list[dict[str, object]]:
    raw = manifest.get("model_family_targets")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _suite_items(target: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    raw = target.get("modality_suites")
    if not isinstance(raw, dict):
        return []
    return [
        (str(key), value)
        for key, value in raw.items()
        if isinstance(value, dict)
    ]


def _target_model_id(target: dict[str, object]) -> str:
    model_ids = target.get("accepted_model_ids")
    if isinstance(model_ids, list):
        for model_id in model_ids:
            if isinstance(model_id, str) and model_id.strip():
                return model_id.strip()
    return str(target.get("model_id") or "").strip()


def _sample_model_id(sample: dict[str, object], fallback: str) -> str:
    model_id = str(sample.get("model_id") or "").strip()
    return model_id or fallback


def _sample_prompt(sample: dict[str, object]) -> str:
    prompt = str(sample.get("prompt") or "").strip()
    if prompt:
        return prompt
    return str(sample.get("question") or "").strip()


def _samples_for(
    samples: list[dict[str, object]],
    *,
    family_id: str,
    suite_id: str,
) -> list[dict[str, object]]:
    return [
        sample
        for sample in samples
        if str(sample.get("family_id") or "").strip() == family_id
        and str(sample.get("modality_suite") or "").strip() == suite_id
    ]


def _media_index(
    manifest: dict[str, object],
    *,
    base_dir: Path,
) -> dict[str, dict[str, object]]:
    media = manifest.get("media_artifacts")
    if not isinstance(media, list):
        return {}
    indexed: dict[str, dict[str, object]] = {}
    for item in media:
        if not isinstance(item, dict):
            continue
        media_id = str(item.get("media_id") or "").strip()
        if not media_id:
            continue
        payload = dict(item)
        path = str(payload.get("path") or "").strip()
        if path and not Path(path).is_absolute():
            payload["path"] = str(base_dir / path)
        indexed[media_id] = payload
    return indexed


def _sample_media(
    sample: dict[str, object],
    media_index: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    media_ids = sample.get("media_ids")
    if not isinstance(media_ids, list):
        return []
    result: list[dict[str, object]] = []
    for media_id in media_ids:
        if not isinstance(media_id, str):
            continue
        media = media_index.get(media_id.strip())
        if media is not None:
            result.append(dict(media))
    return result


def _missing_prerequisites(
    *,
    config: AcceptanceRunConfig,
    target: dict[str, object],
    suite: dict[str, object],
    media_index: dict[str, dict[str, object]],
    samples: list[dict[str, object]],
) -> list[str]:
    missing: list[str] = []
    model_path = _resolve_manifest_path(
        config.manifest_path.parent,
        str(target.get("model_weights_path") or "").strip(),
    )
    if not model_path or not Path(model_path).expanduser().exists():
        missing.append("model_weights")
    if not config.swift_vision_base_url.strip():
        missing.append("swift_vision_endpoint")
    if bool(suite.get("judge_required", False)) and (
        not config.judge_remote_server_id.strip() or not config.judge_model_id.strip()
    ):
        missing.append("judge_target")
    baseline = _manifest_relative_path(config.manifest_path.parent, suite.get("python_baseline_path"))
    if not baseline or not _frozen_baseline_ready(Path(baseline)):
        missing.append("frozen_python_baseline")
    sample_media_ids = {
        media_id.strip()
        for sample in samples
        for media_id in sample.get("media_ids", [])
        if isinstance(media_id, str) and media_id.strip()
    }
    media_missing = False
    for media_id in sample_media_ids:
        media = media_index.get(media_id)
        if media is None:
            media_missing = True
            continue
        path = str(media.get("path") or "").strip()
        checksum = str(media.get("sha256") or "").strip()
        if not path or not Path(path).expanduser().exists() or not checksum:
            media_missing = True
    if media_missing:
        missing.append("fixture_media")
    return sorted(set(missing))


def _write_blocked_artifact(
    output_dir: Path,
    *,
    gate: str,
    family_id: str,
    modality_suite: str,
    model_id: str,
    missing: list[str],
    config: AcceptanceRunConfig,
    target: dict[str, object],
    suite: dict[str, object],
    repo_git_sha: str,
    manifest_hash: str,
) -> Path:
    path = output_dir / "blocked" / f"{family_id}__{modality_suite}.json"
    baseline = str(suite.get("python_baseline_path") or "").strip()
    resolved_baseline = _manifest_relative_path(config.manifest_path.parent, baseline)
    expected = {
        "model_weights": _resolve_manifest_path(
            config.manifest_path.parent,
            str(target.get("model_weights_path") or ""),
        ),
        "judge_target": _judge_target_id(config),
        "fixture_media": "media_artifacts referenced by samples.jsonl",
        "frozen_python_baseline": baseline,
        "swift_vision_endpoint": config.swift_vision_base_url,
    }
    detected = {
        "model_weights": _detected_path(
            _resolve_manifest_path(
                config.manifest_path.parent,
                str(target.get("model_weights_path") or ""),
            )
        ),
        "judge_target": _judge_target_id(config) if "judge_target" not in missing else "",
        "fixture_media": "present" if "fixture_media" not in missing else "",
        "frozen_python_baseline": _detected_path(resolved_baseline),
        "swift_vision_endpoint": config.swift_vision_base_url if config.swift_vision_base_url.strip() else "",
    }
    payload = {
        "schema_version": SWIFT_VISION_BLOCKED_ACCEPTANCE_SCHEMA_VERSION,
        "status": "blocked",
        "gate": gate,
        "family_id": family_id,
        "modality_suite": modality_suite,
        "model_id": model_id,
        "missing_prerequisites": missing,
        "expected_paths_or_ids": expected,
        "detected_paths_or_ids": detected,
        "remediation_hint": _remediation_hint(missing),
        "created_at": _utc_timestamp(),
        "repo_git_sha": repo_git_sha,
        "fixture_manifest_hash": manifest_hash,
    }
    _write_json(path, payload)
    return path


def _score_sample(
    *,
    sample: dict[str, object],
    family_id: str,
    suite_id: str,
    runtime_result: dict[str, object],
    media: list[dict[str, object]],
    judge_runtime: _SemanticJudgeRuntime | None,
) -> dict[str, object]:
    sample_id = _required_text(sample, "sample_id")
    scoring_mode = str(sample.get("scoring_mode") or "").strip() or "normalized_exact_match"
    model_answer = str(runtime_result.get("model_answer") or "").strip()
    if scoring_mode == "judge_backed_semantic":
        if judge_runtime is None:
            score = 0.0
            decision = {
                "equivalent": False,
                "confidence": 0.0,
                "reason_code": "judge_unavailable",
                "short_reason": "Judge target is unavailable.",
            }
        else:
            decision = judge_runtime.decide(
                {
                    "sample_id": sample_id,
                    "family_id": family_id,
                    "modality_suite": suite_id,
                    "model_id": str(sample.get("model_id") or ""),
                    "expected_answer": str(sample.get("expected_answer") or ""),
                    "rubric": str(sample.get("rubric") or ""),
                    "model_answer": model_answer,
                    "media": _redacted_media(media),
                    "route_receipt": runtime_result.get("route_receipt", {}),
                    "runtime_receipts": runtime_result.get("runtime_receipts", {}),
                }
            )
            score = 1.0 if bool(decision.get("equivalent", False)) else 0.0
    else:
        expected = str(sample.get("expected_answer") or "").strip().casefold()
        score = 1.0 if expected and expected in model_answer.casefold() else 0.0
        decision = {
            "equivalent": score == 1.0,
            "confidence": score,
            "reason_code": "normalized_exact_match" if score == 1.0 else "no_exact_match",
            "short_reason": "",
        }
    return {
        "schema_version": SWIFT_VISION_SAMPLE_SCORE_SCHEMA_VERSION,
        "sample_id": sample_id,
        "family_id": family_id,
        "modality_suite": suite_id,
        "model_id": str(sample.get("model_id") or ""),
        "scoring_mode": scoring_mode,
        "score": score,
        "passed": score >= (1.0 if bool(sample.get("critical_sentinel", False)) else 0.70),
        "model_answer": model_answer,
        "expected_answer": str(sample.get("expected_answer") or ""),
        "judge_decision": decision,
        "route_receipt": runtime_result.get("route_receipt", {}),
        "runtime_receipts": runtime_result.get("runtime_receipts", {}),
        "latency_ms": runtime_result.get("latency_ms", 0.0),
    }


def _build_judge_runtime(
    config: AcceptanceRunConfig,
    *,
    judge: object | None,
) -> _SemanticJudgeRuntime | None:
    if judge is None:
        return None
    return _SemanticJudgeRuntime(
        judge=judge,
        judge_remote_server_id=config.judge_remote_server_id,
        judge_model_id=config.judge_model_id,
    )


def _baseline_score(path: Path, *, family_id: str, suite_id: str) -> float:
    payload = _read_json(path)
    scores = payload.get("scores")
    if isinstance(scores, dict):
        family_scores = scores.get(family_id)
        if isinstance(family_scores, dict):
            value = family_scores.get(suite_id)
            if isinstance(value, int | float) and not isinstance(value, bool):
                return float(value)
    return 0.0


def _frozen_baseline_ready(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        payload = _read_json(path)
    except Exception:  # noqa: BLE001
        return False
    status = str(payload.get("status") or "").strip().lower()
    if status in {"placeholder", "blocked", "skip", "xfail"}:
        return False
    return bool(str(payload.get("python_worker_git_sha") or "").strip())


def _record_target_result(
    results: dict[str, dict[str, dict[str, object]]],
    family_id: str,
    suite_id: str,
    payload: dict[str, object],
) -> None:
    results.setdefault(family_id, {})[suite_id] = payload


def _target_status_count(results: dict[str, dict[str, dict[str, object]]], status: str) -> int:
    return sum(
        1
        for suite_results in results.values()
        for payload in suite_results.values()
        if payload.get("status") == status
    )


def _semantic_judge_cache_key(request: dict[str, object]) -> str:
    payload = {
        "judge_prompt_hash": SWIFT_VISION_JUDGE_PROMPT_HASH,
        "sample_id": request.get("sample_id", ""),
        "model_answer": request.get("model_answer", ""),
        "expected_answer": request.get("expected_answer", ""),
        "rubric": request.get("rubric", ""),
        "media": request.get("media", []),
    }
    return _hash_payload(payload)


def _judge_audit_row(
    *,
    request: dict[str, object],
    decision: dict[str, object],
    cache_key: str,
    source: str,
    status: str,
    error_code: str,
    failure_reason: str,
) -> dict[str, object]:
    typed_score = 1.0 if bool(decision.get("equivalent", False)) else 0.0
    return {
        "schema_version": SWIFT_VISION_JUDGE_AUDIT_SCHEMA_VERSION,
        "sample_id": request.get("sample_id", ""),
        "family_id": request.get("family_id", ""),
        "modality_suite": request.get("modality_suite", ""),
        "judge_prompt_version": SWIFT_VISION_JUDGE_PROMPT_VERSION,
        "judge_prompt_hash": SWIFT_VISION_JUDGE_PROMPT_HASH,
        "rubric": request.get("rubric", ""),
        "messages_hash": _hash_payload(
            {
                "expected_answer": request.get("expected_answer", ""),
                "model_answer": request.get("model_answer", ""),
                "media": request.get("media", []),
            }
        ),
        "model_answer": request.get("model_answer", ""),
        "expected_answer": request.get("expected_answer", ""),
        "typed_score": typed_score,
        "equivalent": bool(decision.get("equivalent", False)),
        "confidence": _bounded_float(decision.get("confidence")),
        "reason_code": str(decision.get("reason_code") or ""),
        "failure_reason": failure_reason,
        "short_reason": str(decision.get("short_reason") or ""),
        "source": source,
        "judge_source": source,
        "status": status,
        "cache_key": cache_key,
        "error_code": error_code,
        "latency_ms": 0.0,
    }


def _normalize_judge_decision(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {
            "equivalent": False,
            "confidence": 0.0,
            "reason_code": "malformed_response",
            "short_reason": "Judge response was not a JSON object.",
        }
    equivalent = raw.get("equivalent")
    if not isinstance(equivalent, bool):
        return {
            "equivalent": False,
            "confidence": 0.0,
            "reason_code": "malformed_response",
            "short_reason": "Judge response did not include boolean equivalent.",
        }
    return {
        "equivalent": equivalent,
        "confidence": _bounded_float(raw.get("confidence")),
        "reason_code": str(raw.get("reason_code") or ("same_answer" if equivalent else "not_equivalent")),
        "short_reason": str(raw.get("short_reason") or ""),
    }


def _redacted_media(media: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "media_id": item.get("media_id", ""),
            "kind": item.get("kind", ""),
            "sha256": item.get("sha256", ""),
            "mime_type": item.get("mime_type", ""),
            "duration": item.get("duration", item.get("duration_ms", "")),
            "frame_count": item.get("frame_count", ""),
        }
        for item in media
    ]


def _remediation_hint(missing: list[str]) -> str:
    hints = {
        "model_weights": "Provide local model weights for the accepted concrete model id.",
        "judge_target": "Configure judge remote server id and judge model id for judge-backed samples.",
        "fixture_media": "Vendor immutable fixture media artifacts and update media_artifacts paths.",
        "frozen_python_baseline": "Create the frozen Python baseline artifact before Swift acceptance.",
        "swift_vision_endpoint": "Start Melix with a Swift Vision Worker and pass its OpenAI-compatible base URL.",
    }
    return " ".join(hints[item] for item in missing if item in hints)


def _policy_float(manifest: dict[str, object], key: str, *, default: float) -> float:
    policy = manifest.get("scoring_policy")
    if isinstance(policy, dict):
        value = policy.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return default


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    return str(value or "").strip()


def _manifest_relative_path(base_dir: Path, raw_path: object) -> str:
    path = str(raw_path or "").strip()
    if not path:
        return ""
    return _resolve_manifest_path(base_dir, path)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _bounded_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return round(max(0.0, min(1.0, float(value))), 6)


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _hash_file(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        rows.append(payload)
    return rows


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _infer_git_sha(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return ""
    return result.stdout.strip()


def _detected_path(path: str) -> str:
    if path and Path(path).expanduser().exists():
        return path
    return ""


def _resolve_manifest_path(base_dir: Path, raw_path: str) -> str:
    path = raw_path.strip()
    if not path:
        return ""
    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return str(expanded)
    return str(base_dir / expanded)


def _judge_target_id(config: AcceptanceRunConfig) -> str:
    if config.judge_remote_server_id and config.judge_model_id:
        return f"{config.judge_remote_server_id}/{config.judge_model_id}"
    return ""


def _utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _failure_reason(exc: Exception) -> str:
    first_line = str(exc).splitlines()[0].strip()
    return first_line[:240] if first_line else exc.__class__.__name__


if __name__ == "__main__":
    raise SystemExit(main())
