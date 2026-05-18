from __future__ import annotations

import json
import statistics
import time
from types import SimpleNamespace

from worker.engine.maintenance_core import MaintenanceCore

prompt = "alpha beta gamma delta epsilon"
plain_prompt = " ".join(f"tok{index % 32}" for index in range(4096))
plain_suite = SimpleNamespace(prompt_batches=(plain_prompt,), title="unused")
contexts = (2048, 8192, 32768)
sample_count = 5
iteration_count = 120
plain_iteration_count = 2_000
elapsed_samples: list[float] = []
token_count_samples: list[float] = []
plain_count_samples: list[float] = []
for _ in range(sample_count):
    token_total = 0
    plain_total = 0
    started = time.perf_counter()
    for _ in range(iteration_count):
        for context_length in contexts:
            shaped = MaintenanceCore._shape_benchmark_prompt(prompt, context_length=context_length)
            token_count = shaped.token_count if hasattr(shaped, "token_count") else len(shaped.split())
            if token_count != context_length:
                raise SystemExit(f"unexpected token count {token_count} for {context_length}")
            token_total += token_count
    for _ in range(plain_iteration_count):
        plain_count = MaintenanceCore._benchmark_prompt_token_count(plain_prompt)
        if plain_count != 4096:
            raise SystemExit(f"unexpected plain prompt token count {plain_count}")
        default_context = MaintenanceCore._benchmark_context_lengths(
            MaintenanceCore.__new__(MaintenanceCore),
            suite=plain_suite,
            parameters={},
        )[0]
        if default_context != 4096:
            raise SystemExit(f"unexpected default context length {default_context}")
        plain_total += plain_count + default_context
    elapsed_samples.append((time.perf_counter() - started) * 1000.0)
    token_count_samples.append(float(token_total))
    plain_count_samples.append(float(plain_total))
print(
    json.dumps(
        {
            "context_count": float(len(contexts)),
            "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
            "iteration_count": float(iteration_count),
            "plain_iteration_count": float(plain_iteration_count),
            "sample_count": float(sample_count),
            "token_count_mean": round(statistics.fmean(token_count_samples), 3),
            "plain_token_count_mean": round(statistics.fmean(plain_count_samples), 3),
        },
        sort_keys=True,
    )
)
