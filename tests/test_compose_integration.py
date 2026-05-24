from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "compose-agent.sh"


def _docker_available() -> bool:
    return shutil.which("docker") is not None


@pytest.mark.skipif(not _docker_available(), reason="Docker is required for compose integration tests.")
def test_compose_wrapper_list_pending_smoke():
    down_command = [str(SCRIPT_PATH), "down", "-v"]
    try:
        result = subprocess.run(
            [str(SCRIPT_PATH), "list-pending", "--limit", "1"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        assert payload == {"count": 0, "runs": []}
    finally:
        subprocess.run(
            down_command,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
