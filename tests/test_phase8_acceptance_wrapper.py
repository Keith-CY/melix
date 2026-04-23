from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_phase8_acceptance_wrapper_uses_explicit_python_over_polluted_path(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    wrapper = repo_root / "scripts" / "run_phase8_acceptance_bundle.sh"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    bad_python = fake_bin / "python3"
    bad_python.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    bad_python.chmod(0o755)
    marker = tmp_path / "argv.txt"
    good_python = tmp_path / "good-python"
    good_python.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"-c\" ]; then exit 0; fi\n"
        "printf '%s\\n' \"$@\" > \"$MELIX_PHASE8_WRAPPER_TEST_MARKER\"\n"
        "printf 'WRAPPER_OK\\n'\n",
        encoding="utf-8",
    )
    good_python.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    env["MELIX_PHASE8_ACCEPTANCE_PYTHON"] = str(good_python)
    env["MELIX_PHASE8_WRAPPER_TEST_MARKER"] = str(marker)

    completed = subprocess.run(
        ["bash", str(wrapper), "--help"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == "WRAPPER_OK\n"
    argv = marker.read_text(encoding="utf-8").splitlines()
    assert argv[0] == str(repo_root / "scripts" / "phase8_acceptance_bundle.py")
    assert argv[1:] == ["--help"]


def test_make_phase8_acceptance_uses_wrapper() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")

    assert "bash scripts/run_phase8_acceptance_bundle.sh $(PHASE8_ACCEPTANCE_ARGS)" in makefile
