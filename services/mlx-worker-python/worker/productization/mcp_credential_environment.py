from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import urlparse


MCP_CONFIG_PATH_ENV = "MELIX_MCP_CONFIG_PATH"
MCP_CREDENTIAL_KEYS_ENV = "MELIX_MCP_CREDENTIAL_ENV_KEYS"
MCP_ENVIRONMENT_KEY_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")
MCP_HTTP_HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
MCP_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MCP_CREDENTIAL_HEADER_PATTERN = re.compile(
    r"(?:authorization|cookie|credential|password|private[_-]?key|"
    r"secret|signature|token|api[_-]?key)",
    re.IGNORECASE,
)
MAX_MCP_CONFIG_BYTES = 1_048_576
MAX_MCP_CONFIG_SOURCES = 256
MAX_MCP_CREDENTIAL_REFERENCES = 1_024
MAX_MCP_CREDENTIAL_KEY_BYTES = 255
MAX_MCP_CREDENTIAL_KEY_LIST_BYTES = 32_768
MAX_MCP_REFERENCE_TARGET_BYTES = 255
MAX_MCP_REFERENCE_TARGET_LIST_BYTES = 32_768
MAX_MCP_JSON_NESTING_DEPTH = 128
MAX_MCP_JSON_VALUE_TOKENS = 16_384
MAX_MCP_JSON_OBJECT_MEMBERS = 8_192


def _current_user_home() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def _reject_duplicate_json_object_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant: {value}")


def _reject_json_float(value: str) -> object:
    raise ValueError(f"JSON floating-point number is not allowed: {value}")


def _validate_json_tree(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    value_tokens = 0
    object_members = 0
    while stack:
        current, depth = stack.pop()
        value_tokens += 1
        if (
            depth > MAX_MCP_JSON_NESTING_DEPTH
            or value_tokens > MAX_MCP_JSON_VALUE_TOKENS
        ):
            raise ValueError("JSON structure exceeds its budget")
        if isinstance(current, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in current):
                raise ValueError("JSON contains a lone surrogate")
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, dict):
            object_members += len(current)
            if object_members > MAX_MCP_JSON_OBJECT_MEMBERS:
                raise ValueError("JSON object members exceed their budget")
            for key, item in current.items():
                if any(0xD800 <= ord(character) <= 0xDFFF for character in key):
                    raise ValueError("JSON contains a lone surrogate")
                stack.append((item, depth + 1))

NON_CREDENTIAL_PARENT_ENVIRONMENT_KEYS = (
    "HOME",
    "PATH",
    "TMPDIR",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "DEVELOPER_DIR",
    "SDKROOT",
    "TOOLCHAINS",
    MCP_CONFIG_PATH_ENV,
)

COMMON_CHILD_ENVIRONMENT_KEYS = (
    *NON_CREDENTIAL_PARENT_ENVIRONMENT_KEYS,
    "MELIX_APP_BUNDLE_PATH", "MELIX_REPO_ROOT", "MELIX_CLI",
    "MELIX_LOGICAL_PRODUCT_ID", "MELIX_PACKAGING_TARGET_ID", "MELIX_PACKAGING_KIND",
    "MELIX_PRODUCT_VERSION", "MELIX_UPDATE_CHANNEL_PATH", "MELIX_HOME",
    "MELIX_RUNTIME_DIR", "MELIX_MANAGED_MODEL_ROOT", "MELIX_AUDIO_RUNTIME_PACK_ROOT",
    "MELIX_MODEL_OPS_JOBS_ROOT", "MELIX_EVALUATION_JOBS_ROOT",
    "MELIX_GATEWAY_CONFIG_STORE_PATH", "MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH",
    "MELIX_IMAGE_DEFAULTS_STORE_PATH", "MELIX_PRODUCT_MANIFEST_PATH",
    "MELIX_HTTP_HOST", "MELIX_HTTP_CONNECT_HOST", "MELIX_HTTP_PORT",
    "MELIX_GATEWAY_RUNTIME_BINDING_AUTHORITY", "MELIX_BACKEND_MODE",
    "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE", "MELIX_LOGS_DIR",
    "MELIX_CONTROL_PLANE_METRICS_PATH", "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH",
    "MELIX_PYTHON_WORKER_METRICS_PATH", "MELIX_MENU_BAR_STARTUP_SURFACE",
    "MELIX_MENU_BAR_PRESENTATION_MODE", "MELIX_PYTHON_BRIDGE_EXECUTABLE",
    "MELIX_ACTIVE_RUNTIME_PATH", "PYTHONPATH", "PYTHONUNBUFFERED",
    "PYTHONPYCACHEPREFIX", "PYTHONNOUSERSITE", "PYTHONSAFEPATH",
)

