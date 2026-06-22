---
name: code-design-review
description: Review active branch changes for DRY and DOT violations, writing a report to temp/code-design-review.md. Used by eval loops — the calling agent retries until the report contains only "Code looks good."
---

# Code Design Review

Use this skill when asked to review the design quality of active branch changes. The output is a report written to `temp/code-design-review.md`. The calling agent is the consumer — it reads the report and either fixes violations or stops when the report says **"Code looks good."** (verbatim, nothing else).

The two principles enforced here are:

- **DRY** (Don't Repeat Yourself) — Every piece of logic, data, or behavior should have a single authoritative location. Duplication is a violation whether it is identical code or near-identical code with minor variation.
- **DOT** (Do One Thing) — Every function, class, and module should have one clear responsibility. A unit that does two things should be two units. The test: if you cannot name it without using "and", it fails DOT.

Do not enforce style, naming, performance, or correctness here. Focus exclusively on DRY and DOT.

---

## Phase 1: Identify Changed Files

Get the diff against the merge base of the main branch:

```
git diff $(git merge-base HEAD main)...HEAD --name-only
```

If on main or the command fails, fall back to:

```
git diff HEAD~1...HEAD --name-only
```

Filter to source files only — skip `*.md`, `*.txt`, lock files, config files, and anything under `temp/`, `.todo/`, `data/`, or `migrations/`. If no source files changed, write "Code looks good." and stop.

---

## Phase 2: Read the Diff

For each changed file, read:

1. The full current file (to understand structure and context).
2. The diff for that file (`git diff $(git merge-base HEAD main)...HEAD -- <file>`) to know which lines are new or modified.

Focus analysis on **added or changed lines**. Do not report violations that exist entirely in unchanged code — those are pre-existing issues outside the scope of this review.

---

## Phase 3: Analyze for DRY Violations

For each changed file, look for:

- **Duplicated logic** — a block of code that does the same computation or transformation as another block elsewhere in the diff or in files it imports.
- **Duplicated data** — the same literal value (string, number, dict key) appearing in multiple places where a named constant or config lookup would serve.
- **Copy-paste variants** — two or more functions that are structurally identical except for one variable, where a single parameterized function would do.
- **Re-implemented stdlib/utility behavior** — code that manually does what an existing helper (in this codebase or a standard library) already does.

A violation must be **specific and actionable**: name the duplicate sites (file + line range), describe what they share, and suggest the consolidation (extract a function, define a constant, reuse an existing helper).

---

## Phase 4: Analyze for DOT Violations

For each changed function, class, or module, ask: does it do exactly one thing?

Signs of a DOT violation:

- **"And" functions** — a function that fetches data *and* transforms it *and* writes it. Each "and" is a separate responsibility.
- **Mixed abstraction levels** — a function that mixes high-level orchestration with low-level detail in the same body.
- **God classes** — a class that owns both data modeling and I/O, or business logic and presentation.
- **Side-effect surprise** — a function whose name implies a query but also mutates state, or vice versa.
- **Oversized modules** — a module that is clearly two or more unrelated concerns stitched together.

A violation must be **specific and actionable**: name the function/class, describe the two (or more) things it does, and suggest the split.

---

## Phase 5: Write the Report

Ensure `temp/` exists at the project root (create it if not).

Write the report to `temp/code-design-review.md`.

**If there are no violations**, write exactly this and nothing else:

```
Code looks good.
```

**If there are violations**, write a report using this structure:

```markdown
# Code Design Review

## DRY Violations

### <Short title>
- **Files:** `<file>:<lines>` and `<file>:<lines>`
- **Issue:** <One sentence describing what is duplicated.>
- **Fix:** <One sentence on what to do — extract a function, define a constant, etc.>

(repeat for each DRY violation)

## DOT Violations

### <Short title>
- **Location:** `<file>` — `<FunctionOrClassName>`
- **Issue:** <One sentence describing the two or more things it does.>
- **Fix:** <One sentence on how to split it.>

(repeat for each DOT violation)
```

Omit a section entirely if there are no violations of that type. Do not include meta-commentary, summaries, or suggestions outside of violations. Keep each entry tight — one issue, one fix.

---

## Rules

- Never report pre-existing code that was not touched by this branch.
- Never flag something as a violation without a concrete fix suggestion.
- Never invent violations to appear thorough. If the code is clean, say so.
- The report is machine-read by the calling agent. The success string "Code looks good." must appear alone with no surrounding text.
