from __future__ import annotations

import math
import random
from statistics import NormalDist


def build_paired_statistical_evidence(
    *,
    paired_outcomes: tuple[int | float, ...],
    confidence_level: float,
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> dict[str, object]:
    outcomes = tuple(float(value) for value in paired_outcomes)
    sample_size = len(outcomes)
    delta_accuracy = _rounded(_mean(outcomes))
    bootstrap_interval = _paired_bootstrap_interval(
        outcomes=outcomes,
        confidence_level=confidence_level,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    analytical_interval = _paired_analytical_interval(
        outcomes=outcomes,
        confidence_level=confidence_level,
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
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        category_label = str(row.get("category_label", "")).strip()
        if not category_label:
            continue
        grouped.setdefault(category_label, []).append(row)

    breakdown: dict[str, dict[str, object]] = {}
    for category_label in sorted(grouped):
        category_rows = grouped[category_label]
        sample_size = len(category_rows)
        base_accuracy = _rounded(
            sum(1 for row in category_rows if bool(row.get("base_correct", False)))
            / max(sample_size, 1)
        )
        target_accuracy = _rounded(
            sum(1 for row in category_rows if bool(row.get("target_correct", False)))
            / max(sample_size, 1)
        )
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

    sampler = random.Random(bootstrap_seed)
    sample_size = len(outcomes)
    replicates: list[float] = []
    for _ in range(bootstrap_iterations):
        replicate = [outcomes[sampler.randrange(sample_size)] for _ in range(sample_size)]
        replicates.append(_mean(replicate))

    alpha = (1.0 - confidence_level) / 2.0
    ordered_replicates = sorted(replicates)
    return _interval_payload(
        method="paired_bootstrap_percentile",
        confidence_level=confidence_level,
        lower_bound=_percentile_ordered(ordered_replicates, alpha),
        upper_bound=_percentile_ordered(ordered_replicates, 1.0 - alpha),
        iterations=int(bootstrap_iterations),
        seed=int(bootstrap_seed),
    )


def _paired_analytical_interval(
    *,
    outcomes: tuple[float, ...],
    confidence_level: float,
) -> dict[str, object]:
    if not outcomes:
        return _interval_payload(
            method="paired_difference_normal_approximation",
            confidence_level=confidence_level,
            lower_bound=0.0,
            upper_bound=0.0,
        )

    mean_value = _mean(outcomes)
    if len(outcomes) == 1:
        margin = 0.0
    else:
        variance = sum((value - mean_value) ** 2 for value in outcomes) / (len(outcomes) - 1)
        standard_error = math.sqrt(variance) / math.sqrt(len(outcomes))
        z_value = _two_sided_normal_z_value(confidence_level)
        margin = z_value * standard_error

    return _interval_payload(
        method="paired_difference_normal_approximation",
        confidence_level=confidence_level,
        lower_bound=mean_value - margin,
        upper_bound=mean_value + margin,
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


def _two_sided_normal_z_value(confidence_level: float) -> float:
    bounded_confidence = min(max(float(confidence_level), 0.0), 1.0)
    percentile = 0.5 + (bounded_confidence / 2.0)
    bounded_percentile = min(max(percentile, 1e-12), 1.0 - 1e-12)
    return NormalDist().inv_cdf(bounded_percentile)


def _mean(values: list[float] | tuple[float, ...]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    return _percentile_ordered(sorted(values), percentile)


def _percentile_ordered(ordered: list[float], percentile: float) -> float:
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


def _rounded(value: float) -> float:
    return round(float(value), 4)
