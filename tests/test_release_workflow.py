"""The release workflow's Package step: its Python snippet names each build's archive the
way installed copies look for it."""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from papermini.support.update_service import UpdateService

WORKFLOW = yaml.safe_load(
    (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
    ).read_text(encoding="utf-8")
)
BUILD = WORKFLOW["jobs"]["build"]
TARGETS = [entry["target"] for entry in BUILD["strategy"]["matrix"]["include"]]
PACKAGE = next(step for step in BUILD["steps"] if step.get("name") == "Package")


@pytest.mark.parametrize("target", TARGETS)
def test_package_step_names_the_archive_installed_copies_look_for(target):
    """The snippet once imported a module that had been renamed, so every release
    build failed at this step."""
    snippet = re.search(r'python -c \\\s*"([^"]+)"', PACKAGE["run"])
    assert snippet is not None
    result = subprocess.run(
        [sys.executable, "-c", snippet.group(1), "1.2.3", target],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == UpdateService.asset_name("1.2.3", target)
