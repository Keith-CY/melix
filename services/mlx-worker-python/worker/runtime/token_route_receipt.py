from __future__ import annotations

import json

_JSON_ENCODER = json.JSONEncoder(separators=(",", ":"), sort_keys=True)
_INACTIVE_RECEIPT_JSON_CACHE: dict[tuple[str, str, str, str], str] = {}
ROUTE_SAMPLE_LIMIT = 64


class TokenRouteReceipt:
    __slots__ = (
        "_enabled",
        "_fallback_raw_text_used",
        "_hidden_reasoning_token_count",
        "_last_token_route_channel",
        "_last_token_route_channel_source",
        "_last_token_route_id",
        "_next_fallback_token_id",
        "_pending_token_ids",
        "_reasoning_mode",
        "_records",
        "_route_count",
        "_router_id",
        "_router_version",
        "_sample_limit",
        "_tool_choice_policy",
        "_visible_text_token_count",
    )

    def __init__(
        self,
        *,
        router_id: str,
        router_version: str,
        reasoning_enabled: bool,
        reasoning_mode: str = "",
        tool_choice_policy: str = "",
        sample_limit: int = ROUTE_SAMPLE_LIMIT,
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._router_id = router_id
        self._router_version = router_version
        self._reasoning_mode = reasoning_mode.strip().lower() or (
            "enabled" if reasoning_enabled else "disabled"
        )
        self._tool_choice_policy = tool_choice_policy.strip().lower() or "auto"
        self._sample_limit = sample_limit
        self._pending_token_ids: list[int] = []
        self._next_fallback_token_id = 0
        self._records: list[dict[str, int | str]] = []
        self._route_count = 0
        self._visible_text_token_count = 0
        self._hidden_reasoning_token_count = 0
        self._last_token_route_id = -1
        self._last_token_route_channel = ""
        self._last_token_route_channel_source = ""
        self._fallback_raw_text_used = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def activate(self) -> None:
        self._enabled = True

    @property
    def pending_token_count(self) -> int:
        return len(self._pending_token_ids)

    def append_token_ids(self, token_ids: tuple[int, ...]) -> None:
        if not self._enabled:
            return
        self._pending_token_ids.extend(token_ids)

    def append_synthetic_token(self) -> None:
        if not self._enabled:
            return
        self._pending_token_ids.append(self._next_synthetic_token_id())

    def rollback_pending_to(self, previous_count: int) -> None:
        if not self._enabled:
            return
        if previous_count != len(self._pending_token_ids):
            del self._pending_token_ids[previous_count:]

    def record_span(
        self,
        *,
        channel: str,
        channel_source: str,
        token_count: int = 1,
        consume_all_available: bool = False,
    ) -> None:
        if not self._enabled:
            return
        normalized_token_count = int(token_count)
        if normalized_token_count <= 0:
            return
        if consume_all_available and self._pending_token_ids:
            token_ids = self._pending_token_ids
            self._pending_token_ids = []
            self._record_tokens(
                token_ids=token_ids,
                channel=channel,
                channel_source=channel_source,
            )
            return
        self._record_tokens(
            token_ids=self._route_token_ids(normalized_token_count),
            channel=channel,
            channel_source=channel_source,
        )

    def to_json(self) -> str:
        if (
            not self._enabled
            and self._last_token_route_id == -1
            and self._route_count == 0
            and not self._records
        ):
            return inactive_token_route_receipt_json(
                self._router_id,
                self._router_version,
                self._reasoning_mode,
                self._tool_choice_policy,
            )
        return _JSON_ENCODER.encode(
            {
                "router_id": self._router_id,
                "router_version": self._router_version,
                "token_id": self._last_token_route_id,
                "channel": self._last_token_route_channel,
                "channel_source": self._last_token_route_channel_source,
                "tool_choice_policy": self._tool_choice_policy,
                "reasoning_mode": self._reasoning_mode,
                "visible_text_tokens": self._visible_text_token_count,
                "hidden_reasoning_tokens": self._hidden_reasoning_token_count,
                "fallback_raw_text_used": self._fallback_raw_text_used,
                "route_tracking_enabled": self._enabled,
                "route_count": self._route_count,
                "routes_sampled": len(self._records),
                "routes": self._records,
            }
        )

    def _next_synthetic_token_id(self) -> int:
        token_id = self._next_fallback_token_id
        self._next_fallback_token_id += 1
        self._fallback_raw_text_used = True
        return token_id

    def _route_token_id(self) -> int:
        if self._pending_token_ids:
            return self._pending_token_ids.pop(0)
        return self._next_synthetic_token_id()

    def _route_token_ids(self, token_count: int) -> list[int]:
        return [self._route_token_id() for _ in range(token_count)]

    def _record_tokens(
        self,
        *,
        token_ids: list[int],
        channel: str,
        channel_source: str,
    ) -> None:
        token_count = len(token_ids)
        if not token_count:
            return
        self._route_count += token_count
        if channel == "visible_text":
            self._visible_text_token_count += token_count
        elif channel == "hidden_reasoning":
            self._hidden_reasoning_token_count += token_count
        self._last_token_route_id = token_ids[-1]
        self._last_token_route_channel = channel
        self._last_token_route_channel_source = channel_source
        sample_slots = self._sample_limit - len(self._records)
        if sample_slots <= 0:
            return
        for token_id in token_ids[:sample_slots]:
            self._records.append(
                {
                    "token_id": token_id,
                    "channel": channel,
                    "channel_source": channel_source,
                    "tool_choice_policy": self._tool_choice_policy,
                    "reasoning_mode": self._reasoning_mode,
                }
            )


def inactive_token_route_receipt_json(
    router_id: str,
    router_version: str,
    reasoning_mode: str,
    tool_choice_policy: str,
) -> str:
    cache_key = (router_id, router_version, reasoning_mode, tool_choice_policy)
    cached = _INACTIVE_RECEIPT_JSON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    payload = _JSON_ENCODER.encode(
        {
            "router_id": router_id,
            "router_version": router_version,
            "token_id": -1,
            "channel": "",
            "channel_source": "",
            "tool_choice_policy": tool_choice_policy,
            "reasoning_mode": reasoning_mode,
            "visible_text_tokens": 0,
            "hidden_reasoning_tokens": 0,
            "fallback_raw_text_used": False,
            "route_tracking_enabled": False,
            "route_count": 0,
            "routes_sampled": 0,
            "routes": [],
        }
    )
    _INACTIVE_RECEIPT_JSON_CACHE[cache_key] = payload
    return payload
