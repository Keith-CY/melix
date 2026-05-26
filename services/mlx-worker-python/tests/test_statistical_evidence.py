from __future__ import annotations

import builtins
import math

import pytest

from worker.productization import statistical_evidence as statistical_evidence_module
from worker.productization.statistical_evidence import (
    _interval_sign,
    _ordered_percentile,
    _percentile,
    _percentile_ordered,
    build_category_breakdown,
    build_paired_statistical_evidence,
    classify_release_verdict,
)


def test_build_paired_statistical_evidence_reuses_float_tuple_without_normalization_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_outcomes: list[tuple[float, ...]] = []
    original_bootstrap_interval = statistical_evidence_module._paired_bootstrap_interval

    def tracking_bootstrap_interval(**kwargs: object) -> dict[str, object]:
        outcomes = kwargs["outcomes"]
        assert isinstance(outcomes, tuple)
        captured_outcomes.append(outcomes)  # type: ignore[arg-type]
        return original_bootstrap_interval(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        statistical_evidence_module,
        "_paired_bootstrap_interval",
        tracking_bootstrap_interval,
    )
    outcomes = (1.0, 0.0, -1.0, 1.0)

    evidence = build_paired_statistical_evidence(
        paired_outcomes=outcomes,
        confidence_level=0.95,
        bootstrap_iterations=16,
        bootstrap_seed=17,
    )

    assert captured_outcomes == [outcomes]
    assert captured_outcomes[0] is outcomes
    assert evidence["sample_size"] == 4


def test_build_paired_statistical_evidence_still_normalizes_non_float_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_outcomes: list[tuple[float, ...]] = []
    original_bootstrap_interval = statistical_evidence_module._paired_bootstrap_interval

    def tracking_bootstrap_interval(**kwargs: object) -> dict[str, object]:
        outcomes = kwargs["outcomes"]
        assert isinstance(outcomes, tuple)
        captured_outcomes.append(outcomes)  # type: ignore[arg-type]
        return original_bootstrap_interval(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        statistical_evidence_module,
        "_paired_bootstrap_interval",
        tracking_bootstrap_interval,
    )
    outcomes = (1, True, 0.5)

    evidence = build_paired_statistical_evidence(
        paired_outcomes=outcomes,
        confidence_level=0.95,
        bootstrap_iterations=16,
        bootstrap_seed=17,
    )

    assert captured_outcomes == [(1.0, 1.0, 0.5)]
    assert captured_outcomes[0] is not outcomes
    assert evidence["sample_size"] == 3


def test_build_paired_statistical_evidence_summarizes_outcomes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_mean(values: object) -> float:  # pragma: no cover - regression guard
        raise AssertionError(f"build_paired_statistical_evidence rescanned mean for {values!r}")

    def fail_values_equal(values: object) -> bool:  # pragma: no cover - regression guard
        raise AssertionError(f"build_paired_statistical_evidence rescanned equality for {values!r}")

    monkeypatch.setattr(statistical_evidence_module, "_mean", fail_mean)
    monkeypatch.setattr(statistical_evidence_module, "_outcome_values_equal", fail_values_equal)

    evidence = build_paired_statistical_evidence(
        paired_outcomes=(1.0, 0.0, -1.0, 1.0),
        confidence_level=0.95,
        bootstrap_iterations=8,
        bootstrap_seed=17,
    )

    assert evidence["sample_size"] == 4
    assert evidence["delta_accuracy"] == 0.25


def test_build_paired_statistical_evidence_reports_bootstrap_and_analytical_intervals() -> None:
    evidence = build_paired_statistical_evidence(
        paired_outcomes=(1, 1, 1, 0, 1, 1),
        confidence_level=0.95,
        bootstrap_iterations=200,
        bootstrap_seed=7,
    )

    assert evidence["sample_size"] == 6
    assert evidence["delta_accuracy"] == 0.8333
    assert evidence["bootstrap"]["method"] == "paired_bootstrap_percentile"
    assert evidence["bootstrap"]["iterations"] == 200
    assert evidence["bootstrap"]["seed"] == 7
    assert evidence["bootstrap"]["confidence_level"] == 0.95
    assert evidence["bootstrap"]["crosses_zero"] is False
    assert evidence["bootstrap"]["lower_bound"] < evidence["bootstrap"]["upper_bound"]
    assert evidence["analytical"]["method"] == "paired_difference_normal_approximation"
    assert evidence["analytical"]["confidence_level"] == 0.95
    assert evidence["analytical"]["crosses_zero"] is False
    assert evidence["analytical"]["lower_bound"] < evidence["analytical"]["upper_bound"]


