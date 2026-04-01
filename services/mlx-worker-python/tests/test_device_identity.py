from __future__ import annotations

from worker.productization.device_identity import (
    DeviceIdentity,
    collect_device_identity,
    hash_hostname,
)


def test_device_identity_to_dict_preserves_fields() -> None:
    device = DeviceIdentity(
        chip="Apple M2 Pro",
        memory_gb=32.0,
        os_version="15.3",
        os_build="24D60",
        hostname_hash="abcdef012345",
        melix_version="0.1.0",
    )

    payload = device.to_dict()

    assert payload["chip"] == "Apple M2 Pro"
    assert payload["memory_gb"] == 32.0
    assert payload["os_version"] == "15.3"
    assert payload["os_build"] == "24D60"
    assert payload["hostname_hash"] == "abcdef012345"
    assert payload["melix_version"] == "0.1.0"


def test_hash_hostname_is_stable_and_truncated() -> None:
    h1 = hash_hostname("my-mac.local")
    h2 = hash_hostname("my-mac.local")
    h3 = hash_hostname("other-mac.local")

    assert h1 == h2
    assert len(h1) == 12
    assert h1 != h3


def test_collect_device_identity_returns_populated_fields() -> None:
    device = collect_device_identity(
        chip="Apple M1",
        memory_gb=16.0,
        os_version="14.0",
        os_build="23A344",
        hostname_hash="aabbccddeeff",
        melix_version="0.2.0",
    )

    assert device.chip == "Apple M1"
    assert device.memory_gb == 16.0
    assert device.os_version == "14.0"
    assert device.os_build == "23A344"
    assert device.hostname_hash == "aabbccddeeff"
    assert device.melix_version == "0.2.0"


def test_collect_device_identity_detects_platform_values() -> None:
    device = collect_device_identity()

    assert device.chip != ""
    assert device.memory_gb > 0
    assert device.os_version != ""
    assert device.hostname_hash != ""
    assert len(device.hostname_hash) == 12
