# Code Design Review

## DRY Violations

### Duplicate SQL in `get_pending_eval_games`
- **Files:** `steamtools/db/store.py:405-422` and `steamtools/db/store.py:424-445`
- **Issue:** The two branches of the if/else share an identical SELECT/JOIN/WHERE core, differing only in the IN-list clause, ORDER BY RANDOM, and LIMIT, making this a copy-paste variant of the same query.
- **Fix:** Extract a single parameterized query that accepts optional `appids`, `limit`, and `fill` arguments to build the WHERE and ORDER clauses, eliminating the duplicated branch.

### `min_cluster_size` passed twice by every caller
- **Files:** `steamtools/review_topics/pipeline.py:32` and `steamtools/review_topics/pipeline.py:114`, repeated in `steamtools_cli/cli.py:198-201` and `steamtools_mcp/server.py:63-64`
- **Issue:** Callers must supply `min_cluster_size` twice — once to `from_defaults` (to configure the clusterer) and again to `run_discovery` (to store it in the DB run record) — because the pipeline does not read the value back from its own clusterer.
- **Fix:** Have `run_discovery` read `self._clusterer.min_cluster_size` instead of accepting a redundant parameter, so callers pass it once.

### Gemini JSON call pattern duplicated in `labeler.py`
- **Files:** `steamtools/ai/gemini_client.py:56-62` and `steamtools/review_topics/labeler.py:28-32`
- **Issue:** Both sites call `_get_client().models.generate_content(model=..., contents=..., config=types.GenerateContentConfig(response_mime_type="application/json"))` with identical structure; `labeler.py` also imports the private `_get_client` directly.
- **Fix:** Add a `generate_json(model, prompt)` helper to `gemini_client.py` that encapsulates the JSON-mode call, and have `ClusterLabeler.label_cluster` delegate to it instead of duplicating the call and importing a private symbol.

## DOT Violations

### `_paginate_reviews` fetches, transforms, and writes in one method
- **Location:** `steamtools/db/store.py` — `_paginate_reviews`
- **Issue:** The method paginates the Steam API, transforms raw review dicts into DB rows (inline dict comprehension), and executes the INSERT inside the loop — three distinct responsibilities in one body.
- **Fix:** Extract a `_normalize_reviews_for_db` helper that maps raw review dicts to insert-ready rows, leaving `_paginate_reviews` responsible only for pagination and DB writing.