CONTROL_PLANE_PARENT_ENVIRONMENT_KEYS = (
    "MELIX_ARTIFACT_PATH",
    "MELIX_AUTO_CLEANUP_POLICY",
    "MELIX_BENCHMARK_REPEATS",
    "MELIX_BENCHMARK_WARMUP",
    "MELIX_DATASET_CACHE_PATH",
    "MELIX_DEFAULT_DTYPE",
    "MELIX_DEFAULT_QUANTIZATION",
    "MELIX_DEV_EMBED_BACKEND_ID",
    "MELIX_DEV_EMBED_DIMENSIONS",
    "MELIX_DEV_EMBED_FAMILY_ID",
    "MELIX_DEV_EMBED_MODEL_PATH",
    "MELIX_DEV_EMBED_NORMALIZATION",
    "MELIX_DEV_EMBED_POOLING_MODE",
    "MELIX_DEV_IMAGE_FAMILY_ID",
    "MELIX_DEV_IMAGE_MODEL_PATH",
    "MELIX_DEV_IMAGE_TASK_KIND",
    "MELIX_DEV_RERANK_FAMILY_ID",
    "MELIX_DEV_RERANK_MODEL_PATH",
    "MELIX_DEV_TEXT_FAMILY_ID",
    "MELIX_DEV_TEXT_MODEL_PATH",
    "MELIX_EVAL_SAMPLE_SIZE",
    "MELIX_LOG_RETENTION_DAYS",
    "MELIX_MAX_CONCURRENT_JOBS",
    "MELIX_MEMORY_PRESSURE_THRESHOLD",
    "MELIX_MODEL_CACHE_PATH",
    "MELIX_ALLOWED_HOSTS",
    "MELIX_ALLOWED_ORIGINS",
    "MELIX_CONNECTION_DISCONNECT_GRACE_SECONDS",
    "MELIX_CONNECTION_KEEPALIVE_INTERVAL_SECONDS",
    "MELIX_CONNECTION_RESUME_BUFFER_LIMIT",
    "MELIX_CONNECTION_RETRY_BACKOFF_SECONDS",
    "MELIX_CONNECTION_RETRY_LIMIT",
    "MELIX_DEV_RERANK_BACKEND_ID",
    "MELIX_DEV_RERANK_SCORING_MODE",
    "MELIX_DEV_RERANK_YES_NO_LABELS",
    "MELIX_GATEWAY_ACCELERATION_MODE",
    "MELIX_GATEWAY_ACCELERATION_PROFILE",
    "MELIX_GATEWAY_API_KEYS_JSON",
    "MELIX_GATEWAY_AUTH_MODE",
    "MELIX_GATEWAY_BEARER_TOKEN",
    "MELIX_GATEWAY_BEARER_TOKEN_HINT",
    "MELIX_GATEWAY_BEARER_TOKEN_ID",
    "MELIX_GATEWAY_BEARER_TOKEN_LABEL",
    "MELIX_GATEWAY_COMPLETION_BATCH_SIZE",
    "MELIX_GATEWAY_CONCURRENT_PROCESSING_ENABLED",
    "MELIX_GATEWAY_DEFAULT_MAX_TOKENS",
    "MELIX_GATEWAY_DEFAULT_TEMPERATURE",
    "MELIX_GATEWAY_DEFAULT_TOP_P",
    "MELIX_GATEWAY_DRAFT_MODEL_ID",
    "MELIX_GATEWAY_MAX_CONCURRENT_REQUESTS",
    "MELIX_GATEWAY_MAX_CONCURRENT_SEQUENCES",
    "MELIX_GATEWAY_MULTIMODAL_ROUTE_POLICY",
    "MELIX_GATEWAY_NUM_DRAFT_TOKENS",
    "MELIX_GATEWAY_PREFILL_BATCH_SIZE",
    "MELIX_GATEWAY_RATE_LIMIT_PER_MINUTE",
    "MELIX_GATEWAY_SHARED_ACCESS_ENABLED",
    "MELIX_GATEWAY_SPECULATIVE_ROUTE_POLICY",
    "MELIX_GATEWAY_STREAM_INTERVAL_TOKENS",
    "MELIX_GATEWAY_TIMEOUT_SECONDS",
    "MELIX_IMAGE_DEFAULT_EDIT_MODEL_ID",
    "MELIX_IMAGE_DEFAULT_GENERATE_MODEL_ID",
    "MELIX_IMAGE_DEFAULT_GUIDANCE",
    "MELIX_IMAGE_DEFAULT_NEGATIVE_PROMPT",
    "MELIX_IMAGE_DEFAULT_SIZE",
    "MELIX_IMAGE_DEFAULT_STEPS",
    "MELIX_IMAGE_DEFAULT_STRENGTH",
    "MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS",
    "MELIX_MCP_HIGH_RISK_ALLOWLIST",
    "MELIX_MODEL_IDLE_TIMEOUT_SECONDS",
    "MELIX_PERSISTENT_AUTH_SESSION_TTL_SECONDS",
    "MELIX_PRIVACY_DETECTOR_MODE",
    "MELIX_ROUTE_SELECTION_RECEIPT_PATH",
)

CONTROL_PLANE_SECRET_ENVIRONMENT_KEYS = (
    "MELIX_API_KEY",
    "MELIX_HF_TOKEN",
    "MELIX_HUGGINGFACE_TOKEN",
    "MELIX_GATEWAY_API_KEYS_JSON",
    "MELIX_GATEWAY_AUTH_MODE",
    "MELIX_GATEWAY_BEARER_TOKEN",
    "MELIX_GATEWAY_BEARER_TOKEN_HINT",
    "MELIX_GATEWAY_BEARER_TOKEN_ID",
    "MELIX_GATEWAY_BEARER_TOKEN_LABEL",
    "MELIX_GATEWAY_SHARED_ACCESS_ENABLED",
    "MELIX_MCP_HIGH_RISK_ALLOWLIST",
)

