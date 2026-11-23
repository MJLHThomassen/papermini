# Review a branch before a pull request

Review the changes of the current branch against the guide, in this session.
Don't start subagents for it.

## 1. Collect the changes

- Find the base: `git merge-base HEAD origin/main`.
- Read `git diff <base>...HEAD` and `git log <base>..HEAD`.
- Read every changed file in full where the change touches its structure, and
  the code that calls what changed. A diff alone hides most structure
  problems.

## 2. Check the changes against the guide

Check each changed part against every rule that applies to it. Look in
particular at:

- **Structure (S1 to S16, G1 to G7):** a class or function that took on a
  second job; a new option or variant that has to be added in several places;
  the core importing Qt; a new class that shares a file, or a new module-level
  function.
- **Tests (T1 to T7):** a change in behaviour without a test; a fixed bug
  without a regression test; a refactor of weakly tested code without
  characterisation tests first.
- **Docs (D1 to D7):** docs, help text, comments and the README that still
  describe the old behaviour; samples and screenshots that the change makes
  outdated; the guide itself, if the change adds a pattern it should mention.
- **Tooling (R1 to R10):** commit messages and the pull request title follow
  R7; anything that affects released versions follows R8.
- **The mistakes AGENTS.md lists.** Check comments, docs, commit messages and
  the pull request description you are about to write.

Only report what breaks a rule, and leave out what the guide's "What not to
report" section lists.

## 3. Run the checks

- `just test`
- `just lint`
- `just format --check`
- `just typecheck`. CI fails only when the total number of findings goes up
  (rule R2), so compare it with the base: the branch must not add new findings
  in the code it changes.
- If the change can alter output or the window, the other checks of
  "Proving a change is safe" in the guide.

## 4. Fix or list each finding

- **Fix** what belongs in this change: problems the branch introduced, and
  small problems in the lines it touches. Commit the fixes on the branch
  (rule R7).
- **List** the rest in the pull request description, under a heading
  "Maintainability findings not fixed here", in the guide's finding format.
  These are findings the change only brushes against, or ones that need their
  own batch.

If there is nothing to list, leave the heading out.
