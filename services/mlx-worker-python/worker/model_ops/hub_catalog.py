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
GEMMA4_QAT_AUTOMATIC_ORG = "mlx-community"
MLX_ONLY_SEARCH_MAX_PAGES = 4

_SIZE_HINT_KB = 1024
_SIZE_HINT_MB = _SIZE_HINT_KB * 1024
_SIZE_HINT_GB = _SIZE_HINT_MB * 1024
_SIZE_HINT_MULTIPLIERS = {
    "kb": _SIZE_HINT_KB,
    "mb": _SIZE_HINT_MB,
    "gb": _SIZE_HINT_GB,
}

_BARE_SIZE_HINT_RE = re.compile(r"(?:model\s+size\s*[:|]?\s*)?(\d+(?:\.\d+)?)\s*(kb|mb|gb)\b", re.IGNORECASE)
_EXPLICIT_SIZE_HINT_RE = re.compile(r"\bmodel\s+size\s*[:|]?\s*(\d+(?:\.\d+)?)\s*(kb|mb|gb)\b", re.IGNORECASE)
_NEXT_LINK_REL_MARKER = 'rel="next"'
_URL_HEX_DIGITS = {
    "0": 0,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "a": 10,
    "b": 11,
    "c": 12,
    "d": 13,
    "e": 14,
    "f": 15,
    "A": 10,
    "B": 11,
    "C": 12,
    "D": 13,
    "E": 14,
    "F": 15,
}
_LOWERCASE_WEIGHT_OR_CONFIG_SUFFIXES = (".safetensors", ".npz", ".gguf", "config.json", "tokenizer.json")
@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True)
class HubSearchPage:
    items: list[HubModelSummaryRecord]
    next_cursor: str