STRIP_ONLY_RESERVED_ENVIRONMENT_KEYS = (
    "MELIX_API_KEY",
    "MELIX_HF_TOKEN",
    "MELIX_HUGGINGFACE_TOKEN",
)

CLI_PARENT_ENVIRONMENT_KEYS = (
    "MELIX_BATCH_MODEL_DIR",
    "MELIX_BATCH_MODEL_INDEX",
    "MELIX_BATCH_MODEL_LIST",
    "MELIX_BATCH_MODEL_REPO_ID",
    "MELIX_BATCH_MODEL_TEMP_DIR",
    "MELIX_BATCH_PREFLIGHT",
    "MELIX_BATCH_RUN_ID",
    "MELIX_BENCH_BATCH_FACTOR",
    "MELIX_BENCH_BATCH_SIZE",
    "MELIX_BENCH_CONTEXT_LENGTH",
    "MELIX_BENCH_GENERATION_LENGTH",
    "MELIX_BENCH_REPEATS",
    "MELIX_BENCH_SAMPLE_SIZE",
    "MELIX_BENCH_SUITE",
    "MELIX_CONTINUE_ON_FAILURE",
    "MELIX_DOWNLOAD_ROOT",
    "MELIX_EVAL_BATCH_FACTOR",
    "MELIX_EVAL_DATASET_ID",
    "MELIX_EVAL_SCORING_MODE",
    "MELIX_EVAL_SAMPLE_SIZE",
    "MELIX_EVAL_SUITE",
    "MELIX_INSTALL_METHOD",
    "MELIX_JUDGE_MODEL",
    "MELIX_JUDGE_SERVER_ID",
    "MELIX_MAX_MODELS",
    "MELIX_MLX_LM",
    "MELIX_PROJECT_ROOT",
    "MELIX_PROBE_MODE",
    "MELIX_PUBLIC_CLI_PATH",
    "MELIX_RESTART_STACK_PER_MODEL",
    "MELIX_RUN_ID",
    "MELIX_RUN_TMP_ROOT",
    "MELIX_SERVICE_INSTANCE_NAME",
    "MELIX_START_INDEX",
    "MELIX_UPDATE_CHANNEL",
    "MELIX_UV",
)

APP_PARENT_ENVIRONMENT_KEYS = (
    *CLI_PARENT_ENVIRONMENT_KEYS,
    "MELIX_CONTROL_PLANE_PID",
    "MELIX_MENU_BAR_TERMINATION_MODE",
    "MELIX_PYTHON_WORKER_PID",
    "MELIX_SWIFT_WORKER_PID",
    "MELIX_PUBLIC_CLI_PATH",
    "MELIX_APP_SCREENSHOT_CAPTURE",
    "MELIX_APP_SCREENSHOT_APP_PATH",
    "MELIX_APP_SCREENSHOT_HEIGHT",
    "MELIX_APP_SCREENSHOT_OUTPUT_DIR",
    "MELIX_APP_SCREENSHOT_WIDTH",
    "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE",
    "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_BENCH_SUITES",
    "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_CLI_BUNDLE_PATH",
    "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_DATASET",
    "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_SUITES",
    "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_LOCAL_MODEL_PATH",
    "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MATRIX_SUITES",
    "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MODEL_ID",
    "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_SERVER_SESSION_ID",
    "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TIMESTAMP",
    "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TRAINING_FIXTURE",
    "MELIX_DEV_RERANK_BACKEND_ID",
    "MELIX_DEV_RERANK_SCORING_MODE",
    "MELIX_DEV_RERANK_YES_NO_LABELS",
    "MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS",
)

SWIFT_WORKER_PARENT_ENVIRONMENT_KEYS = (
    "MELIX_DETERMINISTIC_VLM_DELAY_MS", "MELIX_DEV_OCR_MODEL_PATH",
    "MELIX_DEV_TEXT_MODEL_PATH", "MELIX_DEV_VLM_MODEL_PATH",
    "MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE", "MELIX_SWIFT_BASELINE_DECODE_PROBE",
    "MELIX_SWIFT_BATCH_DECODE_FORCE_MODEL_EVAL_PROBE", "MELIX_SWIFT_DFLASH_PROBE",
    "MELIX_SWIFT_DFLASH_PROBE_PATH", "MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT",
    "MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_COHORT_PENDING_WINDOW_MS",
    "MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_PENDING_WINDOW_MS",
    "MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT", "MELIX_SWIFT_TEXT_WORKER_FAMILY",
    "MELIX_SWIFT_TEXT_WORKER_ID", "MELIX_SWIFT_TEXT_WORKER_INITIAL_CACHE_BLOCKS",
    "MELIX_SWIFT_TEXT_WORKER_MODEL_LOAD_HEADROOM_BYTES",
    "MELIX_SWIFT_TEXT_WORKER_PREFILL_MEMORY_HEADROOM_BYTES",
    "MELIX_SWIFT_TEXT_WORKER_PREFILL_QUADRATIC_GUARD_TOKEN_THRESHOLD",
    "MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES",
    "MELIX_SWIFT_TEXT_WORKER_RUNTIME_CACHE_FINGERPRINT",
    "MELIX_SWIFT_TEXT_WORKER_RUNTIME_VERSION", "MELIX_SWIFT_TEXT_WORKER_STARTUP_T0_NS",
    "MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE", "MELIX_SWIFT_VISION_PAYLOAD_RECEIPT_PATH",
    "MELIX_SWIFT_VISION_WORKER_BACKEND_MODE", "MELIX_SWIFT_VISION_WORKER_CACHE_ROOT",
    "MELIX_SWIFT_VISION_WORKER_DETERMINISTIC_DELAY_MS", "MELIX_SWIFT_VISION_WORKER_ID",
    "MELIX_SWIFT_VISION_WORKER_METRICS_PATH",
    "MELIX_SWIFT_VISION_WORKER_RUNTIME_CACHE_FINGERPRINT",
    "MELIX_SWIFT_VISION_WORKER_RUNTIME_VERSION", "MELIX_SWIFT_VISION_WORKER_SOCKET_PATH",
    "MELIX_SWIFT_WORKER_FAMILY",
)

