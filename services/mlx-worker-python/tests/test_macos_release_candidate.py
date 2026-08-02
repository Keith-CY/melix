from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "macos_release_candidate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("melix_macos_release_candidate", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def candidate_fixture(tmp_path: Path) -> tuple[Path, Path]:
    app = tmp_path / "Melix Release Candidate.app"
    executable = app / "Contents" / "MacOS" / "Melix"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"candidate executable")
    executable.chmod(0o755)
    resources = app / "Contents" / "Resources"
    resources.mkdir()
    (resources / "payload.txt").write_text("candidate payload\n", encoding="utf-8")
    (resources / "payload-link").symlink_to("payload.txt")
    archive = tmp_path / "Melix-release-candidate.zip"
    archive.write_bytes(b"candidate archive bytes")
    return app, archive


def test_candidate_receipt_binds_tag_source_bundle_and_archive_digests(
    tmp_path: Path,
) -> None:
    module = load_module()
    app, archive = candidate_fixture(tmp_path)
    source_sha = "a" * 40

    receipt = module.create_candidate_receipt(
        app_path=app,
        archive_path=archive,
        tag_name="v1.2.3",
        source_sha=source_sha,
    )

    assert receipt["schema_version"] == 1
    assert receipt["candidate_target_id"] == "macos_app_bundle_github_release_candidate"
    assert receipt["candidate_bundle_id"] == "io.melix.menubar.release-candidate"
    assert receipt["tag_name"] == "v1.2.3"
    assert receipt["source_sha"] == source_sha
    assert receipt["bundle_name"] == app.name
    assert receipt["bundle_tree_sha256"].startswith("sha256:")
    assert receipt["artifact_sha256"].startswith("sha256:")
    assert module.verify_candidate_receipt(
        receipt,
        app_path=app,
        archive_path=archive,
        expected_tag_name="v1.2.3",
        expected_source_sha=source_sha,
    ) == receipt


def test_candidate_receipt_round_trip_is_canonical(tmp_path: Path) -> None:
    module = load_module()
    app, archive = candidate_fixture(tmp_path)
    receipt_path = tmp_path / "candidate-receipt.json"
    receipt = module.create_candidate_receipt(
        app_path=app,
        archive_path=archive,
        tag_name="v2.0.0",
        source_sha="b" * 40,
    )

    module.write_candidate_receipt(receipt, receipt_path)

    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt
    assert receipt_path.read_text(encoding="utf-8").endswith("\n")


def test_candidate_receipt_rejects_archive_or_bundle_tampering(tmp_path: Path) -> None:
    module = load_module()
    app, archive = candidate_fixture(tmp_path)
    receipt = module.create_candidate_receipt(
        app_path=app,
        archive_path=archive,
        tag_name="v3.4.5",
        source_sha="c" * 40,
    )

    archive.write_bytes(b"tampered archive")
    with pytest.raises(ValueError, match="artifact digest"):
        module.verify_candidate_receipt(
            receipt,
            app_path=app,
            archive_path=archive,
            expected_tag_name="v3.4.5",
            expected_source_sha="c" * 40,
        )

    archive.write_bytes(b"candidate archive bytes")
    (app / "Contents" / "Resources" / "payload.txt").write_text(
        "tampered payload\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="bundle tree digest"):
        module.verify_candidate_receipt(
            receipt,
            app_path=app,
            archive_path=archive,
            expected_tag_name="v3.4.5",
            expected_source_sha="c" * 40,
        )


@pytest.mark.parametrize(
    ("tag_name", "source_sha", "message"),
    [
        ("v1.2.3-alpha", "d" * 40, "stable release tag"),
        ("v1.2.3", "not-a-sha", "source SHA"),
    ],
)
def test_candidate_receipt_rejects_invalid_identity_fields(
    tmp_path: Path,
    tag_name: str,
    source_sha: str,
    message: str,
) -> None:
    module = load_module()
    app, archive = candidate_fixture(tmp_path)

    with pytest.raises(ValueError, match=message):
        module.create_candidate_receipt(
            app_path=app,
            archive_path=archive,
            tag_name=tag_name,
            source_sha=source_sha,
        )


def test_candidate_rejects_missing_paths_and_unsupported_bundle_entry(tmp_path: Path) -> None:
    module = load_module()
    app, archive = candidate_fixture(tmp_path)

    with pytest.raises(ValueError, match="app bundle"):
        module.create_candidate_receipt(
            app_path=tmp_path / "missing.app",
            archive_path=archive,
            tag_name="v1.0.0",
            source_sha="a" * 40,
        )
    with pytest.raises(ValueError, match="archive"):
        module.create_candidate_receipt(
            app_path=app,
            archive_path=tmp_path / "missing.zip",
            tag_name="v1.0.0",
            source_sha="a" * 40,
        )

    fifo = app / "Contents/Resources/unsupported-fifo"
    fifo.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="unsupported bundle entry"):
        module._bundle_tree_digest(app)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 2, "schema version"),
        ("candidate_target_id", "wrong", "target identifier"),
        ("candidate_bundle_id", "wrong", "bundle identifier"),
        ("tag_name", 123, "must be a string"),
    ],
)
def test_candidate_receipt_rejects_shape_and_field_contracts(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    module = load_module()
    app, archive = candidate_fixture(tmp_path)
    receipt = module.create_candidate_receipt(
        app_path=app,
        archive_path=archive,
        tag_name="v1.0.0",
        source_sha="a" * 40,
    )
    receipt[field] = value

    with pytest.raises(ValueError, match=message):
        module._validate_receipt_shape(receipt)

    receipt.pop(field)
    with pytest.raises(ValueError, match="shape mismatch"):
        module._validate_receipt_shape(receipt)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("tag_name", "v1.0.1", "tag mismatch"),
        ("source_sha", "b" * 40, "source SHA mismatch"),
        ("bundle_name", "Other.app", "bundle name mismatch"),
    ],
)
def test_candidate_verifier_rejects_receipt_identity_mismatch(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    module = load_module()
    app, archive = candidate_fixture(tmp_path)
    receipt = module.create_candidate_receipt(
        app_path=app,
        archive_path=archive,
        tag_name="v1.0.0",
        source_sha="a" * 40,
    )
    receipt[field] = value

    with pytest.raises(ValueError, match=message):
        module.verify_candidate_receipt(
            receipt,
            app_path=app,
            archive_path=archive,
            expected_tag_name="v1.0.0",
            expected_source_sha="a" * 40,
        )


def test_candidate_main_create_verify_and_nonobject_receipt(tmp_path: Path) -> None:
    module = load_module()
    app, archive = candidate_fixture(tmp_path)
    receipt_path = tmp_path / "receipt.json"
    common = [
        "--app",
        str(app),
        "--archive",
        str(archive),
        "--tag",
        "v1.0.0",
        "--source-sha",
        "a" * 40,
    ]

    assert module.main(["create", *common, "--output", str(receipt_path)]) == 0
    assert module.main(["verify", "--receipt", str(receipt_path), *common]) == 0

    receipt_path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        module._read_receipt(receipt_path)
