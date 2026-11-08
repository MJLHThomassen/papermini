"""Release notes for a version tag: every commit since the previous version tag.

    python scripts/release_notes.py v1.2.0 [--repo owner/name] [-o notes.md]

Commits are grouped by their Conventional Commit type (features, fixes, ...), with
breaking changes also listed first. Each line names the pull request the commit came in
with, when there was one. Merge commits themselves are left out. The release workflow
uses this instead of GitHub's generated notes, which list only pull request titles.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

# (type, heading), in the order the groups appear
GROUPS = [
    ("feat", "Features"),
    ("fix", "Bug fixes"),
    ("perf", "Performance"),
    ("refactor", "Refactoring"),
    ("docs", "Documentation"),
    ("test", "Tests"),
    ("build", "Build"),
    ("ci", "Continuous integration"),
    ("style", "Style"),
    ("chore", "Chores"),
    ("revert", "Reverts"),
]
OTHER = "Other changes"

SUBJECT = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?: (?P<desc>.+)$")
MERGED_PR = re.compile(r"^Merge pull request #(\d+)")
SQUASHED_PR = re.compile(r"\(#(\d+)\)$")


def git(*args: str, cwd: Optional[str] = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True, encoding="utf-8").stdout


@dataclass
class Commit:
    sha: str
    subject: str
    body: str
    pr: Optional[int] = None

    @property
    def parsed(self):
        return SUBJECT.match(self.subject)

    @property
    def kind(self) -> Optional[str]:
        m = self.parsed
        return m["type"] if m and m["type"] in dict(GROUPS) else None

    @property
    def breaking(self) -> bool:
        m = self.parsed
        return bool(m and m["bang"]) or bool(
            re.search(r"^BREAKING[ -]CHANGE:", self.body, re.M))

    def line(self) -> str:
        m = self.parsed
        if m and self.kind:
            text = m["desc"]
            if m["scope"]:
                text = f"**{m['scope']}:** {text}"
        else:
            text = self.subject
        refs = self.sha[:7] + (f", #{self.pr}" if self.pr else "")
        return f"- {text} ({refs})"


def previous_tag(tag: str, cwd: Optional[str] = None) -> Optional[str]:
    """The newest version tag before ``tag`` in its history, or None for the first."""
    try:
        return git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", f"{tag}^",
                   cwd=cwd).strip() or None
    except subprocess.CalledProcessError:
        return None


def commits(rev_range: str, cwd: Optional[str] = None) -> List[Commit]:
    """The non-merge commits in ``rev_range``, newest first, each with its pull request."""
    sep, end = "\x1f", "\x1e"
    out = git("log", "--no-merges", f"--format=%H{sep}%s{sep}%b{end}", rev_range, cwd=cwd)
    found = []
    for rec in out.split(end):
        rec = rec.strip("\n")
        if rec:
            sha, subject, body = rec.split(sep, 2)
            m = SQUASHED_PR.search(subject)
            found.append(Commit(sha, subject, body, int(m[1]) if m else None))
    # commits that came in with a merged pull request: second parent side of its merge
    pr_of: Dict[str, int] = {}
    merges = git("log", "--merges", "--first-parent", "--format=%H %P%x1f%s", rev_range,
                 cwd=cwd)
    for line in merges.splitlines():
        shas, subject = line.split("\x1f", 1)
        m = MERGED_PR.match(subject)
        parents = shas.split()[1:]
        if not m or len(parents) < 2:
            continue
        for sha in git("rev-list", f"{parents[0]}..{parents[1]}", cwd=cwd).split():
            pr_of[sha] = int(m[1])
    for c in found:
        c.pr = c.pr or pr_of.get(c.sha)
    return found


def notes(tag: str, repo: Optional[str] = None, cwd: Optional[str] = None) -> str:
    """The notes for ``tag``; a tag that does not exist yet means the current commit, so
    the notes can be read before tagging."""
    exists = subprocess.run(["git", "rev-parse", "--verify", "-q", f"{tag}^{{commit}}"],
                            cwd=cwd, capture_output=True).returncode == 0
    rev = tag if exists else "HEAD"
    prev = previous_tag(rev, cwd)
    found = commits(f"{prev}..{rev}" if prev else rev, cwd)
    parts: List[str] = []
    breaking = [c for c in found if c.breaking]
    if breaking:
        parts.append("## ⚠ Breaking changes\n\n" + "\n".join(c.line() for c in breaking))
    for kind, heading in GROUPS + [(None, OTHER)]:
        group = [c for c in found if c.kind == kind]
        if group:
            parts.append(f"## {heading}\n\n" + "\n".join(c.line() for c in group))
    if not found:
        parts.append("No changes.")
    if repo and prev:
        parts.append(f"**Full changelog:** https://github.com/{repo}/compare/{prev}...{tag}")
    return "\n\n".join(parts) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("tag", help="the version tag to describe, e.g. v1.2.0")
    p.add_argument("--repo", help="owner/name on GitHub, for the full changelog link")
    p.add_argument("-o", "--output", help="write to this file instead of the console")
    a = p.parse_args(argv)
    text = notes(a.tag, a.repo)
    if a.output:
        with open(a.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