PYTHON_WORKER_OWNED_ENVIRONMENT_KEYS = (
    "MELIX_APP_PROCESS_PID",
    "MELIX_COMPUTER_BROKER_CAPABILITY_FILE",
    "MELIX_COMPUTER_BROKER_DIR",
    "MELIX_COMPUTER_BROKER_PID",
    "MELIX_COMPUTER_BROKER_PRIVATE_KEY_FILE",
    "MELIX_COMPUTER_BROKER_PROTOCOL_VERSION",
    "MELIX_COMPUTER_BROKER_PUBLIC_KEY_BASE64",
    "MELIX_COMPUTER_BROKER_PUBLIC_KEY_FILE",
    "MELIX_COMPUTER_BROKER_RPC_TIMEOUT_MS",
    "MELIX_DETERMINISTIC_MULTIMODAL_DELAY_MS",
    "MELIX_DEV_SPEECH_MODEL_PATH",
    "MELIX_DEV_TEXT_ROUTE_KIND",
    "MELIX_DEV_TRANSCRIBE_MODEL_PATH",
    "MELIX_DEV_VLM_FAMILY_ID",
    "MELIX_ENABLE_TEST_CACHE_HOOKS",
    "MELIX_EVALUATION_PROBE_ANOMALY_LIMIT",
    "MELIX_EVALUATION_PROBE_SAMPLE_LIMIT",
    "MELIX_EVALUATION_PROBE_TOP_N",
    "MELIX_GIT_BRANCH",
    "MELIX_GIT_COMMIT",
    "MELIX_GIT_DIRTY",
    "MELIX_HOMEBREW_BIN_DIR",
    "MELIX_HTTP_READY_URL",
    "MELIX_LOGICAL_PRODUCT_IDENTITY",
    "MELIX_MLX_AUDIO_KOKORO_MODEL_PATH",
    "MELIX_MLX_AUDIO_PARAKEET_MODEL_PATH",
    "MELIX_MLX_AUDIO_QWEN3_TTS_MODEL_PATH",
    "MELIX_MLX_AUDIO_WHISPER_MODEL_PATH",
    "MELIX_PREFIX_CACHE_COLD_DIR",
    "MELIX_PREFIX_CACHE_COLD_MAX_BYTES",
    "MELIX_PROBE_MODE",
    "MELIX_PYTHON_WORKER_MODEL_LOAD_HEADROOM_BYTES",
    "MELIX_PYTHON_WORKER_PROCESS_MEMORY_BUDGET_BYTES",
    "MELIX_PYTHON_WORKER_STARTUP_T0_NS",
    "MELIX_RELEASE_OBSERVABILITY_OVERHEAD_ITERATIONS",
    "MELIX_RELEASE_OBSERVABILITY_OVERHEAD_SAMPLES",
    "MELIX_RUN_TOKEN",
    "MELIX_TEXT_NATIVE_MTP_PREFILL_STEP_SIZE",
    "MELIX_VLM_TEXT_BATCH_MAX_BATCH_SIZE",
    "MELIX_VLM_TEXT_BATCH_PREFILL_STEP_SIZE",
    "MELIX_WATCHDOG_COMPUTER_BROKER_PID",
    "MELIX_WATCHDOG_CONTROL_PLANE_PID",
    "MELIX_WATCHDOG_PYTHON_WORKER_PID",
    "MELIX_WATCHDOG_SWIFT_WORKER_PID",
)

LAUNCHER_INTERNAL_ENVIRONMENT_KEYS = (
    "MELIX_APP_PROCESS_PID",
    "MELIX_CLANG_MODULE_CACHE_PATH",
    "MELIX_COMPUTER_BROKER_CAPABILITY_FILE",
    "MELIX_COMPUTER_BROKER_DIR",
    "MELIX_COMPUTER_BROKER_PID",
    "MELIX_COMPUTER_BROKER_PRIVATE_KEY_FILE",
    "MELIX_COMPUTER_BROKER_PUBLIC_KEY_FILE",
    "MELIX_CONTROL_PLANE_PID",
    "MELIX_HTTP_READY",
    "MELIX_PYTHON_WORKER_PID",
    "MELIX_RUN_TOKEN",
    "MELIX_SOCKET_DIR",
    "MELIX_SWIFT_HOME",
    "MELIX_SWIFT_WORKER_PID",
    "MELIX_WATCHDOG_COMPUTER_BROKER_PID",
    "MELIX_WATCHDOG_CONTROL_PLANE_PID",
    "MELIX_WATCHDOG_PYTHON_WORKER_PID",
    "MELIX_WATCHDOG_SWIFT_WORKER_PID",
)

