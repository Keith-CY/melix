from __future__ import annotations

import json
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack


def test_models_endpoint_reports_the_warm_dev_model() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    stack.start()

    try:
        with urllib.request.urlopen(stack.models_url(), timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["object"] == "list"
        model_rows = {item["id"]: item for item in payload["data"]}
        assert model_rows["melix-dev-text"]["melix_state"] == "warm"
    finally:
        stack.stop()
