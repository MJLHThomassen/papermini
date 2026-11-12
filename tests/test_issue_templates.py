"""The GitHub issue forms: valid structure, and the bug report's fields that papermini's
Report a problem fills in through the URL."""

from pathlib import Path

import pytest
import yaml

TEMPLATES = Path(__file__).resolve().parents[1] / ".github" / "ISSUE_TEMPLATE"
FORMS = sorted(p for p in TEMPLATES.glob("*.yml") if p.name != "config.yml")
FIELD_TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_there_are_a_bug_report_and_a_feature_request():
    assert {p.name for p in FORMS} == {"bug_report.yml", "feature_request.yml"}


@pytest.mark.parametrize("path", FORMS, ids=lambda p: p.name)
def test_form_structure(path):
    form = _load(path)
    assert form["name"] and form["description"]
    ids = []
    for item in form["body"]:
        assert item["type"] in FIELD_TYPES
        attrs = item["attributes"]
        if item["type"] == "markdown":
            assert attrs["value"]
            continue
        assert attrs["label"]
        assert item["id"].replace("-", "").replace("_", "").isalnum()
        ids.append(item["id"])
    assert len(ids) == len(set(ids)), "field ids must be unique"


def test_bug_report_keeps_the_fields_papermini_fills_in():
    """Released versions fill these in through the URL, so they must keep their ids and
    stay text fields (only inputs and textareas can be filled in that way)."""
    fields = {item["id"]: item for item in _load(TEMPLATES / "bug_report.yml")["body"]
              if "id" in item}
    for fid in ("version", "os", "runs-as", "traceback"):
        assert fields[fid]["type"] in ("input", "textarea"), fid
    # a log can only be dragged into a textarea that is not rendered as code
    assert fields["log"]["type"] == "textarea" and "render" not in fields["log"]["attributes"]


def test_config_keeps_blank_issues_for_the_maintainer_and_links_the_docs():
    cfg = _load(TEMPLATES / "config.yml")
    assert cfg["blank_issues_enabled"] is False  # GitHub still offers it to maintainers
    assert any(link["url"].endswith("docs/reference.md") for link in cfg["contact_links"])
    assert (TEMPLATES.parents[1] / "docs" / "reference.md").is_file()
