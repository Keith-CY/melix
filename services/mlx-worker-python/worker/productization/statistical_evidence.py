from __future__ import annotations

import math
import random
from functools import lru_cache
from statistics import NormalDist

_NORMAL_DIST = NormalDist()


def build_paired_statistical_evidence(
    *,
    paired_outcomes: tuple[int | float, ...],
    confidence_level: float,
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> dict[str, object]:
    outcomes = tuple(float(value) for value in paired_outcomes)
    sample_size = len(outcomes)
    mean_value = _mean(outcomes)
    all_values_equal = bool(outcomes) and _all_values_equal(outcomes)
    delta_accuracy = _rounded(mean_value)
    bootstrap_interval = _paired_bootstrap_interval(
        outcomes=outcomes,
        confidence_level=confidence_level,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
        all_values_equal=all_values_equal,
    )
    analytical_interval = _paired_analytical_interval(
        outcomes=outcomes,
        confidence_level=confidence_level,
        mean_value=mean_value,
        all_values_equal=all_values_equal,
    )
    return {
        "sample_size": sample_size,
        "delta_accuracy": delta_accuracy,
        "bootstrap": bootstrap_interval,
        "analytical": analytical_interval,
    }


def classify_release_verdict(
    *,
    delta_accuracy: float,
    effect_threshold: float,
    bootstrap_interval: dict[str, object],
    analytical_interval: dict[str, object],
) -> dict[str, object]:
    signed_threshold = abs(float(effect_threshold))
    signed_delta = float(delta_accuracy)
    threshold_passed = abs(signed_delta) >= signed_threshold
    bootstrap_sign = _interval_sign(bootstrap_interval)
    analytical_sign = _interval_sign(analytical_interval)
    both_intervals_same_side = bootstrap_sign != 0 and bootstrap_sign == analytical_sign

    if not threshold_passed:
        verdict = "inconclusive"
        reason = "delta_below_effect_threshold"
    elif not both_intervals_same_side:
        verdict = "inconclusive"
        reason = "confidence_intervals_cross_zero"
    elif signed_delta > 0:
        verdict = "improvement"
        reason = "delta_exceeds_threshold_with_supported_intervals"
    else:
        verdict = "regression"
        reason = "delta_exceeds_threshold_with_supported_intervals"

    return {
        "verdict": verdict,
        "reason": reason,
        "effect_threshold": _rounded(signed_threshold),
        "delta_accuracy": _rounded(signed_delta),
        "threshold_passed": threshold_passed,
        "both_intervals_same_side": both_intervals_same_side,
    }


def build_category_breakdown(
    *,
    rows: tuple[dict[str, object], ...],
) -> dict[str, dict[str, object]]:
    category_totals: dict[str, list[int]] = {}
    for row in rows:
        try:
            raw_category_label = row["category_label"]
        except KeyError:
            continue
        category_label = (
            raw_category_label.strip()
            if isinstance(raw_category_label, str)
            else str(raw_category_label).strip()
        )
        if not category_label:
            continue
        totals = category_totals.get(category_label)
        if totals is None:
            totals = [0, 0, 0]
            category_totals[category_label] = totals
        totals[0] += 1
        if row.get("base_correct", False):
            totals[1] += 1
        if row.get("target_correct", False):
            totals[2] += 1

    breakdown: dict[str, dict[str, object]] = {}
    for category_label, totals in sorted(category_totals.items()):
        sample_size, base_correct, target_correct = totals
        inverse_sample_size = 1.0 / sample_size
        base_accuracy = _rounded(base_correct * inverse_sample_size)
        target_accuracy = _rounded(target_correct * inverse_sample_size)
        breakdown[category_label] = {
            "sample_size": sample_size,
            "base_accuracy": base_accuracy,
            "target_accuracy": target_accuracy,
            "delta_accuracy": _rounded(target_accuracy - base_accuracy),
        }
    return breakdown


def _paired_bootstrap_interval(
    *,
    outcomes: tuple[float, ...],
    confidence_level: float,
    bootstrap_iterations: int,
    bootstrap_seed: int,
    all_values_equal: bool | None = None,
) -> dict[str, object]:
    if not outcomes or bootstrap_iterations <= 0:
        return _interval_payload(
            method="paired_bootstrap_percentile",
            confidence_level=confidence_level,
            lower_bound=0.0,
            upper_bound=0.0,
            iterations=max(int(bootstrap_iterations), 0),
            seed=int(bootstrap_seed),
        )

    values_equal = all_values_equal if all_values_equal is not None else _all_values_equal(outcomes)
    if values_equal:
        return _interval_payload(
            method="paired_bootstrap_percentile",
            confidence_level=confidence_level,
            lower_bound=outcomes[0],
            upper_bound=outcomes[0],
            iterations=int(bootstrap_iterations),
            seed=int(bootstrap_seed),
        )

    sampler = random.Random(bootstrap_seed)
    sample_size = len(outcomes)
    inverse_sample_size = 1.0 / sample_size
    choices = sampler.choices
    replicates: list[float] = []
    append_replicate = replicates.append
    for _ in range(bootstrap_iterations):
        append_replicate(sum(choices(outcomes, k=sample_size)) * inverse_sample_size)

    alpha = (1.0 - confidence_level) / 2.0
    replicates.sort()
    return _interval_payload(
        method="paired_bootstrap_percentile",
        confidence_level=confidence_level,
        lower_bound=_ordered_percentile(replicates, alpha),
        upper_bound=_ordered_percentile(replicates, 1.0 - alpha),
        iterations=int(bootstrap_iterations),
        seed=int(bootstrap_seed),
    )


def _all_values_equal(values: tuple[float, ...]) -> bool:
    iterator = iter(values)
    first_value = next(iterator)
    return all(value == first_value for value in iterator)


def _paired_analytical_interval(
    *,
    outcomes: tuple[float, ...],
    confidence_level: float,
    mean_value: float | None = None,
    all_values_equal: bool | None = None,
) -> dict[str, object]:
    if not outcomes:
        return _interval_payload(
            method="paired_difference_normal_approximation",
            confidence_level=confidence_level,
            lower_bound=0.0,
            upper_bound=0.0,
        )

    resolved_mean = _mean(outcomes) if mean_value is None else mean_value
    values_equal = all_values_equal if all_values_equal is not None else _all_values_equal(outcomes)
    if len(outcomes) == 1 or values_equal:
        margin = 0.0
    else:
        variance = sum((value - resolved_mean) ** 2 for value in outcomes) / (len(outcomes) - 1)
        standard_error = math.sqrt(variance) / math.sqrt(len(outcomes))
        z_value = _two_sided_normal_z_value(confidence_level)
        margin = z_value * standard_error

    return _interval_payload(
        method="paired_difference_normal_approximation",
        confidence_level=confidence_level,
        lower_bound=resolved_mean - margin,
        upper_bound=resolved_mean + margin,
    )


def _interval_payload(
    *,
    method: str,
    confidence_level: float,
    lower_bound: float,
    upper_bound: float,
    iterations: int | None = None,
    seed: int | None = None,
) -> dict[str, object]:
    payload = {
        "method": method,
        "confidence_level": float(confidence_level),
        "lower_bound": _rounded(lower_bound),
        "upper_bound": _rounded(upper_bound),
    }
    payload["crosses_zero"] = payload["lower_bound"] <= 0.0 <= payload["upper_bound"]
    if iterations is not None:
        payload["iterations"] = iterations
    if seed is not None:
        payload["seed"] = seed
    return payload


def _interval_sign(interval: dict[str, object]) -> int:
    if bool(interval.get("crosses_zero", False)):
        return 0
    lower_bound = float(interval.get("lower_bound", 0.0))
    upper_bound = float(interval.get("upper_bound", 0.0))
    if lower_bound > 0.0 and upper_bound > 0.0:
        return 1
    if lower_bound < 0.0 and upper_bound < 0.0:
        return -1
    return 0


@lru_cache(maxsize=32)
def _two_sided_normal_z_value(confidence_level: float) -> float:
    bounded_confidence = min(max(float(confidence_level), 0.0), 1.0)
    percentile = 0.5 + (bounded_confidence / 2.0)
    bounded_percentile = min(max(percentile, 1e-12), 1.0 - 1e-12)
    return _NORMAL_DIST.inv_cdf(bounded_percentile)


def _mean(values: list[float] | tuple[float, ...]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    return _ordered_percentile(sorted(values), percentile)


def _ordered_percentile(ordered: list[float], percentile: float) -> float:
    if not ordered:
        return 0.0
    bounded_percentile = min(max(percentile, 0.0), 1.0)
    if len(ordered) == 1:
        return ordered[0]
    position = bounded_percentile * (len(ordered) - 1)
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    if lower_index == upper_index:
        return lower_value
    fraction = position - lower_index
    return lower_value + (upper_value - lower_value) * fraction


def _percentile_ordered(ordered: list[float], percentile: float) -> float:
    return _ordered_percentile(ordered, percentile)


def _rounded(value: float) -> float:
    return round(float(value), 4)
