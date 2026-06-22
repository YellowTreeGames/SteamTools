---
name: update-claude-md
description: After a successful code review pass, update CLAUDE.md to reflect new commands and architecture introduced by the branch. Optimized to run on Haiku.
---

# Update CLAUDE.md

Run after a branch passes code review. Read CLAUDE.md and the changed files, then update CLAUDE.md to reflect any new commands or architectural additions the branch introduced.

**Only update when something genuinely new was introduced.** This is not a full re-sync — it is a targeted update for additions the current CLAUDE.md would miss.

---

## Phase 1: Identify What Changed

Get the list of changed source files:

```
git diff $(git merge-base HEAD main)...HEAD --name-only
```

Fallback if on main or the command fails:
```
git diff HEAD~1...HEAD --name-only
```

Filter to source files only. Also get the full diff summary:

```
git diff $(git merge-base HEAD main)...HEAD --stat
```

---

## Phase 2: Read the Relevant Files

1. Read `CLAUDE.md` in full.
2. For each changed source file, read it.
3. For any changed CLI entrypoints, routing files, or config files, read those too.

Look specifically for:
- **New CLI commands or subcommands** — new `@app.command()` decorators, new Typer commands, new entrypoints in `pyproject.toml` or equivalent.
- **New modules or packages** added to the codebase that represent a new architectural layer or concern.
- **Changed entrypoints** — if `pyproject.toml` scripts changed or a new `__main__.py` was added.
- **New environment variables or config keys** required to run the project.
- **Removed commands or modules** that CLAUDE.md still references.

Do **not** update for:
- Bug fixes or refactors that don't change the public surface area
- New functions or classes within existing modules (the architecture description stays the same)
- Test files
- Anything already accurately described in CLAUDE.md

---

## Phase 3: Update CLAUDE.md

Edit CLAUDE.md in-place. Keep all existing content unless it is now wrong. Make the minimum changes necessary:

- **Add new CLI commands** to the "Run the CLI" section, following the existing format exactly.
- **Add new modules** to the "Architecture" section, following the existing bullet style.
- **Update config** if new env vars were added — add them to the relevant config section.
- **Remove stale entries** if a command or module was deleted.

Do not rewrite sections that are still accurate. Do not change tone, style, or formatting beyond what is necessary. Do not add sections that don't already exist.

---

## Rules

- If nothing in CLAUDE.md needs updating, say so and do not touch the file.
- Never remove content unless you confirmed it is now wrong by reading the current code.
- Match the existing formatting exactly — same bullet style, same heading levels, same code block style.
