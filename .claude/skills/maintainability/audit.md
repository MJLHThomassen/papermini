# Audit the whole repository

Four reviewers each check one aspect of the guide. You merge and rank their
findings, the maintainer picks the batches to fix, and each batch becomes one
issue and one pull request.

## 1. Ask before starting the reviewers

The audit starts four `maintainability-reviewer` subagents on opus, which
costs a lot of tokens. Tell the maintainer this and wait for a clear yes.

## 2. Start the reviewers

Start all four in one message, so that they run in parallel. Use the
`maintainability-reviewer` agent and pass `model: "opus"`. Each prompt names
the aspect, its rules and where to look:

| Aspect | Rules | Where to look |
|--------|-------|---------------|
| Structure and readability | S1 to S14, G1 to G7 | `src/papermini`, `scripts`, `packaging` |
| Tests | T1 to T7 | `tests`, and `just coverage` for what the risky parts of `src/papermini` leave untested |
| Docs and writing | D1 to D7 | `README.md`, `docs`, `AGENTS.md`, docstrings and comments, CLI help, user-visible text in the GUI, `examples` |
| Tooling and release | R1 to R10 | `pyproject.toml`, `justfile`, `.github`, `packaging`, `scripts` |

## 3. Merge the findings

- **Check each finding yourself** in the code. Drop findings that are wrong,
  that no rule supports, or that the guide's "What not to report" section
  lists.
- **Merge duplicates.** Reviewers of different aspects can report the same
  problem; keep one finding and list every rule it breaks.
- **Align the batches.** Give findings that belong together one batch name,
  even when they came from different reviewers. A batch is one coherent
  change in one area that can be reviewed as one pull request.
- **Order the batches.** Rank them by benefit for effort, high benefit and
  small effort first. A batch that makes others safer, such as
  characterisation tests for code another batch refactors, goes before them.
- **Collect proposed rules.** List what the reviewers think the guide is
  missing separately.

## 4. Report

Publish the report as a private artifact page, and give the maintainer the
link. It contains:

- an overview table of the batches, with each batch's findings, benefit,
  effort and risk;
- each batch with its findings, in the guide's finding format;
- the proposed new rules for the guide.

Then wait. The maintainer replies with the batches they approve, and may
change them.

## 5. Fix the approved batches

Work through the approved batches one at a time, in the order of the report,
unless the maintainer picks another order. For each batch:

1. **Open an issue.** Ask the maintainer before creating it. The issue holds
   the batch's findings in the guide's format.
2. **Branch** from the latest `main`.
3. **Pin down weakly tested code first** with characterisation tests (T7).
4. **Make the change.** Prove it is safe as "Proving a change is safe" in the
   guide describes. A change that alters how anything looks or works needs
   the maintainer's design approval first (AGENTS.md).
5. **Review the branch** with the steps in [pr.md](pr.md).
6. **Open one pull request** that closes the issue. Then wait for the
   maintainer to merge it before starting the next batch.

## 6. Tighten the checks

- After a batch that adds tests, set `fail_under` under
  `[tool.coverage.report]` in `pyproject.toml` to the new coverage total,
  rounded down to a whole percent. Take the lower of the totals from the CI
  report and from `just coverage`, since they measure slightly differently.
- Once `just typecheck` reports nothing, remove `continue-on-error` from the
  ty step in `.github/workflows/ci.yml`, so that the type check blocks a merge
  like the other checks.
