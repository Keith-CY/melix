from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote_plus, urlencode
from urllib.request import Request, urlopen

from worker.productization.device_identity import collect_device_identity


MEMORY_COMFORT_BUDGET_FACTOR = 0.60
RESIDENT_MEMORY_OVERHEAD_FACTOR = 1.35

_BARE_SIZE_HINT_RE = re.compile(r"(?:model\s+size\s*[:|]?\s*)?(\d+(?:\.\d+)?)\s*(kb|mb|gb)\b", re.IGNORECASE)
_EXPLICIT_SIZE_HINT_RE = re.compile(r"\bmodel\s+size\s*[:|]?\s*(\d+(?:\.\d+)?)\s*(kb|mb|gb)\b", re.IGNORECASE)


@dataclass(frozen=True)
class HubModelSummaryRecord:
    repo_id: str
    author: str
    model_name: str
    summary: str
    pipeline_tag: str
    tags: list[str]
    downloads: int
    likes: int
    mlx_compatible: bool
    library_name: str
    sibling_files: list[str]
    last_modified: str
    local_fit_status: str = "unknown"
    local_fit_reasons: list[str] = field(default_factory=list)
    estimated_artifact_bytes: int = 0
    estimated_resident_bytes: int = 0
    parameter_count: int = 0
    quantization_summary: str = ""
    gated: bool = False
    recommended_action: str = "inspect_metadata"


@dataclass(frozen=True)
class HubSearchPage:
    items: list[HubModelSummaryRecord]
    next_cursor: str


@dataclass(frozen=True)
class HubModelCardRecord:
    repo_id: str
    author: str
    model_name: str
    summary: str
    license: str
    pipeline_tag: str
    tags: list[str]
    downloads: int
    likes: int
    mlx_compatible: bool
    library_name: str
    sibling_files: list[str]
    base_models: list[str]
    last_modified: str
    local_fit_status: str = "unknown"
    local_fit_reasons: list[str] = field(default_factory=list)
    estimated_artifact_bytes: int = 0
    estimated_resident_bytes: int = 0
    parameter_count: int = 0
    quantization_summary: str = ""
    gated: bool = False
    recommended_action: str = "inspect_metadata"


