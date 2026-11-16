---
name: maintainability
description: Check papermini against its maintainability guide. `/maintainability pr` reviews the current branch before a pull request; `/maintainability audit` reviews the whole repository and proposes batches of fixes.
argument-hint: pr | audit
disable-model-invocation: true
---

# Maintainability check

The mode is `$0`.

First read `docs/maintainability.md` in full. It is the single source of
truth: the rules, how to prove a change is safe, the finding format and what
not to report. Then read `AGENTS.md`.

Then follow the steps for the mode:

- `pr`: [pr.md](pr.md). Review the current branch before opening a pull
  request.
- `audit`: [audit.md](audit.md). Review the whole repository, rank the
  findings and fix them in batches.

If the mode is empty or something else, ask which of the two to run.
