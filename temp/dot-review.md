## DOT Violations

### sync_reviews: Pagination and storage mixed
- **Location:** `steamtools/db/store.py` — `StoDB.sync_reviews()`
- **Issue:** The method does three things: (1) checks staleness and short-circuits if current, (2) paginates through Steam's review API, and (3) upserts results into two separate tables (reviews and summary). Each is a separate responsibility.
- **Fix:** Split into two methods: a stateless `_paginate_reviews()` that yields paginated review pages, and `sync_reviews()` that orchestrates pagination and persists. Alternatively, move staleness checking and the `already_current` short-circuit into the caller (e.g., `get_review_summary()`) so `sync_reviews()` is purely fetch-and-persist.

### get_review_summary: Query and fetch decision logic mixed
- **Location:** `steamtools/db/store.py` — `StoDB.get_review_summary()`
- **Issue:** The method both queries the DB *and* decides whether to trigger a fresh fetch (invoking `sync_reviews()`). It conflates read-path logic with write-trigger logic.
- **Fix:** Rename to clarify intent (e.g., `get_or_fetch_review_summary()`) or split into two: `get_review_summary()` returns only what is in the DB (no side effects), and a caller method handles the refresh decision. This aligns with the pattern used for `get_app_details()` in the same class.
