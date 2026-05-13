from __future__ import annotations

import os
from collections.abc import Mapping


GIT_LOCAL_ENV_VARS = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_OBJECT_DIRECTORY",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE",
    "GIT_INDEX_FILE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_COMMON_DIR",
)
# GIT_NAMESPACE is not scrubbed: it selects a repository namespace, not the
# caller's working tree, index, object directory, or config context.


def scrub_git_local_env(*, env: Mapping[str, str] | None = None) -> dict[str, str]:
    clean_env = dict(os.environ if env is None else env)
    for name in GIT_LOCAL_ENV_VARS:
        clean_env.pop(name, None)
    return clean_env
