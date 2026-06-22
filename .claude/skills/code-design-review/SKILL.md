---
name: code-design-review
description: Orchestrate a multi-specialist code design review (DOT, DRY, Architect, Adversarial Critic), writing a final report to temp/code-design-review.md. Used by eval loops — the calling agent retries until the report contains only "Code looks good."
---

# Code Design Review

Orchestrate a pipeline of four specialist agents reviewing the active branch changes, then update CLAUDE.md if the review passes.

The pipeline:
1. **DOT Review** (Haiku) + **DRY Review** (Haiku) + **Architect Review** (Sonnet) — run in parallel
2. **Adversarial Critic** (Sonnet) — reads all three reports and filters pedantic or speculative findings

The final report lands at `temp/code-design-review.md`. The success string the calling agent polls for is **"Code looks good."** (verbatim, nothing else in the file).

---

## Phase 1: Run the Three Specialists in Parallel

Spawn three background agents simultaneously using the Agent tool. Give each one the instructions from its skill, and specify the model explicitly.

**Agent 1 — DOT Review (model: haiku)**

Prompt:
> You are a DOT (Do One Thing) specialist. Review active branch changes for violations of the principle that every function, class, and module should have one clear responsibility.
>
> Step 1: Get changed source files via `git diff $(git merge-base HEAD main)...HEAD --name-only`. Fallback to `git diff HEAD~1...HEAD --name-only` if on main or the command fails. Filter to source files only — skip `*.md`, `*.txt`, lock files, config files, and anything under `temp/`, `.todo/`, `data/`, or `migrations/`.
>
> Step 2: For each changed source file, read the full file and its diff (`git diff $(git merge-base HEAD main)...HEAD -- <file>`). Focus analysis on added or changed lines only.
>
> Step 3: For each changed function, class, or module, ask: does it do exactly one thing? Signs of violation: "and" functions, mixed abstraction levels, god classes, side-effect surprise, oversized modules. Only flag violations introduced by this branch.
>
> Step 4: Write to `temp/dot-review.md`. If no violations, write exactly "No DOT violations." Otherwise use this format:
> ```
> ## DOT Violations
> ### <Short title>
> - **Location:** `<file>` — `<FunctionOrClassName>`
> - **Issue:** <One sentence.>
> - **Fix:** <One sentence.>
> ```
> Every finding must have a concrete fix. Never invent violations.

**Agent 2 — DRY Review (model: haiku)**

Prompt:
> You are a DRY (Don't Repeat Yourself) specialist. Review active branch changes for violations of the principle that every piece of logic, data, or behavior should have a single authoritative location.
>
> Step 1: Get changed source files via `git diff $(git merge-base HEAD main)...HEAD --name-only`. Fallback to `git diff HEAD~1...HEAD --name-only` if on main or the command fails. Filter to source files only — skip `*.md`, `*.txt`, lock files, config files, and anything under `temp/`, `.todo/`, `data/`, or `migrations/`.
>
> Step 2: For each changed source file, read the full file and its diff (`git diff $(git merge-base HEAD main)...HEAD -- <file>`). Focus analysis on added or changed lines only.
>
> Step 3: Look for duplicated logic, duplicated data literals, copy-paste variants that want to be a parameterized function, and re-implemented stdlib/utility behavior. Only flag violations introduced by this branch. Name both duplicate sites (file + line range) for every finding.
>
> Step 4: Write to `temp/dry-review.md`. If no violations, write exactly "No DRY violations." Otherwise use this format:
> ```
> ## DRY Violations
> ### <Short title>
> - **Files:** `<file>:<lines>` and `<file>:<lines>`
> - **Issue:** <One sentence.>
> - **Fix:** <One sentence.>
> ```
> Every finding must name both duplicate sites and include a concrete fix. Never invent violations.

**Agent 3 — Architect Review (model: sonnet)**

Prompt:
> You are an architecture specialist. Review active branch changes for high-level structural concerns. You are not doing line-by-line analysis — you are evaluating whether the design decisions introduced by this branch are sound.
>
> Step 1: Get changed source files via `git diff $(git merge-base HEAD main)...HEAD --name-only`. Fallback to `git diff HEAD~1...HEAD --name-only` if on main or the command fails. Filter to source files only.
>
> Step 2: For each changed source file, read the full file and its diff. Then follow imports one level deep — read files this codebase imports from (not stdlib, not third-party) to understand abstraction boundaries.
>
> Step 3: Look for structural concerns only — wrong abstraction layer, unnecessary coupling, missed abstraction, module boundary violations, readability at scale, design pattern mismatches. Propose sweeping changes if warranted. Do not flag line-level DRY or DOT issues.
>
> Step 4: Write to `temp/architect-review.md`. If no concerns, write exactly "No architectural concerns." Otherwise use this format:
> ```
> ## Architectural Concerns
> ### <Short title>
> - **Scope:** `<file(s)>` — `<what is affected>`
> - **Issue:** <One or two sentences.>
> - **Proposed fix:** <Concrete suggestion.>
> ```
> Every finding must include a concrete proposed fix. Never flag findings just to appear thorough.

Wait for all three background agents to complete before proceeding.

---

## Phase 2: Run the Adversarial Critic

Once all three specialist reports exist, spawn one foreground agent using the Agent tool with model: sonnet.

Prompt:
> You are an adversarial critic reviewing a code design pipeline's findings. Read the three specialist reports and challenge every finding ruthlessly. Your job is to dismiss anything pedantic, speculative, or premature.
>
> Step 1: Read `temp/dot-review.md`, `temp/dry-review.md`, `temp/architect-review.md`. Also read `CLAUDE.md` to understand intentional patterns.
>
> Step 2: For each finding, apply this checklist: Is it concrete? Is the fix simpler than the current code? Is the fix proportionate? Is this a real problem now, not just in theory? Does CLAUDE.md already address this? Would a competent developer disagree it's a problem? Dismiss any finding that fails any of these.
>
> Be especially skeptical of: architect proposals for large refactors, DRY findings where two things that look similar are actually different concepts, DOT findings on small readable functions.
>
> Step 3: Write to `temp/code-design-review.md`. If no findings survive, write ONLY the exact string "Code looks good." with nothing else in the file. If findings survive, use this structure:
> ```
> # Code Design Review
>
> ## DRY Violations
> ### <title>
> - **Files:** ...
> - **Issue:** ...
> - **Fix:** ...
>
> ## DOT Violations
> ### <title>
> - **Location:** ...
> - **Issue:** ...
> - **Fix:** ...
>
> ## Architectural Concerns
> ### <title>
> - **Scope:** ...
> - **Issue:** ...
> - **Proposed fix:** ...
> ```
> Omit sections with no survivors. Do not explain dismissals. Do not add new findings.
> CRITICAL: If the verdict is clean, the file must contain ONLY "Code looks good." — no headers, no other text.

---

## Rules

- The three specialist agents in Phase 1 must run in parallel (background: true).
- The critic in Phase 2 must wait for all three to finish.
- Never skip the critic — it is the quality gate, not a formality.
- The reviewer never touches CLAUDE.md or any other documentation — that is handled separately by `/update-claude-md`.
- The file `temp/code-design-review.md` is what the calling agent reads. Its content must match the spec exactly.