PRIVATE_SERVICE_ENVIRONMENT_KEYS = (
    "MELIX_WORKER_SOCKET_PATH",
    "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH",
    "MELIX_SWIFT_VISION_WORKER_SOCKET_PATH",
    "MELIX_CONTROL_PLANE_SOCKET_PATH",
    "MELIX_COMPUTER_BROKER_SOCKET",
    "MELIX_COMPUTER_BROKER_CLIENT_INSTANCE_ID",
    "MELIX_COMPUTER_BROKER_CALLER_BUNDLE_ID",
    "MELIX_COMPUTER_BROKER_CALLER_TEAM_ID",
    "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE",
    "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD",
    "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_FD",
    "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY",
    "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_BASE64",
    "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_BASE64",
)

# The Python worker is the only process that resolves MCP credential references,
# but it is not a general-purpose parent-environment credential escrow.  Keep
# this role contract explicit and add the active config's initial references at
# launch time via ``python_worker_parent_environment``.
PYTHON_WORKER_PARENT_ENVIRONMENT_KEYS = tuple(
    dict.fromkeys(
        (
            *COMMON_CHILD_ENVIRONMENT_KEYS,
            *(
                key
                for key in CONTROL_PLANE_PARENT_ENVIRONMENT_KEYS
                if key not in CONTROL_PLANE_SECRET_ENVIRONMENT_KEYS
            ),
            *PYTHON_WORKER_OWNED_ENVIRONMENT_KEYS,
            "MELIX_MODEL_ROOTS",
            "MELIX_DEV_OCR_MODEL_PATH",
            "MELIX_DEV_VLM_MODEL_PATH",
            "MELIX_DETERMINISTIC_VLM_DELAY_MS",
        )
    )
)
PYTHON_WORKER_PARENT_ENVIRONMENT_KEYS = tuple(
    key
    for key in PYTHON_WORKER_PARENT_ENVIRONMENT_KEYS
    if key not in PRIVATE_SERVICE_ENVIRONMENT_KEYS
    and key not in LAUNCHER_INTERNAL_ENVIRONMENT_KEYS
    and key not in STRIP_ONLY_RESERVED_ENVIRONMENT_KEYS
)

MCP_CREDENTIAL_RESERVED_ENVIRONMENT_KEYS = frozenset(
    (
        *PRIVATE_SERVICE_ENVIRONMENT_KEYS,
        *NON_CREDENTIAL_PARENT_ENVIRONMENT_KEYS,
        *COMMON_CHILD_ENVIRONMENT_KEYS,
        *CONTROL_PLANE_PARENT_ENVIRONMENT_KEYS,
        *STRIP_ONLY_RESERVED_ENVIRONMENT_KEYS,
        *APP_PARENT_ENVIRONMENT_KEYS,
        *SWIFT_WORKER_PARENT_ENVIRONMENT_KEYS,
        *PYTHON_WORKER_OWNED_ENVIRONMENT_KEYS,
        *LAUNCHER_INTERNAL_ENVIRONMENT_KEYS,
        MCP_CONFIG_PATH_ENV,
        MCP_CREDENTIAL_KEYS_ENV,
        "MELIX_MODEL_ROOTS",
        "MELIX_SWIFT_MLX_METALLIB_PATH",
        "MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE",
        "MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE",
        "MELIX_SWIFT_DFLASH_PROBE",
        "MELIX_SWIFT_DFLASH_PROBE_PATH",
        "MELIX_DEV_TEXT_MODEL_PATH",
        "MELIX_DEV_VLM_MODEL_PATH",
        "PATH",
        "HOME",
        "PYTHONPATH",
        "UV_CACHE_DIR",
        "CLANG_MODULE_CACHE_PATH",
        "MELIX_REPO_ROOT",
        "MELIX_HOME",
        "MELIX_RUNTIME_DIR",
        "MELIX_SERVICE_INSTANCE_NAME",
        "MELIX_MANAGED_MODEL_ROOT",
        "MELIX_AUDIO_RUNTIME_PACK_ROOT",
        "MELIX_MODEL_OPS_JOBS_ROOT",
        "MELIX_EVALUATION_JOBS_ROOT",
        "MELIX_GATEWAY_CONFIG_STORE_PATH",
        "MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH",
        "MELIX_IMAGE_DEFAULTS_STORE_PATH",
        "MELIX_HTTP_HOST",
        "MELIX_HTTP_CONNECT_HOST",
        "MELIX_HTTP_PORT",
        "MELIX_BACKEND_MODE",
        "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE",
        "MELIX_PYTHON_BRIDGE_EXECUTABLE",
        "MELIX_MENU_BAR_STARTUP_SURFACE",
        "MELIX_MENU_BAR_PRESENTATION_MODE",
        "MELIX_MENU_BAR_TERMINATION_MODE",
    )
)


def non_credential_parent_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source_environment = os.environ if environment is None else environment
    return {
        key: source_environment[key]
        for key in NON_CREDENTIAL_PARENT_ENVIRONMENT_KEYS
        if key in source_environment
    }