class HubCatalogError(RuntimeError):
    def __init__(self, code: str, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retriable = retriable


class HubCatalog:
    def __init__(
        self,
        *,
        endpoint: str = "https://huggingface.co",
        opener: Callable[[Request], Any] | None = None,
        local_memory_gb: float | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._opener = opener or (lambda request: urlopen(request, timeout=20))
        self._local_memory_gb = (
            local_memory_gb
            if local_memory_gb is not None
            else collect_device_identity().memory_gb
        )

    def search_models(
        self,
        *,
        query: str,
        page_size: int,
        cursor: str,
        mlx_only: bool,
    ) -> HubSearchPage:
        payloads, next_cursor = self._fetch_models(
            search=query,
            page_size=page_size,
            cursor=cursor,
        )
        if mlx_only:
            payloads = [payload for payload in payloads if _payload_is_mlx_compatible(payload)]
        items = [self._summary_record(payload) for payload in payloads]
        return HubSearchPage(items=items, next_cursor=next_cursor)

    def get_model_card(self, *, repo_id: str) -> HubModelCardRecord:
        if not repo_id.strip():
            raise HubCatalogError("invalid_argument", "Hub repo_id is required.")

        payloads, _ = self._fetch_models(search=repo_id, page_size=10, cursor="")
        payload = next(
            (
                item
                for item in payloads
                if _string(item.get("id") or item.get("modelId")) == repo_id
            ),
            None,
        )
        if payload is None:
            raise HubCatalogError("not_found", f"Hub model not found for repo_id={repo_id}.")
        return self._card_record(payload)

    def _fetch_models(
        self,
        *,
        search: str,
        page_size: int,
        cursor: str,
    ) -> tuple[list[dict[str, Any]], str]:
        normalized_page_size = max(1, page_size or 20)
        params: list[tuple[str, str]] = [
            ("limit", str(normalized_page_size)),
            ("full", "true"),
            ("cardData", "true"),
            ("config", "true"),
        ]
        if search:
            params.append(("search", search))
        if cursor:
            params.append(("cursor", cursor))

        request = Request(
            url=f"{self._endpoint}/api/models?{urlencode(params, doseq=True)}",
            headers={
                "Accept": "application/json",
                "User-Agent": "Melix/0.1 hub-catalog",
            },
        )
        try:
            response = self._opener(request)
            with response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, list):
                    raise HubCatalogError("hub_payload_invalid", "Hub model search returned a non-list payload.")
                next_cursor = _next_cursor_from_link(response.headers.get("Link", ""))
                return [
                    item
                    for item in payload
                    if isinstance(item, dict)
                ], next_cursor
        except HubCatalogError:
            raise
        except HTTPError as exc:
            code = "hub_rate_limited" if exc.code == 429 else "hub_request_failed"
            raise HubCatalogError(code, f"Hub request failed with HTTP {exc.code}.", retriable=exc.code >= 500) from exc
        except URLError as exc:
            raise HubCatalogError("hub_unreachable", f"Hub request failed: {exc.reason}.", retriable=True) from exc
        except json.JSONDecodeError as exc:
            raise HubCatalogError("hub_payload_invalid", f"Hub payload could not be decoded: {exc}") from exc

    def _summary_record(self, payload: dict[str, Any]) -> HubModelSummaryRecord:
        card_data = payload.get("cardData") if isinstance(payload.get("cardData"), dict) else {}
        repo_id = _string(payload.get("id") or payload.get("modelId"))
        tags = _string_list(payload.get("tags"))
        lowered_tags = _lowered_tag_set(tags)
        library_name = _string(payload.get("library_name") or card_data.get("library_name"))
        sibling_files = _sibling_files(payload.get("siblings"))
        mlx_compatible = _is_mlx_compatible(
            repo_id=repo_id,
            tags=tags,
            lowered_tags=lowered_tags,
            library_name=library_name,
            card_data=card_data,
        )
        local_fit = _local_fit_evidence(
            payload=payload,
            repo_id=repo_id,
            pipeline_tag=_string(payload.get("pipeline_tag") or card_data.get("pipeline_tag")),
            tags=tags,
            lowered_tags=lowered_tags,
            mlx_compatible=mlx_compatible,
            local_memory_gb=self._local_memory_gb,
        )
        return HubModelSummaryRecord(
            repo_id=repo_id,
            author=_author(payload, repo_id),
            model_name=_model_name(repo_id),
            summary=_string(card_data.get("model_name") or payload.get("description")),
            pipeline_tag=_string(payload.get("pipeline_tag") or card_data.get("pipeline_tag")),
            tags=tags,
            downloads=_int(payload.get("downloads")),
            likes=_int(payload.get("likes")),
            mlx_compatible=mlx_compatible,
            library_name=library_name,
            sibling_files=sibling_files,
            last_modified=_string(payload.get("lastModified")),
            local_fit_status=local_fit["status"],
            local_fit_reasons=local_fit["reasons"],
            estimated_artifact_bytes=local_fit["estimated_artifact_bytes"],
            estimated_resident_bytes=local_fit["estimated_resident_bytes"],
            parameter_count=local_fit["parameter_count"],
            quantization_summary=local_fit["quantization_summary"],
            gated=local_fit["gated"],
            recommended_action=local_fit["recommended_action"],
        )

    def _card_record(self, payload: dict[str, Any]) -> HubModelCardRecord:
        summary = self._summary_record(payload)
        card_data = payload.get("cardData") if isinstance(payload.get("cardData"), dict) else {}
        return HubModelCardRecord(
            repo_id=summary.repo_id,
            author=summary.author,
            model_name=summary.model_name,
            summary=summary.summary,
            license=_string(card_data.get("license")) or _license_from_tags(summary.tags),
            pipeline_tag=summary.pipeline_tag,
            tags=summary.tags,
            downloads=summary.downloads,
            likes=summary.likes,
            mlx_compatible=summary.mlx_compatible,
            library_name=summary.library_name,
            sibling_files=summary.sibling_files,
            base_models=_base_models(card_data.get("base_model")),
            last_modified=summary.last_modified,
            local_fit_status=summary.local_fit_status,
            local_fit_reasons=summary.local_fit_reasons,
            estimated_artifact_bytes=summary.estimated_artifact_bytes,
            estimated_resident_bytes=summary.estimated_resident_bytes,
            parameter_count=summary.parameter_count,
            quantization_summary=summary.quantization_summary,
            gated=summary.gated,
            recommended_action=summary.recommended_action,
        )


def _next_cursor_from_link(link_header: str) -> str:
    search_start = 0
    while True:
        url_start = link_header.find("<", search_start)
        if url_start < 0:
            return ""
        url_end = link_header.find(">", url_start + 1)
        if url_end < 0:
            return ""
        next_url_start = link_header.find("<", url_end + 1)
        relation_start = url_end + 1
        relation_end = next_url_start if next_url_start >= 0 else len(link_header)
        if link_header.find('rel="next"', relation_start, relation_end) >= 0:
            return _cursor_query_value(link_header, url_start + 1, url_end)
        search_start = relation_end


def _cursor_query_value(url: str, start: int, end: int) -> str:
    query_start = url.find("?", start, end)
    if query_start < 0:
        return ""
    query_end = url.find("#", query_start + 1, end)
    if query_end < 0:
        query_end = end

    value_start = query_start + 1
    if url.startswith("cursor=", value_start, query_end):
        value_start += len("cursor=")
    else:
        cursor_start = url.find("&cursor=", value_start, query_end)
        if cursor_start < 0:
            return ""
        value_start = cursor_start + len("&cursor=")

    value_end = url.find("&", value_start, query_end)
    if value_end < 0:
        value_end = query_end
    return unquote_plus(url[value_start:value_end])


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _lowered_tag_set(tags: list[str]) -> set[str]:
    return {tag.lower() for tag in tags}


def _normalized_lowered_tags(tags: list[str], lowered_tags: set[str] | None = None) -> set[str]:
    return lowered_tags if lowered_tags is not None else _lowered_tag_set(tags)


def _sibling_files(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    files: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        filename = item.get("rfilename")
        if isinstance(filename, str) and filename:
            files.append(filename)
    return files


def _model_name(repo_id: str) -> str:
    if "/" not in repo_id:
        return repo_id
    return repo_id.split("/", 1)[1]


def _author(payload: dict[str, Any], repo_id: str) -> str:
    author = _string(payload.get("author"))
    if author:
        return author
    if "/" not in repo_id:
        return ""
    return repo_id.split("/", 1)[0]


def _license_from_tags(tags: list[str]) -> str:
    for tag in tags:
        if tag.startswith("license:"):
            return tag.split(":", 1)[1]
    return ""


def _base_models(value: Any) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def _payload_is_mlx_compatible(payload: dict[str, Any]) -> bool:
    card_data = payload.get("cardData") if isinstance(payload.get("cardData"), dict) else {}
    tags = _string_list(payload.get("tags"))
    if any(tag.lower() == "mlx" for tag in tags):
        return True
    library_name = _string(payload.get("library_name") or card_data.get("library_name"))
    if library_name.lower() == "mlx":
        return True
    repo_id = _string(payload.get("id") or payload.get("modelId"))
    if "mlx" in repo_id.lower():
        return True
    card_tags = card_data.get("tags")
    if not card_tags:
        return False
    return any(tag.lower() == "mlx" for tag in _string_list(card_tags))


def _is_mlx_compatible(
    *,
    repo_id: str,
    tags: list[str],
    library_name: str,
    card_data: dict[str, Any],
    lowered_tags: set[str] | None = None,
) -> bool:
    lowered_tags = _normalized_lowered_tags(tags, lowered_tags)
    if "mlx" in lowered_tags:
        return True
    if library_name.lower() == "mlx":
        return True
    lowered_repo_id = repo_id.lower()
    if "mlx" in lowered_repo_id:
        return True
    card_tags = card_data.get("tags")
    if not card_tags:
        return False
    return "mlx" in {tag.lower() for tag in _string_list(card_tags)}


def _local_fit_evidence(
    *,
    payload: dict[str, Any],
    repo_id: str,
    pipeline_tag: str,
    tags: list[str],
    mlx_compatible: bool,
    local_memory_gb: float,
    lowered_tags: set[str] | None = None,
) -> dict[str, Any]:
    lowered_tags = _normalized_lowered_tags(tags, lowered_tags)
    artifact_bytes = _estimated_artifact_bytes(payload)
    parameter_count = _parameter_count(payload.get("safetensors"))
    quantization_summary = _quantization_summary(tags, lowered_tags=lowered_tags)
    estimated_resident_bytes = _estimated_resident_bytes(
        artifact_bytes=artifact_bytes,
        parameter_count=parameter_count,
        tags=tags,
        lowered_tags=lowered_tags,
    )
    gated = _gated(payload.get("gated"))
    reasons: list[str] = []

    if not mlx_compatible:
        reasons.append("No MLX compatibility signal")
        return {
            "status": "blocked",
            "reasons": reasons,
            "estimated_artifact_bytes": artifact_bytes,
            "estimated_resident_bytes": estimated_resident_bytes,
            "parameter_count": parameter_count,
            "quantization_summary": quantization_summary,
            "gated": gated,
            "recommended_action": "unavailable",
        }

    reasons.append("MLX-compatible Hub metadata found.")
    if _normalized_pipeline_tag(pipeline_tag) not in {"text-generation", "image-text-to-text"}:
        reasons.append(f"Unsupported Melix pipeline tag: {pipeline_tag or 'unknown'}.")
        return {
            "status": "blocked",
            "reasons": reasons,
            "estimated_artifact_bytes": artifact_bytes,
            "estimated_resident_bytes": estimated_resident_bytes,
            "parameter_count": parameter_count,
            "quantization_summary": quantization_summary,
            "gated": gated,
            "recommended_action": "unavailable",
        }

    if gated:
        reasons.append("Hub repository is gated and requires authorized access before download.")
        return {
            "status": "blocked",
            "reasons": reasons,
            "estimated_artifact_bytes": artifact_bytes,
            "estimated_resident_bytes": estimated_resident_bytes,
            "parameter_count": parameter_count,
            "quantization_summary": quantization_summary,
            "gated": gated,
            "recommended_action": "request_access",
        }

    if artifact_bytes <= 0 and estimated_resident_bytes <= 0:
        reasons.append("No artifact size metadata")
        return {
            "status": "unknown",
            "reasons": reasons,
            "estimated_artifact_bytes": artifact_bytes,
            "estimated_resident_bytes": estimated_resident_bytes,
            "parameter_count": parameter_count,
            "quantization_summary": quantization_summary,
            "gated": gated,
            "recommended_action": "inspect_metadata",
        }

    memory_budget_bytes = int(max(local_memory_gb, 0.0) * (1024 ** 3) * MEMORY_COMFORT_BUDGET_FACTOR)
    if memory_budget_bytes > 0 and estimated_resident_bytes > memory_budget_bytes:
        reasons.append("Estimated resident bytes exceed the memory comfort budget.")
        return {
            "status": "heavy",
            "reasons": reasons,
            "estimated_artifact_bytes": artifact_bytes,
            "estimated_resident_bytes": estimated_resident_bytes,
            "parameter_count": parameter_count,
            "quantization_summary": quantization_summary,
            "gated": gated,
            "recommended_action": "review_risk",
        }

    if local_memory_gb <= 0:
        reasons.append("Local memory probe is unavailable.")
        status = "unknown"
        recommended_action = "inspect_metadata"
    else:
        reasons.append("Estimated resident bytes are within the memory comfort budget.")
        status = "good"
        recommended_action = "download"

    return {
        "status": status,
        "reasons": reasons,
        "estimated_artifact_bytes": artifact_bytes,
        "estimated_resident_bytes": estimated_resident_bytes,
        "parameter_count": parameter_count,
        "quantization_summary": quantization_summary,
        "gated": gated,
        "recommended_action": recommended_action,
    }


def _estimated_artifact_bytes(payload: dict[str, Any]) -> int:
    for key in ("usedStorage", "used_storage", "storage", "size"):
        value = _int(payload.get(key))
        if value > 0:
            return value

    sibling_bytes = _sibling_file_bytes(payload.get("siblings"))
    if sibling_bytes > 0:
        return sibling_bytes

    hint_bytes = _size_hint_bytes(payload)
    return hint_bytes


def _sibling_file_bytes(value: Any) -> int:
    if not isinstance(value, list):
        return 0
    total = 0
    for item in value:
        if not isinstance(item, dict):
            continue
        filename = _string(item.get("rfilename"))
        if not filename or not _is_weight_or_config_file(filename):
            continue
        size = _int(item.get("size"))
        if size <= 0 and isinstance(item.get("lfs"), dict):
            size = _int(item["lfs"].get("size"))
        total += max(size, 0)
    return total


def _is_weight_or_config_file(filename: str) -> bool:
    lowered = filename.lower()
    return lowered.endswith((".safetensors", ".npz", ".gguf", "config.json", "tokenizer.json"))


def _size_hint_bytes(payload: dict[str, Any]) -> int:
    raw_card_data = payload.get("cardData")
    card_data = raw_card_data if isinstance(raw_card_data, dict) else {}
    direct_card_text = _string(card_data.get("model_size"))
    if direct_card_text:
        direct_card_hint = _size_hint_from_text(direct_card_text, allow_bare=True)
        if direct_card_hint > 0:
            return direct_card_hint

    text = "\n".join(
        text
        for value in (
            payload.get("description"),
            payload.get("readme"),
            card_data.get("description"),
        )
        if (text := _string(value))
    )
    if not text:
        return 0
    return _size_hint_from_text(text, allow_bare=False)


def _size_hint_from_text(text: str, *, allow_bare: bool) -> int:
    if not text:
        return 0
    pattern = _BARE_SIZE_HINT_RE if allow_bare else _EXPLICIT_SIZE_HINT_RE
    match = pattern.search(text)
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2).lower()
    multiplier = {"kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}[unit]
    return int(value * multiplier)


def _parameter_count(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    for key in ("total", "parameter_count", "params"):
        count = _int(value.get(key))
        if count > 0:
            return count
    parameters = value.get("parameters") or value.get("parameterCount")
    if isinstance(parameters, dict):
        return sum(max(_int(item), 0) for item in parameters.values())
    return 0


def _estimated_resident_bytes(
    *,
    artifact_bytes: int,
    parameter_count: int,
    tags: list[str],
    lowered_tags: set[str] | None = None,
) -> int:
    if artifact_bytes > 0:
        base_size = artifact_bytes
    elif parameter_count > 0:
        base_size = parameter_count * _bytes_per_parameter(tags, lowered_tags=lowered_tags)
    else:
        return 0
    return math.ceil(base_size * RESIDENT_MEMORY_OVERHEAD_FACTOR)


def _bytes_per_parameter(tags: list[str], *, lowered_tags: set[str] | None = None) -> float:
    lowered = _normalized_lowered_tags(tags, lowered_tags)
    joined = " ".join(lowered)
    if "2bit" in joined or "2-bit" in joined:
        return 0.25
    if "3bit" in joined or "3-bit" in joined:
        return 0.375
    if "4bit" in joined or "4-bit" in joined:
        return 0.5
    if "8bit" in joined or "8-bit" in joined:
        return 1.0
    if "fp32" in joined or "float32" in joined or "f32" in joined:
        return 4.0
    if "bf16" in joined or "fp16" in joined or "float16" in joined:
        return 2.0
    return 2.0


def _quantization_summary(tags: list[str], *, lowered_tags: set[str] | None = None) -> str:
    lowered = _normalized_lowered_tags(tags, lowered_tags)
    ordered = [
        ("2-bit", {"2bit", "2-bit"}),
        ("3-bit", {"3bit", "3-bit"}),
        ("4-bit", {"4bit", "4-bit"}),
        ("8-bit", {"8bit", "8-bit"}),
        ("mixed-precision", {"mixed-precision", "mixed_precision"}),
        ("optiq", {"optiq"}),
        ("fp32", {"fp32", "float32", "f32"}),
        ("bf16", {"bf16"}),
        ("fp16", {"fp16", "float16"}),
    ]
    values = [label for label, aliases in ordered if lowered.intersection(aliases)]
    return ", ".join(values)


def _gated(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "none", "no", "0", "auto"}
    return False


def _normalized_pipeline_tag(value: str) -> str:
    return value.strip().lower()
