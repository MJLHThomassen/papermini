"""The CI and release workflows run the justfile's recipes, not their own commands for the
same tasks."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
# a recipe's first line: its name, its parameters, then a colon that does not start :=
RECIPE = re.compile(r"^([A-Za-z][\w-]*)\b[^:\n]*:(?!=)", re.MULTILINE)
RECIPES = set(RECIPE.findall((ROOT / "justfile").read_text(encoding="utf-8")))
JUST_CALL = re.compile(r"^\s*just ([\w-]+)", re.MULTILINE)
# commands of tasks that have a recipe
OWN_COMMAND = re.compile(
    r"uv sync|pytest|ruff |ty check|pyinstaller|scripts/", re.IGNORECASE
)


def _run_scripts(path: Path) -> list[str]:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        step["run"]
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "run" in step
    ]


def test_the_justfile_parses_into_its_recipes():
    assert {"setup", "test", "coverage", "lint", "build", "sign-release"} <= RECIPES
    assert not {"set", "export", "uv_run"} & RECIPES


def test_the_workflows_call_only_recipes_that_exist():
    called = {
        name
        for path in WORKFLOWS
        for run in _run_scripts(path)
        for name in JUST_CALL.findall(run)
    }
    assert called
    assert called <= RECIPES, called - RECIPES


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_the_workflow_runs_no_command_that_a_recipe_runs(path):
    for run in _run_scripts(path):
        assert not OWN_COMMAND.search(run), run