def control_plane_parent_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source_environment = os.environ if environment is None else environment
    return {
        **non_credential_parent_environment(source_environment),
        **{
            key: source_environment[key]
            for key in CONTROL_PLANE_PARENT_ENVIRONMENT_KEYS
            if key in source_environment
        },
    }


def app_parent_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source_environment = os.environ if environment is None else environment
    return {
        **non_credential_parent_environment(source_environment),
        **{
            key: source_environment[key]
            for key in APP_PARENT_ENVIRONMENT_KEYS
            if key in source_environment
        },
    }


def swift_worker_parent_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source_environment = os.environ if environment is None else environment
    return {
        **non_credential_parent_environment(source_environment),
        **{
            key: source_environment[key]
            for key in SWIFT_WORKER_PARENT_ENVIRONMENT_KEYS
            if key in source_environment
        },
    }


def python_worker_parent_environment(
    environment: Mapping[str, str] | None = None,
    *,
    credential_keys: Sequence[str] = (),
) -> dict[str, str]:
    source_environment = os.environ if environment is None else environment
    validated_credential_keys = bounded_mcp_credential_environment_key_union(
        credential_keys
    )
    allowed_keys = (*PYTHON_WORKER_PARENT_ENVIRONMENT_KEYS, *validated_credential_keys)
    result = {
        key: source_environment[key]
        for key in allowed_keys
        if key in source_environment
    }
    result[MCP_CREDENTIAL_KEYS_ENV] = ",".join(validated_credential_keys)
    return result


def bounded_mcp_credential_environment_key_union(
    *key_collections: Sequence[str],
) -> tuple[str, ...]:
    keys: dict[str, None] = {}
    encoded_bytes = 0
    for collection in key_collections:
        for key in collection:
            if (
                not isinstance(key, str)
                or not MCP_ENVIRONMENT_KEY_PATTERN.fullmatch(key)
                or len(key.encode("utf-8")) > MAX_MCP_CREDENTIAL_KEY_BYTES
                or key in MCP_CREDENTIAL_RESERVED_ENVIRONMENT_KEYS
            ):
                raise RuntimeError(
                    "Active MCP config is invalid; refusing to launch the app."
                )
            if key in keys:
                continue
            if keys:
                encoded_bytes += 1
            encoded_bytes += len(key.encode("utf-8"))
            keys[key] = None
            if (
                len(keys) > MAX_MCP_CREDENTIAL_REFERENCES
                or encoded_bytes > MAX_MCP_CREDENTIAL_KEY_LIST_BYTES
            ):
                raise RuntimeError(
                    "Active MCP config is invalid; refusing to launch the app."
                )
    return tuple(keys)


def validate_frozen_mcp_credential_environment_key_snapshot(
    initial_keys: Sequence[str],
    current_keys: Sequence[str],
) -> tuple[str, ...]:
    validated_initial = bounded_mcp_credential_environment_key_union(initial_keys)
    validated_current = bounded_mcp_credential_environment_key_union(current_keys)
    if not set(validated_current).issubset(validated_initial):
        raise RuntimeError(
            "Active MCP credential references changed; restart Melix."
        )
    return validated_initial


