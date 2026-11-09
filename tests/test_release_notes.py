"""Release notes list every commit since the previous version tag, not just the pull
request titles (scripts/release_notes.py, used by the release workflow)."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_notes.py"
spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
rn = importlib.util.module_from_spec(spec)
sys.modules["release_notes"] = rn  # (its dataclass looks itself up there)
spec.loader.exec_module(rn)


def _git(repo, *args):
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                   cwd=repo, check=True, capture_output=True)


def _commit(repo, message):
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)


@pytest.fixture
def repo(tmp_path):
    """v0.1.0, then a pull request with three commits merged into main, a commit pushed
    straight to main, and v0.2.0."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "symbolic-ref", "HEAD", "refs/heads/main")  # (init -b needs git 2.28)
    _commit(tmp_path, "feat: first version")
    _git(tmp_path, "tag", "-a", "v0.1.0", "-m", "0.1.0")
    _git(tmp_path, "checkout", "-q", "-b", "topic")
    _commit(tmp_path, "feat(gui): a new button")
    _commit(tmp_path, "fix(sheet): keep the scale bar on the first page")
    _commit(tmp_path, "feat(cli)!: rename --old to --new\n\nBREAKING CHANGE: --old is gone")
    _git(tmp_path, "checkout", "-q", "main")
    _git(tmp_path, "merge", "-q", "--no-ff", "topic",
         "-m", "Merge pull request #7 from someone/topic")
    _commit(tmp_path, "Update the readme")
    _git(tmp_path, "tag", "-a", "v0.2.0", "-m", "0.2.0")
    return tmp_path


def test_notes_list_every_commit_with_its_pull_request(repo):
    text = rn.notes("v0.2.0", "owner/name", cwd=str(repo))
    assert "first version" not in text                      # (in the previous release)
    assert "Merge pull request" not in text
    assert "- **gui:** a new button (" in text and ", #7)" in text
    assert "## Bug fixes\n\n- **sheet:** keep the scale bar on the first page" in text
    breaking, rest = text.split("## Features")
    assert "rename --old to --new" in breaking               # also listed first
    assert "## Other changes\n\n- Update the readme (" in rest
    assert "Update the readme" in rest and "#7" not in rest.split("## Other changes")[1]
    assert text.index("## Features") < text.index("## Bug fixes") < text.index("## Other")
    assert text.rstrip().endswith("https://github.com/owner/name/compare/v0.1.0...v0.2.0")


def test_notes_can_be_read_before_tagging(repo):
    text = rn.notes("v0.3.0", "owner/name", cwd=str(repo))   # right on v0.2.0
    assert text.startswith("No changes.") and "compare/v0.2.0...v0.3.0" in text
    _commit(repo, "fix: one more thing")
    text = rn.notes("v0.3.0", "owner/name", cwd=str(repo))   # (no such tag yet)
    assert text.startswith("## Bug fixes\n\n- one more thing (")
    assert "a new button" not in text and "compare/v0.2.0...v0.3.0" in text


def test_first_release_lists_everything(repo, tmp_path):
    text = rn.notes("v0.1.0", "owner/name", cwd=str(repo))
    assert "- first version (" in text and "compare" not in text


def test_writes_a_notes_file(repo, tmp_path, monkeypatch):
    out = tmp_path / "notes.md"
    monkeypatch.chdir(repo)
    assert rn.main(["v0.2.0", "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("## ⚠ Breaking changes")