def test_build_paired_statistical_evidence_handles_empty_and_singleton_samples() -> None:
    empty_evidence = build_paired_statistical_evidence(
        paired_outcomes=(),
        confidence_level=0.95,
        bootstrap_iterations=0,
        bootstrap_seed=7,
    )
    singleton_evidence = build_paired_statistical_evidence(
        paired_outcomes=(1,),
        confidence_level=0.95,
        bootstrap_iterations=1,
        bootstrap_seed=7,
    )

    assert empty_evidence == {
        "sample_size": 0,
        "delta_accuracy": 0.0,
        "bootstrap": {
            "method": "paired_bootstrap_percentile",
            "confidence_level": 0.95,
            "lower_bound": 0.0,
            "upper_bound": 0.0,
            "crosses_zero": True,
            "iterations": 0,
            "seed": 7,
        },
        "analytical": {
            "method": "paired_difference_normal_approximation",
            "confidence_level": 0.95,
            "lower_bound": 0.0,
            "upper_bound": 0.0,
            "crosses_zero": True,
        },
    }
    assert singleton_evidence["sample_size"] == 1
    assert singleton_evidence["delta_accuracy"] == 1.0
    assert singleton_evidence["analytical"]["lower_bound"] == 1.0
    assert singleton_evidence["analytical"]["upper_bound"] == 1.0
    assert singleton_evidence["analytical"]["crosses_zero"] is False


def test_build_paired_statistical_evidence_keeps_full_confidence_intervals_finite() -> None:
    statistical_evidence_module._two_sided_normal_z_value.cache_clear()
    evidence = build_paired_statistical_evidence(
        paired_outcomes=(1, 0, 1, 1, 0, 1),
        confidence_level=1.0,
        bootstrap_iterations=200,
        bootstrap_seed=7,
    )

    assert math.isfinite(evidence["analytical"]["lower_bound"])
    assert math.isfinite(evidence["analytical"]["upper_bound"])
    assert evidence["analytical"]["lower_bound"] <= evidence["analytical"]["upper_bound"]


def test_two_sided_normal_z_value_reuses_confidence_level_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statistical_evidence_module._two_sided_normal_z_value.cache_clear()
    calls: list[float] = []
    original_inv_cdf = statistical_evidence_module._NORMAL_DIST.inv_cdf

    class TrackingNormalDist:
        def inv_cdf(self, percentile: float) -> float:
            calls.append(percentile)
            return original_inv_cdf(percentile)

    monkeypatch.setattr(statistical_evidence_module, "_NORMAL_DIST", TrackingNormalDist())

    first = statistical_evidence_module._two_sided_normal_z_value(0.95)
    second = statistical_evidence_module._two_sided_normal_z_value(0.95)
    third = statistical_evidence_module._two_sided_normal_z_value(0.99)

    assert first == second
    assert third > second
    assert calls == [0.975, 0.995]
    statistical_evidence_module._two_sided_normal_z_value.cache_clear()


def test_bootstrap_interval_sorts_replicates_in_place(monkeypatch: pytest.MonkeyPatch) -> None:
    sorted_call_lengths: list[int] = []
    original_sorted = builtins.sorted

    def tracking_sorted(values: object, *args: object, **kwargs: object) -> list[object]:
        materialized = list(values)  # type: ignore[arg-type]
        sorted_call_lengths.append(len(materialized))
        return original_sorted(materialized, *args, **kwargs)

    monkeypatch.setattr(statistical_evidence_module, "sorted", tracking_sorted, raising=False)

    evidence = build_paired_statistical_evidence(
        paired_outcomes=(1, 0, 1, 1, -1, 0, 1, 1),
        confidence_level=0.9,
        bootstrap_iterations=64,
        bootstrap_seed=13,
    )

    assert sorted_call_lengths == []
    assert evidence["bootstrap"] == {
        "method": "paired_bootstrap_percentile",
        "confidence_level": 0.9,
        "lower_bound": 0.125,
        "upper_bound": 0.875,
        "crosses_zero": False,
        "iterations": 64,
        "seed": 13,
    }


