from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, TypeVar

from worker.model_ops.errors import ModelOperationError

_T = TypeVar("_T")


@dataclass(frozen=True)
class ReleaseCompareBundlePolicy:
    in_domain_suite_ids: list[str] = field(default_factory=list)
    guard_suite_ids: list[str] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)
    minimum_sample_counts: dict[str, int] = field(default_factory=dict)

    def as_manifest(self) -> dict[str, object]:
        return {
            "schema_version": "melix.lora_release_compare_bundle_policy.v1",
            "in_domain_suite_ids": list(self.in_domain_suite_ids),
            "guard_suite_ids": list(self.guard_suite_ids),
            "thresholds": dict(self.thresholds),
            "minimum_sample_counts": dict(self.minimum_sample_counts),
        }


def resolve_release_compare_bundle_policy(
    ext: dict[str, str],
    *,
    float_value: Callable[[str, float, float, str], float],
    int_value: Callable[[str, int, int, str], int],
) -> ReleaseCompareBundlePolicy:
    in_domain_suite_ids = _csv_values(
        ext.get("release_compare_in_domain_suite_ids", "")
        or ext.get("melix.release_compare.in_domain_suite_ids", "")
    )
    guard_suite_ids = _csv_values(
        ext.get("release_compare_guard_suite_ids", "")
        or ext.get("melix.release_compare.guard_suite_ids", "")
    )
    suite_ids = [*in_domain_suite_ids, *guard_suite_ids]
    return ReleaseCompareBundlePolicy(
        in_domain_suite_ids=in_domain_suite_ids,
        guard_suite_ids=guard_suite_ids,
        thresholds=_resolve_release_compare_thresholds(
            ext,
            suite_ids=suite_ids,
            float_value=float_value,
        ),
        minimum_sample_counts=_resolve_release_compare_minimum_sample_counts(
            ext,
            suite_ids=suite_ids,
            int_value=int_value,
        ),
    )


def _resolve_release_compare_thresholds(
    ext: dict[str, str],
    *,
    suite_ids: Iterable[str],
    float_value: Callable[[str, float, float, str], float],
) -> dict[str, float]:
    raw = (
        ext.get("release_compare_thresholds", "")
        or ext.get("melix.release_compare.thresholds", "")
    )
    default_raw = (
        ext.get("release_compare_default_threshold", "")
        or ext.get("melix.release_compare.default_threshold", "")
    )
    return _keyed_release_compare_values(
        raw,
        default_raw=default_raw,
        suite_ids=suite_ids,
        field_name="release_compare_thresholds",
        parse_value=lambda value, field_name: float_value(
            value,
            0.0,
            0.0,
            field_name,
        ),
    )


def _resolve_release_compare_minimum_sample_counts(
    ext: dict[str, str],
    *,
    suite_ids: Iterable[str],
    int_value: Callable[[str, int, int, str], int],
) -> dict[str, int]:
    raw = (
        ext.get("release_compare_minimum_sample_counts", "")
        or ext.get("melix.release_compare.minimum_sample_counts", "")
    )
    default_raw = (
        ext.get("release_compare_default_minimum_sample_count", "")
        or ext.get("melix.release_compare.default_minimum_sample_count", "")
    )
    return _keyed_release_compare_values(
        raw,
        default_raw=default_raw,
        suite_ids=suite_ids,
        field_name="release_compare_minimum_sample_counts",
        parse_value=lambda value, field_name: int_value(
            value,
            0,
            1,
            field_name,
        ),
    )


def _keyed_release_compare_values(
    raw_value: str,
    *,
    default_raw: str,
    suite_ids: Iterable[str],
    field_name: str,
    parse_value: Callable[[str, str], _T],
) -> dict[str, _T]:
    values: dict[str, _T] = {}
    for segment in raw_value.split(","):
        item = segment.strip()
        if not item:
            continue
        suite_id, separator, raw_suite_value = item.partition("=")
        normalized_suite_id = suite_id.strip()
        if not separator or not normalized_suite_id or not raw_suite_value.strip():
            raise ModelOperationError(
                code="invalid_argument",
                message=f"{field_name} entries must use suite_id=value.",
                details={"field": field_name, "raw_value": item},
            )
        values[normalized_suite_id] = parse_value(
            raw_suite_value.strip(),
            f"{field_name}.{normalized_suite_id}",
        )

    if default_raw.strip():
        default_value = parse_value(default_raw.strip(), f"{field_name}.default")
        for suite_id in suite_ids:
            values.setdefault(suite_id, default_value)
    return values


def _csv_values(raw_value: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_value.split(","):
        value = raw_item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values