def active_mcp_credential_environment_keys(
    *,
    environment: Mapping[str, str] | None = None,
    melix_home_dir: Path | None = None,
) -> tuple[str, ...]:
    source_environment = os.environ if environment is None else environment
    configured_path = normalized_explicit_mcp_config_path(source_environment)
    if configured_path:
        config_path = Path(configured_path)
        config_required = True
    else:
        resolved_home = melix_home_dir
        if resolved_home is None:
            raw_home = source_environment.get("MELIX_HOME", "").strip()
            if raw_home:
                resolved_home = Path(raw_home).expanduser()
            else:
                environment_home = source_environment.get("HOME", "").strip()
                user_home = (
                    Path(environment_home)
                    if environment_home and Path(environment_home).is_absolute()
                    else _current_user_home()
                )
                resolved_home = user_home / ".melix"
        config_path = resolved_home / "config/mcp-tools.json"
        config_required = False

    try:
        resolved_config_path = config_path.resolve(strict=True)
    except FileNotFoundError as exc:
        if not config_required:
            return ()
        raise RuntimeError(
            "Active MCP config is unreadable; refusing to launch the app."
        ) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError(
            "Active MCP config is unreadable; refusing to launch the app."
        ) from exc

    open_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        open_flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(resolved_config_path, open_flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(
                "Active MCP config is unreadable; refusing to launch the app."
            )
        if metadata.st_size < 0 or metadata.st_size > MAX_MCP_CONFIG_BYTES:
            raise RuntimeError(
                "Active MCP config is too large; refusing to launch the app."
            )
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = -1
            encoded_payload = handle.read(MAX_MCP_CONFIG_BYTES + 1)
    except RuntimeError:
        raise
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            "Active MCP config is unreadable; refusing to launch the app."
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if len(encoded_payload) > MAX_MCP_CONFIG_BYTES:
        raise RuntimeError("Active MCP config is too large; refusing to launch the app.")
    try:
        payload = json.loads(
            encoded_payload,
            object_pairs_hook=_reject_duplicate_json_object_keys,
            parse_constant=_reject_nonstandard_json_constant,
            parse_float=_reject_json_float,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise RuntimeError("Active MCP config is invalid; refusing to launch the app.") from exc
    try:
        _validate_json_tree(payload)
    except (ValueError, RecursionError) as exc:
        raise RuntimeError(
            "Active MCP config is invalid; refusing to launch the app."
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
    if "default_parser_mode" in payload and not isinstance(
        payload["default_parser_mode"], str
    ):
        raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) > MAX_MCP_CONFIG_SOURCES:
        raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")

    credential_keys: set[str] = set()
    encoded_credential_key_bytes = 0
    reference_count = 0
    encoded_reference_target_bytes = 0
    http_header_count = 0
    encoded_http_header_bytes = 0
    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        raw_source_id = source.get("source_id")
        if not isinstance(raw_source_id, str):
            raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        source_id = raw_source_id.strip().lower()
        if (
            not MCP_SOURCE_ID_PATTERN.fullmatch(source_id)
            or source_id in source_ids
        ):
            raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        source_ids.add(source_id)
        for field_name in ("enabled",):
            if field_name in source and not isinstance(source[field_name], bool):
                raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        for field_name in ("namespaces", "redaction_terms"):
            if field_name in source and (
                not isinstance(source[field_name], list)
                or any(not isinstance(value, str) for value in source[field_name])
            ):
                raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        for field_name, maximum in (
            ("request_timeout_ms", 0xFFFF_FFFF),
            ("connect_timeout_ms", 0xFFFF_FFFF),
            ("max_result_bytes", 0xFFFF_FFFF_FFFF_FFFF),
        ):
            if field_name in source:
                value = source[field_name]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                    or value > maximum
                ):
                    raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        if "configuration_revision" in source and not isinstance(
            source["configuration_revision"], str
        ):
            raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        if "transport" not in source:
            continue
        transport = source["transport"]
        if not isinstance(transport, dict):
            raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        transport_kind = transport.get("kind")
        if transport_kind == "stdio":
            if any(
                field_name in transport
                for field_name in ("url", "headers", "header_environment_references")
            ):
                raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
            command = transport.get("command")
            arguments = transport.get("arguments", [])
            working_directory = transport.get("working_directory", "")
            if (
                not isinstance(command, str)
                or not command.strip()
                or "\x00" in command
                or not isinstance(arguments, list)
                or any(not isinstance(argument, str) for argument in arguments)
                or not isinstance(working_directory, str)
                or (
                    bool(working_directory)
                    and not Path(working_directory).is_absolute()
                )
            ):
                raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        elif transport_kind == "streamable_http":
            if any(
                field_name in transport
                for field_name in (
                    "command",
                    "arguments",
                    "working_directory",
                    "environment_references",
                )
            ):
                raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
            url = transport.get("url")
            if not isinstance(url, str) or not url.strip():
                raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
            try:
                parsed_url = urlparse(url)
                parsed_hostname = parsed_url.hostname
            except ValueError as exc:
                raise RuntimeError(
                    "Active MCP config is invalid; refusing to launch the app."
                ) from exc
            if (
                parsed_url.scheme not in {"http", "https"}
                or not parsed_hostname
                or parsed_url.username is not None
                or parsed_url.password is not None
                or "#" in url
                or (
                    parsed_url.scheme == "http"
                    and parsed_hostname not in {"localhost", "127.0.0.1", "::1"}
                )
            ):
                raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        else:
            raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        headers = transport.get("headers", {})
        if not isinstance(headers, dict):
            raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        source_http_header_names: set[str] = set()
        for header_name, header_value in headers.items():
            if (
                not isinstance(header_name, str)
                or not isinstance(header_value, str)
                or len(header_name.encode("utf-8")) > MAX_MCP_REFERENCE_TARGET_BYTES
                or not MCP_HTTP_HEADER_NAME_PATTERN.fullmatch(header_name)
                or MCP_CREDENTIAL_HEADER_PATTERN.search(header_name)
            ):
                raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
            normalized_header_name = header_name.lower()
            if normalized_header_name in source_http_header_names:
                raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
            source_http_header_names.add(normalized_header_name)
            http_header_count += 1
            encoded_http_header_bytes += len(header_name.encode("utf-8"))
            if http_header_count > 1:
                encoded_http_header_bytes += 1
            if (
                http_header_count > MAX_MCP_CREDENTIAL_REFERENCES
                or encoded_http_header_bytes > MAX_MCP_REFERENCE_TARGET_LIST_BYTES
            ):
                raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
        reference_field_names = (
            ("environment_references",)
            if transport_kind == "stdio"
            else ("header_environment_references",)
        )
        for field_name in reference_field_names:
            references = transport.get(field_name, {})
            if not isinstance(references, dict):
                raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
            for child_key, source_key in references.items():
                if not isinstance(child_key, str) or not isinstance(source_key, str):
                    raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
                child_key_bytes = len(child_key.encode("utf-8"))
                if (
                    child_key_bytes > MAX_MCP_REFERENCE_TARGET_BYTES
                    or (
                        field_name == "environment_references"
                        and not MCP_ENVIRONMENT_KEY_PATTERN.fullmatch(child_key)
                    )
                    or (
                        field_name == "header_environment_references"
                        and not MCP_HTTP_HEADER_NAME_PATTERN.fullmatch(child_key)
                    )
                ):
                    raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
                if field_name == "header_environment_references":
                    normalized_header_name = child_key.lower()
                    if normalized_header_name in source_http_header_names:
                        raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
                    source_http_header_names.add(normalized_header_name)
                    http_header_count += 1
                    encoded_http_header_bytes += child_key_bytes
                    if http_header_count > 1:
                        encoded_http_header_bytes += 1
                    if (
                        http_header_count > MAX_MCP_CREDENTIAL_REFERENCES
                        or encoded_http_header_bytes
                        > MAX_MCP_REFERENCE_TARGET_LIST_BYTES
                    ):
                        raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
                reference_count += 1
                encoded_reference_target_bytes += child_key_bytes
                if reference_count > 1:
                    encoded_reference_target_bytes += 1
                if (
                    reference_count > MAX_MCP_CREDENTIAL_REFERENCES
                    or encoded_reference_target_bytes
                    > MAX_MCP_REFERENCE_TARGET_LIST_BYTES
                ):
                    raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
                if (
                    not MCP_ENVIRONMENT_KEY_PATTERN.fullmatch(source_key)
                    or len(source_key.encode("utf-8")) > MAX_MCP_CREDENTIAL_KEY_BYTES
                ):
                    raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
                if source_key in MCP_CREDENTIAL_RESERVED_ENVIRONMENT_KEYS:
                    raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
                if source_key not in credential_keys:
                    if credential_keys:
                        encoded_credential_key_bytes += 1
                    encoded_credential_key_bytes += len(source_key.encode("utf-8"))
                    credential_keys.add(source_key)
                if len(credential_keys) > MAX_MCP_CREDENTIAL_REFERENCES:
                    raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
                if encoded_credential_key_bytes > MAX_MCP_CREDENTIAL_KEY_LIST_BYTES:
                    raise RuntimeError("Active MCP config is invalid; refusing to launch the app.")
    return tuple(sorted(credential_keys))


def normalized_explicit_mcp_config_path(
    environment: Mapping[str, str] | None = None,
) -> str | None:
    source_environment = os.environ if environment is None else environment
    configured_path = source_environment.get(MCP_CONFIG_PATH_ENV, "").strip()
    if not configured_path:
        return None
    is_current_user_tilde = configured_path == "~" or configured_path.startswith("~/")
    if (
        "\x00" in configured_path
        or len(configured_path.encode("utf-8")) > 4_096
        or not (Path(configured_path).is_absolute() or is_current_user_tilde)
    ):
        raise RuntimeError("Active MCP config path is invalid; refusing to launch the app.")
    if is_current_user_tilde:
        raw_home = source_environment.get("HOME", "").strip()
        home = (
            Path(raw_home)
            if raw_home and Path(raw_home).is_absolute()
            else _current_user_home()
        )
        suffix = configured_path[2:].lstrip("/") if configured_path != "~" else ""
        path = home / suffix
    else:
        path = Path(configured_path)
    normalized = os.path.abspath(os.path.normpath(os.fspath(path)))
    if normalized.startswith("//"):
        normalized = f"/{normalized.lstrip('/')}"
    return normalized


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print active MCP credential environment key names, one per line."
    )
    parser.add_argument("--melix-home")
    parser.add_argument("--normalize-explicit-path", action="store_true")
    parser.add_argument("--validate-key-union", action="store_true")
    parser.add_argument("--validate-frozen-key-snapshot", action="store_true")
    args = parser.parse_args(argv)
    if args.normalize_explicit_path:
        print(normalized_explicit_mcp_config_path(os.environ) or "")
        return 0
    if args.validate_key_union:
        encoded_payload = sys.stdin.buffer.read(
            MAX_MCP_CREDENTIAL_KEY_LIST_BYTES * 2 + 4_097
        )
        if len(encoded_payload) > MAX_MCP_CREDENTIAL_KEY_LIST_BYTES * 2 + 4_096:
            raise RuntimeError(
                "Active MCP config is invalid; refusing to launch the app."
            )
        try:
            raw_keys = encoded_payload.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                "Active MCP config is invalid; refusing to launch the app."
            ) from exc
        for key in bounded_mcp_credential_environment_key_union(raw_keys):
            print(key)
        return 0
    if args.validate_frozen_key_snapshot:
        encoded_payload = sys.stdin.buffer.read(
            MAX_MCP_CREDENTIAL_KEY_LIST_BYTES * 2 + 4_097
        )
        if len(encoded_payload) > MAX_MCP_CREDENTIAL_KEY_LIST_BYTES * 2 + 4_096:
            raise RuntimeError(
                "Active MCP config is invalid; refusing to launch the app."
            )
        try:
            initial_payload, current_payload = encoded_payload.split(b"\0", 1)
            initial_keys = initial_payload.decode("utf-8").splitlines()
            current_keys = current_payload.decode("utf-8").splitlines()
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError(
                "Active MCP config is invalid; refusing to launch the app."
            ) from exc
        for key in validate_frozen_mcp_credential_environment_key_snapshot(
            initial_keys,
            current_keys,
        ):
            print(key)
        return 0
    if not args.melix_home:
        parser.error("--melix-home is required unless validating a key union")
    for key in active_mcp_credential_environment_keys(
        environment=os.environ,
        melix_home_dir=Path(args.melix_home),
    ):
        print(key)
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
