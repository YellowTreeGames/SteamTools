---
name: dot-review
description: Analyze active branch changes for DOT (Do One Thing) violations, writing findings to temp/dot-review.md. Used by the code-design-review orchestrator. Optimized to run on Haiku.
---

# DOT Review

Check active branch changes for violations of the **DOT principle**: every function, class, and module should have one clear responsibility. If you cannot name it without using "and", it fails DOT.

Write findings to `temp/dot-review.md`. This is consumed by the adversarial-critic — be specific and concrete.

---

## Phase 1: Identify Changed Files

```
git diff $(git merge-base HEAD main)...HEAD --name-only
```

Fallback if on main or the command fails:
```
git diff HEAD~1...HEAD --name-only
```

Filter to source files only. Skip `*.md`, `*.txt`, lock files, config files, and anything under `temp/`, `.todo/`, `data/`, or `migrations/`. If no source files changed, write "No DOT violations." and stop.

---

## Phase 2: Read Changed Files

For each changed file:
1. Read the full current file (to understand structure and context).
2. Read the diff (`git diff $(git merge-base HEAD main)...HEAD -- <file>`) to know which lines are new or modified.

Focus analysis on **added or changed lines only**. Do not flag violations that exist entirely in unchanged code — those are pre-existing issues outside the scope of this review.

---

## Phase 3: Analyze for DOT Violations

For each changed function, class, or module, ask: does it do exactly one thing?

Signs of a violation:
- **"And" functions** — a function that fetches data *and* transforms it *and* writes it. Each "and" is a separate responsibility.
- **Mixed abstraction levels** — high-level orchestration mixed with low-level implementation detail in the same function body.
- **God classes** — a class that owns both data modeling and I/O, or both business logic and presentation.
- **Side-effect surprise** — a function whose name implies a query but also mutates state, or vice versa.
- **Oversized modules** — a module that is clearly two or more unrelated concerns stitched together.

Each violation must be **specific and actionable**: name the exact function or class, describe the two or more responsibilities, and suggest how to split it.

---

## Phase 4: Write the Report

Ensure `temp/` exists (create it if not). Write to `temp/dot-review.md`.

**If no violations**, write exactly:
```
No DOT violations.
```

**If violations exist**:
```markdown
## DOT Violations

### <Short title>
- **Location:** `<file>` — `<FunctionOrClassName>`
- **Issue:** <One sentence describing the two or more things it does.>
- **Fix:** <One sentence on how to split it.>
```

Repeat for each violation. Omit meta-commentary. One issue, one fix per entry.

---

## Rules

- Only report violations introduced by this branch. Never flag unchanged pre-existing code.
- Never invent violations to appear thorough. If the changed code is clean, say so.
- Every finding must have a concrete fix suggestion.
