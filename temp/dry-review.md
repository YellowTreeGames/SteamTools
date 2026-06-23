## DRY Violations

### Staleness check pattern duplication
- **Files:** `steamtools/db/staleness.py:16-20` and `steamtools/db/staleness.py:23-27`
- **Issue:** `needs_refresh_details()` and `needs_refresh_review_summary()` are structurally identical except for the constant used (30 vs 7 days). Both check `if not row or not row.get("fetched_at")`, then compare age to a constant.
- **Fix:** Extract a parameterized helper function `_needs_refresh(row, max_days)` that both functions call with different `max_days` values.

### Print format duplication in CLI
- **Files:** `steamtools_cli/cli.py:26-29` and `steamtools_cli/cli.py:92-99`
- **Issue:** Both the `info()` command and `_print_review_summary()` print app stats in nearly identical format with `{key}: {value}` lines and optional "Last fetched" field.
- **Fix:** Extract a generic `_print_stats()` helper that takes a dict and optional keys list, reducing the repetition in printing review vs app stats.
