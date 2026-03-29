from __future__ import annotations

import base64
import json
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack


def test_image_generation_endpoint_returns_job_and_artifact_metadata() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-image"])
        request = urllib.request.Request(
            stack.image_generations_url(),
            data=json.dumps(
                {
                    "id": "integration-image-generate",
                    "model": "melix-dev-image",
                    "prompt": "red fox in snow",
                    "size": "256x256",
                    "n": 1,
                    "response_format": "png",
                    "artifact_namespace": "integration",
                }
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["model"] == "melix-dev-image"
        assert payload["job"]["job_id"] == "integration-image-generate::image-generate"
        assert payload["job"]["state"] == "completed"
        assert payload["data"][0]["artifact"]["role"] == "generated"
        image_bytes = base64.b64decode(payload["data"][0]["b64_json"])
        assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        assert b"PROMPT=red fox in snow" in image_bytes
        assert b"SIZE=256x256" in image_bytes
        assert b"VARIANT=0" in image_bytes
    finally:
        stack.stop()


def test_image_edit_endpoint_returns_generated_output_and_lineage() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-image"])
        request = urllib.request.Request(
            stack.image_edits_url(),
            data=json.dumps(
                {
                    "id": "integration-image-edit",
                    "model": "melix-dev-image",
                    "prompt": "add glow",
                    "image_base64": base64.b64encode(b"SOURCE").decode("ascii"),
                    "mask_base64": base64.b64encode(b"MASK").decode("ascii"),
                    "strength": 0.5,
                    "size": "256x256",
                    "n": 1,
                    "response_format": "png",
                }
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["job"]["job_id"] == "integration-image-edit::image-edit"
        assert payload["job"]["state"] == "completed"
        assert len(payload["job"]["artifacts"]) == 3
        assert payload["job"]["artifacts"][0]["role"] == "edit_source"
        assert payload["job"]["artifacts"][1]["role"] == "mask"
        assert payload["job"]["artifacts"][2]["role"] == "generated"
        image_bytes = base64.b64decode(payload["data"][0]["b64_json"])
        assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        assert b"PROMPT=add glow" in image_bytes
        assert b"SIZE=256x256" in image_bytes
        assert b"STRENGTH=0.50" in image_bytes
    finally:
        stack.stop()
