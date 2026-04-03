from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


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
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._opener = opener or (lambda request: urlopen(request, timeout=20))

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
        items = [self._summary_record(payload) for payload in payloads]
        if mlx_only:
            items = [item for item in items if item.mlx_compatible]
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
            ("config", "false"),
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

    @staticmethod
    def _summary_record(payload: dict[str, Any]) -> HubModelSummaryRecord:
        card_data = payload.get("cardData") if isinstance(payload.get("cardData"), dict) else {}
        repo_id = _string(payload.get("id") or payload.get("modelId"))
        tags = _string_list(payload.get("tags"))
        library_name = _string(payload.get("library_name") or card_data.get("library_name"))
        sibling_files = _sibling_files(payload.get("siblings"))
        return HubModelSummaryRecord(
            repo_id=repo_id,
            author=_author(payload, repo_id),
            model_name=_model_name(repo_id),
            summary=_string(card_data.get("model_name") or payload.get("description")),
            pipeline_tag=_string(payload.get("pipeline_tag") or card_data.get("pipeline_tag")),
            tags=tags,
            downloads=_int(payload.get("downloads")),
            likes=_int(payload.get("likes")),
            mlx_compatible=_is_mlx_compatible(
                repo_id=repo_id,
                tags=tags,
                library_name=library_name,
                card_data=card_data,
            ),
            library_name=library_name,
            sibling_files=sibling_files,
            last_modified=_string(payload.get("lastModified")),
        )

    @classmethod
    def _card_record(cls, payload: dict[str, Any]) -> HubModelCardRecord:
        summary = cls._summary_record(payload)
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
        )


def _next_cursor_from_link(link_header: str) -> str:
    for raw_part in link_header.split(","):
        part = raw_part.strip()
        if 'rel="next"' not in part:
            continue
        if not part.startswith("<") or ">" not in part:
            continue
        next_url = part[1:part.index(">")]
        query = parse_qs(urlparse(next_url).query)
        return _string(query.get("cursor", [""])[0])
    return ""


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


def _is_mlx_compatible(
    *,
    repo_id: str,
    tags: list[str],
    library_name: str,
    card_data: dict[str, Any],
) -> bool:
    lowered_tags = {tag.lower() for tag in tags}
    card_tags = {
        tag.lower()
        for tag in _string_list(card_data.get("tags"))
    }
    lowered_repo_id = repo_id.lower()
    if "mlx" in lowered_tags or "mlx" in card_tags:
        return True
    if library_name.lower() == "mlx":
        return True
    if "mlx" in lowered_repo_id:
        return True
    return repo_id.startswith("mlx-community/")
