from worker.runtime.deterministic_ocr_runtime import DeterministicOCRRuntime


def test_deterministic_ocr_runtime_declares_hot_path_slots() -> None:
    assert DeterministicOCRRuntime.__slots__ == (
        "_last_probe",
        "_last_single_prompt_input_bytes",
        "_last_single_prompt_request",
        "_last_single_prompt_text",
        "_last_single_prompt_token_count",
    )