def test_bootstrap_interval_sums_replicates_without_mean_helper_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mean_lengths: list[int] = []
    original_mean = statistical_evidence_module._mean

    def tracking_mean(values: list[float] | tuple[float, ...]) -> float:
        mean_lengths.append(len(values))
        return original_mean(values)

    monkeypatch.setattr(statistical_evidence_module, "_mean", tracking_mean)

    evidence = build_paired_statistical_evidence(
        paired_outcomes=(1, 0, 1, 1, -1, 0, 1, 1),
        confidence_level=0.9,
        bootstrap_iterations=64,
        bootstrap_seed=13,
    )

    assert mean_lengths == []
    assert evidence["bootstrap"] == {
        "method": "paired_bootstrap_percentile",
        "confidence_level": 0.9,
        "lower_bound": 0.125,
        "upper_bound": 0.875,
        "crosses_zero": False,
        "iterations": 64,
        "seed": 13,
    }


def test_bootstrap_interval_short_circuits_constant_outcomes_without_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden_random = object()

    monkeypatch.setattr(statistical_evidence_module.random, "Random", forbidden_random)

    evidence = build_paired_statistical_evidence(
        paired_outcomes=(1, 1, 1, 1, 1),
        confidence_level=0.95,
        bootstrap_iterations=1000,
        bootstrap_seed=17,
    )

    assert evidence["delta_accuracy"] == 1.0
    assert evidence["bootstrap"] == {
        "method": "paired_bootstrap_percentile",
        "confidence_level": 0.95,
        "lower_bound": 1.0,
        "upper_bound": 1.0,
        "crosses_zero": False,
        "iterations": 1000,
        "seed": 17,
    }
    assert evidence["analytical"]["lower_bound"] == 1.0
    assert evidence["analytical"]["upper_bound"] == 1.0


def test_build_paired_statistical_evidence_reuses_summary_scan_between_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    equality_scan_lengths: list[int] = []
    original_all_values_equal = statistical_evidence_module._all_values_equal

    def tracking_all_values_equal(values: tuple[float, ...]) -> bool:
        equality_scan_lengths.append(len(values))
        return original_all_values_equal(values)

    monkeypatch.setattr(statistical_evidence_module, "_all_values_equal", tracking_all_values_equal)

    evidence = build_paired_statistical_evidence(
        paired_outcomes=(1, 1, 1, 1, 1),
        confidence_level=0.95,
        bootstrap_iterations=1000,
        bootstrap_seed=17,
    )

    assert equality_scan_lengths == []
    assert evidence["bootstrap"]["lower_bound"] == 1.0
    assert evidence["bootstrap"]["upper_bound"] == 1.0
    assert evidence["analytical"]["lower_bound"] == 1.0
    assert evidence["analytical"]["upper_bound"] == 1.0


def test_build_paired_statistical_evidence_skips_equality_scan_when_endpoints_differ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        statistical_evidence_module,
        "_all_values_equal",
        lambda values: (_ for _ in ()).throw(
            AssertionError(f"unexpected full equality scan for {len(values)} values")
        ),
    )

    evidence = build_paired_statistical_evidence(
        paired_outcomes=(1.0, 1.0, 0.0),
        confidence_level=0.95,
        bootstrap_iterations=16,
        bootstrap_seed=17,
    )

    assert evidence["sample_size"] == 3
    assert evidence["bootstrap"]["lower_bound"] < evidence["bootstrap"]["upper_bound"]


def test_constant_outcome_detection_avoids_tail_slice_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SliceGuardedTuple(tuple):
        def __getitem__(self, key: object) -> object:
            if isinstance(key, slice):
                raise AssertionError("constant bootstrap detection must not slice outcomes")
            return super().__getitem__(key)

    forbidden_random = object()
    monkeypatch.setattr(statistical_evidence_module.random, "Random", forbidden_random)
    outcomes = SliceGuardedTuple((1.0,) * 512)
    with pytest.raises(AssertionError, match="must not slice outcomes"):
        _ = outcomes[1:]

    evidence = statistical_evidence_module._paired_bootstrap_interval(
        outcomes=outcomes,  # type: ignore[arg-type]
        confidence_level=0.95,
        bootstrap_iterations=1000,
        bootstrap_seed=17,
    )

    assert evidence == {
        "method": "paired_bootstrap_percentile",
        "confidence_level": 0.95,
        "lower_bound": 1.0,
        "upper_bound": 1.0,
        "crosses_zero": False,
        "iterations": 1000,
        "seed": 17,
    }


