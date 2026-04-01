from __future__ import annotations

import hashlib
import platform
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceIdentity:
    chip: str
    memory_gb: float
    os_version: str
    os_build: str
    hostname_hash: str
    melix_version: str

    def to_dict(self) -> dict[str, object]:
        return {
            "chip": self.chip,
            "memory_gb": self.memory_gb,
            "os_version": self.os_version,
            "os_build": self.os_build,
            "hostname_hash": self.hostname_hash,
            "melix_version": self.melix_version,
        }


def hash_hostname(hostname: str) -> str:
    return hashlib.sha256(hostname.encode("utf-8")).hexdigest()[:12]


def collect_device_identity(
    *,
    chip: str | None = None,
    memory_gb: float | None = None,
    os_version: str | None = None,
    os_build: str | None = None,
    hostname_hash: str | None = None,
    melix_version: str = "0.0.0-dev",
) -> DeviceIdentity:
    return DeviceIdentity(
        chip=chip or _detect_chip(),
        memory_gb=memory_gb if memory_gb is not None else _detect_memory_gb(),
        os_version=os_version or platform.mac_ver()[0] or platform.platform(),
        os_build=os_build or _detect_os_build(),
        hostname_hash=hostname_hash or hash_hostname(platform.node()),
        melix_version=melix_version,
    )


def _detect_chip() -> str:
    try:
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return platform.machine() or "unknown"


def _detect_memory_gb() -> float:
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return round(int(result.stdout.strip()) / (1024 ** 3), 1)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return 0.0


def _detect_os_build() -> str:
    try:
        result = subprocess.run(
            ["sw_vers", "-buildVersion"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""
