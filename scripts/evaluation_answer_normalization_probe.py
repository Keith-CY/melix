from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.engine.evaluation_core import EvaluationCore


def _normalization_metrics() -> dict[str, float]:
    free_text_answers = tuple(
        f"Final Answer: city {index % 97} with extra spacing"
        for index in range(2400)
    )
    numeric_answers = tuple(str((index % 31) + 0.0) for index in range(300))
    option_answers = tuple(chr(ord("A") + (index % 4)) for index in range(300))
    answers = free_text_answers + numeric_answers + option_answers
    sample_count = 5
    iteration_count = 80

    original_numeric = EvaluationCore._extract_numeric_value
    original_option = EvaluationCore._extract_option_value
    elapsed_samples: list[float] = []
    numeric_call_samples: list[float] = []
    option_call_samples: list[float] = []
    checksum = 0
    for _ in range(sample_count):
        numeric_calls = 0
        option_calls = 0

        def counting_numeric(value: str) -> str | None:
            nonlocal numeric_calls
            numeric_calls += 1
            return original_numeric(value)

        def counting_option(value: str) -> str | None:
            nonlocal option_calls
            option_calls += 1
            return original_option(value)

        EvaluationCore._extract_numeric_value = staticmethod(counting_numeric)
        EvaluationCore._extract_option_value = staticmethod(counting_option)
        try:
            started = time.perf_counter()
            local_checksum = 0
            for _ in range(iteration_count):
                for answer in answers:
                    local_checksum += len(EvaluationCore._normalized_answer(answer))
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            numeric_call_samples.append(numeric_calls / iteration_count)
            option_call_samples.append(option_calls / iteration_count)
            checksum = local_checksum
        finally:
            EvaluationCore._extract_numeric_value = original_numeric
            EvaluationCore._extract_option_value = original_option

    if EvaluationCore._normalized_answer("9.0") != "9":
        raise SystemExit("unexpected numeric normalization")
    if EvaluationCore._normalized_answer("b") != "B":
        raise SystemExit("unexpected option normalization")
    if EvaluationCore._normalized_answer("Final Answer: Paris") != "final answer: paris":
        raise SystemExit("unexpected free-text normalization")

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "numeric_extract_calls_mean": statistics.fmean(numeric_call_samples),
        "option_extract_calls_mean": statistics.fmean(option_call_samples),
        "answer_count": float(len(answers)),
        "free_text_answer_count": float(len(free_text_answers)),
        "iteration_count": float(iteration_count),
        "normalization_checksum": float(checksum),
    }


def _answer_match_metrics() -> dict[str, float]:
    exact_pairs = tuple((f"city-{index % 97}", f"city-{index % 97}") for index in range(2400))
    folded_pairs = tuple(("Paris", " paris ") for _ in range(300))
    empty_pairs = tuple(("Paris", "") for _ in range(300))
    pairs = exact_pairs + folded_pairs + empty_pairs
    sample_count = 5
    iteration_count = 120
    elapsed_samples: list[float] = []
    match_count = 0
    for _ in range(sample_count):
        started = time.perf_counter()
        local_match_count = 0
        for _ in range(iteration_count):
            for expected, predicted in pairs:
                if EvaluationCore._answers_match(expected=expected, predicted=predicted):
                    local_match_count += 1
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        match_count = local_match_count

    expected_matches = (len(exact_pairs) + len(folded_pairs)) * iteration_count
    if match_count != expected_matches:
        raise SystemExit(f"unexpected answer match count: {match_count} != {expected_matches}")

    return {
        "answer_match_elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "answer_match_pair_count": float(len(pairs)),
        "answer_match_exact_pair_count": float(len(exact_pairs)),
        "answer_match_iteration_count": float(iteration_count),
        "answer_match_checksum": float(match_count),
    }


def main() -> None:
    metrics = _normalization_metrics()
    metrics.update(_answer_match_metrics())
    print(json.dumps({key: round(value, 6) for key, value in metrics.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