def test_classify_release_verdict_returns_inconclusive_when_any_interval_crosses_zero() -> None:
    verdict = classify_release_verdict(
        delta_accuracy=0.2,
        effect_threshold=0.1,
        bootstrap_interval={"lower_bound": 0.05, "upper_bound": 0.4, "crosses_zero": False},
        analytical_interval={"lower_bound": -0.01, "upper_bound": 0.3, "crosses_zero": True},
    )

    assert verdict["verdict"] == "inconclusive"
    assert verdict["threshold_passed"] is True
    assert verdict["both_intervals_same_side"] is False
    assert verdict["reason"] == "confidence_intervals_cross_zero"


def test_classify_release_verdict_requires_threshold_and_same_side_intervals() -> None:
    improvement = classify_release_verdict(
        delta_accuracy=0.25,
        effect_threshold=0.1,
        bootstrap_interval={"lower_bound": 0.1, "upper_bound": 0.35, "crosses_zero": False},
        analytical_interval={"lower_bound": 0.12, "upper_bound": 0.38, "crosses_zero": False},
    )
    regression = classify_release_verdict(
        delta_accuracy=-0.3,
        effect_threshold=0.1,
        bootstrap_interval={"lower_bound": -0.42, "upper_bound": -0.11, "crosses_zero": False},
        analytical_interval={"lower_bound": -0.39, "upper_bound": -0.13, "crosses_zero": False},
    )
    below_threshold = classify_release_verdict(
        delta_accuracy=0.04,
        effect_threshold=0.1,
        bootstrap_interval={"lower_bound": 0.01, "upper_bound": 0.08, "crosses_zero": False},
        analytical_interval={"lower_bound": 0.02, "upper_bound": 0.09, "crosses_zero": False},
    )

    assert improvement["verdict"] == "improvement"
    assert improvement["reason"] == "delta_exceeds_threshold_with_supported_intervals"
    assert regression["verdict"] == "regression"
    assert regression["reason"] == "delta_exceeds_threshold_with_supported_intervals"
    assert below_threshold["verdict"] == "inconclusive"
    assert below_threshold["reason"] == "delta_below_effect_threshold"


def test_statistical_helper_edges_cover_percentiles_and_interval_sign_fallbacks() -> None:
    assert _percentile([], 0.5) == 0.0
    assert _ordered_percentile([], 0.5) == 0.0
    assert _percentile([0.25], 0.5) == 0.25
    assert _percentile([0.25, 0.5, 0.75], 0.5) == 0.5
    assert _percentile_ordered([], 0.5) == 0.0
    assert _interval_sign({"lower_bound": -0.2, "upper_bound": 0.3, "crosses_zero": False}) == 0


def test_build_category_breakdown_aggregates_supported_categories_only() -> None:
    breakdown = build_category_breakdown(
        rows=(
            {"category_label": "math", "base_correct": False, "target_correct": True},
            {"category_label": "math", "base_correct": True, "target_correct": True},
            {"category_label": "history", "base_correct": True, "target_correct": False},
            {"category_label": "history"},
            {"category_label": 7, "base_correct": False, "target_correct": True},
            {"category_label": "", "base_correct": True, "target_correct": True},
        )
    )

    assert breakdown == {
        "7": {
            "sample_size": 1,
            "base_accuracy": 0.0,
            "target_accuracy": 1.0,
            "delta_accuracy": 1.0,
        },
        "history": {
            "sample_size": 2,
            "base_accuracy": 0.5,
            "target_accuracy": 0.0,
            "delta_accuracy": -0.5,
        },
        "math": {
            "sample_size": 2,
            "base_accuracy": 0.5,
            "target_accuracy": 1.0,
            "delta_accuracy": 0.5,
        },
    }


def test_build_category_breakdown_preserves_ordering_and_rounded_totals() -> None:
    rows = tuple(
        {
            "category_label": f" category-{index % 3} ",
            "base_correct": index % 2 == 0,
            "target_correct": index % 4 != 0,
        }
        for index in range(12)
    ) + (
        {"category_label": "   ", "base_correct": True, "target_correct": True},
        {"base_correct": True, "target_correct": True},
    )

    breakdown = build_category_breakdown(rows=rows)

    assert list(breakdown) == ["category-0", "category-1", "category-2"]
    assert breakdown == {
        "category-0": {
            "sample_size": 4,
            "base_accuracy": 0.5,
            "target_accuracy": 0.75,
            "delta_accuracy": 0.25,
        },
        "category-1": {
            "sample_size": 4,
            "base_accuracy": 0.5,
            "target_accuracy": 0.75,
            "delta_accuracy": 0.25,
        },
        "category-2": {
            "sample_size": 4,
            "base_accuracy": 0.5,
            "target_accuracy": 0.75,
            "delta_accuracy": 0.25,
        },
    }