@dataclass(frozen=True, slots=True)
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
        normalized_page_size = max(1, page_size or 20)
        if not mlx_only:
            payloads, next_cursor = self._fetch_models(
                search=query,
                page_size=normalized_page_size,
                cursor=cursor,
                hub_filter="",
            )
            items = [self._summary_record(payload) for payload in payloads]
            return HubSearchPage(items=items, next_cursor=next_cursor)

        payloads: list[dict[str, Any]] = []
        next_cursor = ""
        current_cursor = cursor
        pages_fetched = 0
        while pages_fetched < MLX_ONLY_SEARCH_MAX_PAGES:
            page_payloads, next_cursor = self._fetch_models(
                search=query,
                page_size=normalized_page_size,
                cursor=current_cursor,
                hub_filter="mlx",
            )
            payloads.extend(
                payload
                for payload in page_payloads
                if _payload_is_mlx_compatible(payload)
            )
            pages_fetched += 1
            if len(payloads) >= normalized_page_size or not next_cursor:
                break
            current_cursor = next_cursor

        items = [self._summary_record(payload) for payload in payloads]
        return HubSearchPage(items=items, next_cursor=next_cursor)

    def get_model_card(self, *, repo_id: str) -> HubModelCardRecord:
        if not repo_id.strip():
            raise HubCatalogError("invalid_argument", "Hub repo_id is required.")

        payloads, _ = self._fetch_models(search=repo_id, page_size=10, cursor="", hub_filter="")
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
        hub_filter: str,
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
        if hub_filter:
            params.append(("filter", hub_filter))
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
        payload_get = payload.get
        raw_card_data = payload_get("cardData")
        card_data = raw_card_data if isinstance(raw_card_data, dict) else {}
        card_get = card_data.get
        repo_id = _string(payload_get("id") or payload_get("modelId"))
        tags = _string_list(payload_get("tags"))
        lowered_tags = _lowered_tag_set(tags)
        library_name = _string(payload_get("library_name") or card_get("library_name"))
        pipeline_tag = _string(payload_get("pipeline_tag") or card_get("pipeline_tag"))
        sibling_files = _sibling_files(payload_get("siblings"))
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
            pipeline_tag=pipeline_tag,
            tags=tags,
            lowered_tags=lowered_tags,
            mlx_compatible=mlx_compatible,
            local_memory_gb=self._local_memory_gb,
            card_data=card_data,
        )
        return HubModelSummaryRecord(
            repo_id=repo_id,
            author=_author(payload, repo_id),
            model_name=_model_name(repo_id),
            summary=_string(card_get("model_name") or payload_get("description")),
            pipeline_tag=pipeline_tag,
            tags=tags,
            downloads=_int(payload_get("downloads")),
            likes=_int(payload_get("likes")),
            mlx_compatible=mlx_compatible,
            library_name=library_name,
            sibling_files=sibling_files,
            last_modified=_string(payload_get("lastModified")),
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
        raw_card_data = payload.get("cardData")
        card_data = raw_card_data if isinstance(raw_card_data, dict) else {}
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
    marker = _NEXT_LINK_REL_MARKER
    marker_len = len(marker)
    search_start = 0
    while True:
        relation_start = link_header.find(marker, search_start)
        if relation_start < 0:
            return ""
        url_end = link_header.rfind(">", 0, relation_start)
        if url_end < 0:
            search_start = relation_start + marker_len
            continue
        url_start = link_header.rfind("<", 0, url_end)
        if url_start < 0:
            search_start = relation_start + marker_len
            continue
        query_start = link_header.rfind("?", url_start + 1, url_end)
        if query_start < 0:
            return ""
        query_end = link_header.find("#", query_start + 1, url_end)
        if query_end < 0:
            query_end = url_end
        value_start = query_start + 1
        if link_header.startswith("cursor=", value_start, query_end):
            value_start += len("cursor=")
        else:
            cursor_start = link_header.find("&cursor=", value_start, query_end)
            if cursor_start < 0:
                return ""
            value_start = cursor_start + len("&cursor=")
        value_end = link_header.find("&", value_start, query_end)
        if value_end < 0:
            value_end = query_end
        return _unquote_plus_ascii_cursor(link_header[value_start:value_end])


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
    return _unquote_plus_ascii_cursor(url[value_start:value_end])


def _unquote_plus_ascii_cursor(value: str) -> str:
    if "%" not in value and "+" not in value:
        return value
    hex_digits = _URL_HEX_DIGITS
    output: list[str] = []
    append = output.append
    index = 0
    value_len = len(value)
    while index < value_len:
        char = value[index]
        if char == "+":
            append(" ")
            index += 1
            continue
        if char == "%" and index + 2 < value_len:
            high = hex_digits.get(value[index + 1])
            low = hex_digits.get(value[index + 2])
            if high is not None and low is not None:
                codepoint = (high << 4) + low
                if codepoint > 0x7F:
                    return unquote_plus(value)
                append(chr(codepoint))
                index += 3
                continue
        append(char)
        index += 1
    return "".join(output)


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
    if type(value) is list:
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _lowered_tag_set(tags: list[str]) -> set[str]:
    return {tag.lower() for tag in tags}


def _is_mlx_atom(value: str) -> bool:
    return len(value) == 3 and value[0] in "mM" and value[1] in "lL" and value[2] in "xX"


def _tag_payload_contains_mlx(value: Any) -> bool:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and (
                item == "MLX" or item == "mlx" or (len(item) == 3 and _is_mlx_atom(item))
            ):
                return True
        return False
    if isinstance(value, str):
        return _is_mlx_atom(value)
    return False


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
    separator_index = repo_id.find("/")
    if separator_index < 0:
        return repo_id
    return repo_id[separator_index + 1 :]


def _author(payload: dict[str, Any], repo_id: str) -> str:
    author = _string(payload.get("author"))
    if author:
        return author
    separator_index = repo_id.find("/")
    if separator_index < 0:
        return ""
    return repo_id[:separator_index]


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
    library_name = _string(payload.get("library_name"))
    if library_name and _is_mlx_atom(library_name):
        return True
    if _tag_payload_contains_mlx(payload.get("tags")):
        return True
    repo_id = _string(payload.get("id") or payload.get("modelId"))
    if "mlx" in repo_id.lower():
        return True
    card_data = payload.get("cardData")
    if not isinstance(card_data, dict):
        return False
    if not library_name and _is_mlx_atom(_string(card_data.get("library_name"))):
        return True
    card_tags = card_data.get("tags")
    if not card_tags:
        return False
    return _tag_payload_contains_mlx(card_tags)


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
    if _is_mlx_atom(library_name):
        return True
    lowered_repo_id = repo_id.lower()
    if "mlx" in lowered_repo_id:
        return True
    card_tags = card_data.get("tags")
    if not card_tags:
        return False
    return _tag_payload_contains_mlx(card_tags)


def _local_fit_evidence(
    *,
    payload: dict[str, Any],
    repo_id: str,
    pipeline_tag: str,
    tags: list[str],
    mlx_compatible: bool,
    local_memory_gb: float,
    lowered_tags: set[str] | None = None,
    card_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lowered_tags = _normalized_lowered_tags(tags, lowered_tags)
    artifact_bytes = _estimated_artifact_bytes(payload, card_data=card_data)
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
    gemma4_qat: dict[str, str] = {}
    if "qat" in lowered_tags or "qat" in repo_id or "QAT" in repo_id:
        repo_id_lower = repo_id.lower()
    else:
        repo_id_lower = ""
    if repo_id_lower and _gemma4_qat_fast_candidate(repo_id_lower, lowered_tags):
        gemma4_qat = _gemma4_qat_evidence(
            repo_id_lower=repo_id_lower,
            tags=tags,
            lowered_tags=lowered_tags,
            card_data=card_data,
        )
    if gemma4_qat.get("enabled") == "true" and "QAT" not in quantization_summary.split(", "):
        quantization_summary = (
            f"{quantization_summary}, QAT" if quantization_summary else "QAT"
        )

    if not mlx_compatible:
        unsupported_format = gemma4_qat.get("unsupported_format", "")
        if unsupported_format:
            reasons.append(f"Unsupported Gemma 4 QAT runtime format for Melix: {unsupported_format}.")
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

    if gemma4_qat.get("enabled") == "true" and gemma4_qat.get("auto_supported") != "true":
        reasons.append(
            "Experimental Gemma 4 QAT MLX asset outside mlx-community; manual import required."
        )
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

    config = _text_config(payload)
    kv_cache_bytes = _estimated_kv_cache_bytes(config)
    if kv_cache_bytes > 0:
        estimated_resident_bytes += kv_cache_bytes
        context_tokens = _context_token_count_from_config(config)
        reasons.append(
            f"Estimated KV cache bytes for {context_tokens} context tokens: {kv_cache_bytes}."
        )

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

    if gemma4_qat.get("auto_supported") == "true":
        reasons.append("Gemma 4 QAT MLX asset is in the automatic support scope.")
        reasons.append("Matching MTP draft companion can be auto-paired when available.")

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


def _estimated_artifact_bytes(
    payload: dict[str, Any], *, card_data: dict[str, Any] | None = None
) -> int:
    for key in ("usedStorage", "used_storage", "storage", "size"):
        value = _int(payload.get(key))
        if value > 0:
            return value

    sibling_bytes = _sibling_file_bytes(payload.get("siblings"))
    if sibling_bytes > 0:
        return sibling_bytes

    hint_bytes = _size_hint_bytes(payload, card_data=card_data)
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
    if filename.endswith(_LOWERCASE_WEIGHT_OR_CONFIG_SUFFIXES):
        return True
    lowered = filename.lower()
    return lowered.endswith(_LOWERCASE_WEIGHT_OR_CONFIG_SUFFIXES)


def _size_hint_bytes(payload: dict[str, Any], *, card_data: dict[str, Any] | None = None) -> int:
    if card_data is None:
        raw_card_data = payload.get("cardData")
        card_data = raw_card_data if isinstance(raw_card_data, dict) else {}
    direct_card_text = _string(card_data.get("model_size"))
    if direct_card_text:
        direct_card_hint = _direct_card_size_hint_from_text(direct_card_text)
        if direct_card_hint > 0:
            return direct_card_hint
        direct_card_hint = _size_hint_from_text(direct_card_text, allow_bare=True)
        if direct_card_hint > 0:
            return direct_card_hint

    description_text = _string(payload.get("description"))
    readme_text = _string(payload.get("readme"))
    card_description_text = _string(card_data.get("description"))
    if not readme_text and not card_description_text:
        return (
            _size_hint_from_text(description_text, allow_bare=False)
            if description_text and _may_contain_model_marker(description_text)
            else 0
        )
    if not description_text and not card_description_text:
        return (
            _size_hint_from_text(readme_text, allow_bare=False)
            if readme_text and _may_contain_model_marker(readme_text)
            else 0
        )
    if not description_text and not readme_text:
        return (
            _size_hint_from_text(card_description_text, allow_bare=False)
            if card_description_text and _may_contain_model_marker(card_description_text)
            else 0
        )

    found_model_marker = False
    for text in (description_text, readme_text, card_description_text):
        if not text or not _may_contain_model_marker(text):
            continue
        found_model_marker = True
        direct_hint = _direct_explicit_size_hint_from_text(text)
        if direct_hint > 0:
            return direct_hint
        hint = _size_hint_from_text(text, allow_bare=False)
        if hint > 0:
            return hint
    if not found_model_marker:
        return 0
    text = "\n".join(
        text
        for text in (description_text, readme_text, card_description_text)
        if text
    )
    return _size_hint_from_text(text, allow_bare=False)


def _direct_size_hint_from_text(text: str) -> int:
    if len(text) >= 4 and text[-3].isspace():
        unit_suffix = ord(text[-1])
        if unit_suffix == 66 or unit_suffix == 98:  # B or b
            unit_initial = ord(text[-2])
            if unit_initial == 77 or unit_initial == 109:  # M or m
                multiplier = _SIZE_HINT_MB
            elif unit_initial == 71 or unit_initial == 103:  # G or g
                multiplier = _SIZE_HINT_GB
            elif unit_initial == 75 or unit_initial == 107:  # K or k
                multiplier = _SIZE_HINT_KB
            else:
                multiplier = 0
            if multiplier:
                value_text = text[:-3]
                if value_text.isdecimal():
                    return int(value_text) * multiplier
                try:
                    return int(float(value_text) * multiplier)
                except ValueError:
                    return 0

    parts = text.split(maxsplit=2)
    if len(parts) != 2:
        return 0
    value_text, unit_text = parts
    multiplier = _SIZE_HINT_MULTIPLIERS.get(unit_text.lower())
    if multiplier is None:
        return 0
    if value_text.isdecimal():
        return int(value_text) * multiplier
    try:
        return int(float(value_text) * multiplier)
    except ValueError:
        return 0


def _direct_card_size_hint_from_text(text: str) -> int:
    stripped_text = _strip_model_size_label(text)
    if stripped_text:
        return _direct_size_hint_from_text(stripped_text)
    return _direct_size_hint_from_text(text)


def _direct_explicit_size_hint_from_text(text: str) -> int:
    marker_index = text.find("Model size")
    if marker_index < 0:
        marker_index = text.find("MODEL SIZE")
    if marker_index < 0:
        marker_index = text.find("model size")
    if marker_index < 0:
        return 0

    value_start = marker_index + 10
    text_length = len(text)
    while value_start < text_length and text[value_start].isspace():
        value_start += 1
    if value_start < text_length and (text[value_start] == ":" or text[value_start] == "|"):
        value_start += 1
    while value_start < text_length and text[value_start].isspace():
        value_start += 1

    value_end = value_start
    while (
        value_end < text_length
        and text[value_end] not in "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"
    ):
        value_end += 1
    return _direct_size_hint_from_text(text[value_start:value_end])


def _strip_model_size_label(text: str) -> str:
    if text.startswith("Model size: "):
        return text[12:]
    if text.startswith("MODEL SIZE:") or text.startswith("MODEL SIZE|"):
        return text[11:]
    if not _starts_with_model_size_label(text):
        return ""
    cursor = 10
    text_length = len(text)
    while cursor < text_length and text[cursor].isspace():
        cursor += 1
    if cursor < text_length and (text[cursor] == ":" or text[cursor] == "|"):
        cursor += 1
    while cursor < text_length and text[cursor].isspace():
        cursor += 1
    return text[cursor:]


def _starts_with_model_size_label(text: str) -> bool:
    return (
        len(text) >= 10
        and (text[0] == "m" or text[0] == "M")
        and (text[1] == "o" or text[1] == "O")
        and (text[2] == "d" or text[2] == "D")
        and (text[3] == "e" or text[3] == "E")
        and (text[4] == "l" or text[4] == "L")
        and text[5] == " "
        and (text[6] == "s" or text[6] == "S")
        and (text[7] == "i" or text[7] == "I")
        and (text[8] == "z" or text[8] == "Z")
        and (text[9] == "e" or text[9] == "E")
    )


def _size_hint_from_text(text: str, *, allow_bare: bool) -> int:
    if not text:
        return 0
    pattern = _BARE_SIZE_HINT_RE if allow_bare else _EXPLICIT_SIZE_HINT_RE
    match = pattern.search(text)
    if not match:
        return 0
    value_text = match.group(1)
    unit_text = match.group(2)
    if unit_text == "kb" or unit_text == "KB":
        multiplier = _SIZE_HINT_KB
    elif unit_text == "mb" or unit_text == "MB":
        multiplier = _SIZE_HINT_MB
    elif unit_text == "gb" or unit_text == "GB":
        multiplier = _SIZE_HINT_GB
    else:
        multiplier = _SIZE_HINT_MULTIPLIERS[unit_text.lower()]
    if value_text.isdecimal():
        return int(value_text) * multiplier
    return int(float(value_text) * multiplier)


def _may_contain_model_marker(text: str) -> bool:
    return "MO" in text or "Mo" in text or "mo" in text or "mO" in text


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


def _estimated_kv_cache_bytes(config: dict[str, Any]) -> int:
    context_tokens = _context_token_count_from_config(config)
    layers = _positive_config_int(config, "num_hidden_layers", "n_layer", "num_layers")
    attention_heads = _positive_config_int(config, "num_attention_heads", "n_head", "n_heads")
    kv_heads = _positive_config_int(config, "num_key_value_heads", "n_kv_heads") or attention_heads
    head_dim = _positive_config_int(config, "head_dim")
    if head_dim <= 0 and attention_heads > 0:
        hidden_size = _positive_config_int(config, "hidden_size", "n_embd", "d_model")
        if hidden_size > 0 and hidden_size % attention_heads == 0:
            head_dim = hidden_size // attention_heads
    if context_tokens <= 0 or layers <= 0 or kv_heads <= 0 or head_dim <= 0:
        return 0
    return context_tokens * layers * kv_heads * head_dim * _kv_cache_bytes_per_element(config) * 2


def _text_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("config")
    if not isinstance(config, dict):
        return {}
    text_config = config.get("text_config")
    if not isinstance(text_config, dict):
        return config
    merged = dict(config)
    merged.update(text_config)
    return merged


def _context_token_count_from_config(config: dict[str, Any]) -> int:
    return _positive_config_int(
        config,
        "max_position_embeddings",
        "model_max_length",
        "max_seq_len",
        "max_sequence_length",
        "context_length",
        "seq_length",
    )


def _positive_config_int(config: dict[str, Any], *keys: str) -> int:
    for key in keys:
        raw_value = config.get(key)
        value = _int(raw_value)
        if value > 0:
            return value
        # _int() does not coerce strings; handle string-typed config fields explicitly
        if isinstance(raw_value, str) and raw_value.isdecimal():
            parsed = int(raw_value)
            if parsed > 0:
                return parsed
    return 0


def _kv_cache_bytes_per_element(config: dict[str, Any]) -> int:
    dtype = _string(config.get("torch_dtype") or config.get("dtype")).lower()
    if dtype in {"float32", "fp32", "f32"}:
        return 4
    if dtype in {"float8", "fp8", "int8", "uint8"}:
        return 1
    return 2


def _bytes_per_parameter(tags: list[str], *, lowered_tags: set[str] | None = None) -> float:
    lowered = _normalized_lowered_tags(tags, lowered_tags)
    if "2bit" in lowered or "2-bit" in lowered:
        return 0.25
    if "3bit" in lowered or "3-bit" in lowered:
        return 0.375
    if "4bit" in lowered or "4-bit" in lowered:
        return 0.5
    if "8bit" in lowered or "8-bit" in lowered:
        return 1.0
    if "fp32" in lowered or "float32" in lowered or "f32" in lowered:
        return 4.0
    return _bytes_per_parameter_from_tag_substrings(lowered)


def _bytes_per_parameter_from_tag_substrings(lowered: set[str]) -> float:
    has_3bit = False
    has_4bit = False
    has_8bit = False
    has_fp32 = False
    for tag in lowered:
        if "2bit" in tag or "2-bit" in tag:
            return 0.25
        if not has_3bit and ("3bit" in tag or "3-bit" in tag):
            has_3bit = True
        if not has_4bit and ("4bit" in tag or "4-bit" in tag):
            has_4bit = True
        if not has_8bit and ("8bit" in tag or "8-bit" in tag):
            has_8bit = True
        if not has_fp32 and ("fp32" in tag or "float32" in tag or "f32" in tag):
            has_fp32 = True
    if has_3bit:
        return 0.375
    if has_4bit:
        return 0.5
    if has_8bit:
        return 1.0
    if has_fp32:
        return 4.0
    return 2.0


def _quantization_summary(tags: list[str], *, lowered_tags: set[str] | None = None) -> str:
    lowered = _normalized_lowered_tags(tags, lowered_tags)
    values: list[str] = []
    if "2bit" in lowered or "2-bit" in lowered:
        values.append("2-bit")
    if "3bit" in lowered or "3-bit" in lowered:
        values.append("3-bit")
    if "4bit" in lowered or "4-bit" in lowered:
        values.append("4-bit")
    if "8bit" in lowered or "8-bit" in lowered:
        values.append("8-bit")
    if "mixed-precision" in lowered or "mixed_precision" in lowered:
        values.append("mixed-precision")
    if "optiq" in lowered:
        values.append("optiq")
    if "fp32" in lowered or "float32" in lowered or "f32" in lowered:
        values.append("fp32")
    if "bf16" in lowered:
        values.append("bf16")
    if "fp16" in lowered or "float16" in lowered:
        values.append("fp16")
    if "qat" in lowered:
        values.append("QAT")
    return ", ".join(values)


def _gemma4_qat_fast_candidate(repo_id_lower: str, lowered_tags: set[str]) -> bool:
    has_qat = "qat" in repo_id_lower or "qat" in lowered_tags
    if not has_qat:
        return False
    return (
        "gemma-4" in repo_id_lower
        or "gemma4" in repo_id_lower
        or "gemma-4" in lowered_tags
        or "gemma4" in lowered_tags
    )


def _gemma4_qat_evidence(
    *,
    repo_id_lower: str,
    tags: list[str],
    lowered_tags: set[str] | None,
    card_data: dict[str, Any] | None,
) -> dict[str, str]:
    lowered = _normalized_lowered_tags(tags, lowered_tags)
    card_data = card_data or {}
    combined_parts = [repo_id_lower, *lowered]
    for value in _base_models(card_data.get("base_model")):
        combined_parts.append(value.lower())
    pre_card_combined = " ".join(combined_parts)
    if (
        "gemma-4" not in pre_card_combined
        and "gemma4" not in pre_card_combined
        and "qat" not in pre_card_combined
    ):
        return {}
    raw_card_tags = card_data.get("tags")
    if raw_card_tags:
        combined_parts.extend(tag.lower() for tag in _string_list(raw_card_tags))
    combined = " ".join(combined_parts)
    if ("gemma-4" not in combined and "gemma4" not in combined) or "qat" not in combined:
        return {}

    unsupported_format = _gemma4_qat_unsupported_format(combined)
    if unsupported_format:
        return {"enabled": "true", "unsupported_format": unsupported_format}

    if "mlx" not in combined:
        return {"enabled": "true", "unsupported_format": "non_mlx"}

    organization = _repo_organization(repo_id_lower)
    return {
        "enabled": "true",
        "asset_format": "mlx",
        "organization": organization,
        "auto_supported": "true" if organization == GEMMA4_QAT_AUTOMATIC_ORG else "false",
    }


def _gemma4_qat_unsupported_format(value: str) -> str:
    if "mobile-transformers" in value or "mobile_transformers" in value:
        return "mobile_transformers"
    if "litert" in value or "lite-rt" in value or "tflite" in value:
        return "litert"
    if "compressed-tensors" in value or "compressed_tensors" in value or "-ct" in value:
        return "compressed_tensors"
    if "q4_0-unquantized" in value and "mlx" not in value:
        return "compressed_tensors"
    return ""


def _repo_organization(repo_id: str) -> str:
    separator_index = repo_id.find("/")
    if separator_index < 0:
        return ""
    return repo_id[:separator_index].lower()


def _gated(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "none", "no", "0", "auto"}
    return False


def _normalized_pipeline_tag(value: str) -> str:
    return value.strip().lower()
