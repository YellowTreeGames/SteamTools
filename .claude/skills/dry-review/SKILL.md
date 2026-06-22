---
name: dry-review
description: Analyze active branch changes for DRY (Don't Repeat Yourself) violations, writing findings to temp/dry-review.md. Used by the code-design-review orchestrator. Optimized to run on Haiku.
---

# DRY Review

Check active branch changes for violations of the **DRY principle**: every piece of logic, data, or behavior should have a single authoritative location. Duplication is a violation whether the code is identical or near-identical with minor variation.

Write findings to `temp/dry-review.md`. This is consumed by the adversarial-critic — be specific and concrete.

---

## Phase 1: Identify Changed Files

```
git diff $(git merge-base HEAD main)...HEAD --name-only
```

Fallback if on main or the command fails:
```
git diff HEAD~1...HEAD --name-only
```

Filter to source files only. Skip `*.md`, `*.txt`, lock files, config files, and anything under `temp/`, `.todo/`, `data/`, or `migrations/`. If no source files changed, write "No DRY violations." and stop.

---

## Phase 2: Read Changed Files

For each changed file:
1. Read the full current file (to understand structure and context).
2. Read the diff (`git diff $(git merge-base HEAD main)...HEAD -- <file>`) to know which lines are new or modified.

Focus analysis on **added or changed lines only**. Do not flag violations that exist entirely in unchanged code — those are pre-existing issues outside the scope of this review.

---

## Phase 3: Analyze for DRY Violations

Look for:
- **Duplicated logic** — a block of code that does the same computation or transformation as another block elsewhere in the diff or in files it imports from.
- **Duplicated data** — the same literal value (string, number, dict key) appearing in multiple places where a named constant or config lookup would serve.
- **Copy-paste variants** — two or more functions that are structurally identical except for one variable, where a single parameterized function would do.
- **Re-implemented stdlib/utility behavior** — code that manually does what an existing helper (in this codebase or the standard library) already does.

Each violation must be **specific and actionable**: name the duplicate sites (file + line range), describe what they share, and suggest the consolidation — extract a function, define a constant, reuse an existing helper, etc.

---

## Phase 4: Write the Report

Ensure `temp/` exists (create it if not). Write to `temp/dry-review.md`.

**If no violations**, write exactly:
```
No DRY violations.
```

**If violations exist**:
```markdown
## DRY Violations

### <Short title>
- **Files:** `<file>:<lines>` and `<file>:<lines>`
- **Issue:** <One sentence describing what is duplicated.>
- **Fix:** <One sentence on what to do — extract a function, define a constant, etc.>
```

Repeat for each violation. Omit meta-commentary. One issue, one fix per entry.

---

## Rules

- Only report violations introduced by this branch. Never flag unchanged pre-existing code.
- Never invent violations to appear thorough. If the changed code is clean, say so.
- Every finding must name both duplicate sites and include a concrete fix suggestion.
