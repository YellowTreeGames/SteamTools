---
name: code-design-review
description: Orchestrate a multi-specialist code design review (DOT, DRY, Architect, Adversarial Critic), writing a final report to temp/code-design-review.md. Used by eval loops — the calling agent retries until the report contains only "Code looks good."
---

# Code Design Review

Orchestrate a pipeline of four specialist agents reviewing the active branch changes.

The pipeline:
1. **DOT Review** (Haiku) + **DRY Review** (Haiku) + **Architect Review** (Sonnet) — run in parallel
2. **Adversarial Critic** (Sonnet) — reads all three reports and filters pedantic or speculative findings

The final report lands at `temp/code-design-review.md`. The success string the calling agent polls for is **"Code looks good."** (verbatim, nothing else in the file).

---

## Phase 1: Run the Three Specialists in Parallel

Spawn three background agents simultaneously using the Agent tool. Each agent invokes its skill via the Skill tool.

**Agent 1 — DOT Review (model: haiku)**

Prompt:
> Use the Skill tool to invoke the `dot-review` skill.

**Agent 2 — DRY Review (model: haiku)**

Prompt:
> Use the Skill tool to invoke the `dry-review` skill.

**Agent 3 — Architect Review (model: sonnet)**

Prompt:
> Use the Skill tool to invoke the `architect-review` skill.

Wait for all three background agents to complete before proceeding.

---

## Phase 2: Run the Adversarial Critic

Once all three specialist reports exist, spawn one foreground agent using the Agent tool with model: sonnet.

Prompt:
> Use the Skill tool to invoke the `adversarial-critic` skill.

---

## Rules

- The three specialist agents in Phase 1 must run in parallel (background: true).
- The critic in Phase 2 must wait for all three to finish.
- Never skip the critic — it is the quality gate, not a formality.
- The reviewer never touches CLAUDE.md or any other documentation — that is handled separately by `/update-claude-md`.
- The file `temp/code-design-review.md` is what the calling agent reads. Its content must match the spec exactly.