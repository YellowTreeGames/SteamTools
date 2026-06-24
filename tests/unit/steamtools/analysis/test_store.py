"""Unit tests for steamtools.analysis.store — isolated SQLite DB per test."""

import pytest


@pytest.fixture()
def tmp_analysis_db(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis_test.db"
    monkeypatch.setattr("steamtools.analysis.connection.ANALYSIS_DB_PATH", db_path)
    return db_path


@pytest.fixture()
def adb(tmp_analysis_db):
    from steamtools.analysis.store import AnalysisDB

    return AnalysisDB()


_ASPECTS = [
    {"category": "Gameplay", "specific_feature": "combat", "sentiment": "Positive", "rationale": "Fun fights."},
    {"category": "Audio", "specific_feature": "boss music", "sentiment": "Positive", "rationale": "Great OST."},
]


class TestGetProcessedReviewIds:
    def test_empty_on_fresh_db(self, adb):
        assert adb.get_processed_review_ids(1) == set()

    def test_returns_ids_after_save(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        assert 111 in adb.get_processed_review_ids(1)

    def test_scoped_to_appid(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        assert adb.get_processed_review_ids(2) == set()


class TestSaveAbsaResult:
    def test_saves_processed_row(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        assert 111 in adb.get_processed_review_ids(1)

    def test_saves_aspect_rows(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        aspects = adb.get_absa_aspects(1)
        assert len(aspects) == 2

    def test_replaces_on_duplicate_review(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        adb.save_absa_result(111, 1, _ASPECTS[:1], "gemini-2.0-flash")
        assert len(adb.get_absa_aspects(1)) == 3  # old 2 + new 1 (INSERT OR REPLACE only replaces processed row)

    def test_empty_aspects_saves_processed_row(self, adb):
        adb.save_absa_result(999, 1, [], "gemini-2.0-flash")
        assert 999 in adb.get_processed_review_ids(1)


class TestDeleteAbsaResult:
    def test_removes_processed_row(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        adb.delete_absa_result(111, 1)
        assert 111 not in adb.get_processed_review_ids(1)

    def test_removes_aspect_rows(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        adb.delete_absa_result(111, 1)
        assert adb.get_absa_aspects(1) == []

    def test_delete_nonexistent_is_noop(self, adb):
        adb.delete_absa_result(999, 1)  # should not raise

    def test_scoped_to_review_and_appid(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        adb.save_absa_result(222, 1, _ASPECTS, "gemini-2.0-flash")
        adb.delete_absa_result(111, 1)
        assert 222 in adb.get_processed_review_ids(1)


class TestGetAbsaAspects:
    def test_returns_all_for_appid(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        assert len(adb.get_absa_aspects(1)) == 2

    def test_filters_by_category(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        results = adb.get_absa_aspects(1, category="Gameplay")
        assert all(r["category"] == "Gameplay" for r in results)
        assert len(results) == 1

    def test_filters_by_sentiment(self, adb):
        mixed = [
            *_ASPECTS,
            {"category": "Performance", "specific_feature": "fps", "sentiment": "Negative", "rationale": "Drops a lot."},
        ]
        adb.save_absa_result(111, 1, mixed, "gemini-2.0-flash")
        results = adb.get_absa_aspects(1, sentiment="Negative")
        assert all(r["sentiment"] == "Negative" for r in results)

    def test_filters_by_category_and_sentiment(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        results = adb.get_absa_aspects(1, category="Gameplay", sentiment="Positive")
        assert len(results) == 1

    def test_empty_for_unknown_appid(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        assert adb.get_absa_aspects(999) == []


class TestAbsaStats:
    def test_zero_counts_on_empty_db(self, adb):
        stats = adb.absa_stats(1)
        assert stats["reviews_processed"] == 0
        assert stats["by_category"] == []
        assert stats["by_sentiment"] == []

    def test_counts_by_category(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        stats = adb.absa_stats(1)
        categories = {r["category"] for r in stats["by_category"]}
        assert "Gameplay" in categories
        assert "Audio" in categories

    def test_counts_by_sentiment(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        stats = adb.absa_stats(1)
        sentiments = {r["sentiment"] for r in stats["by_sentiment"]}
        assert "Positive" in sentiments

    def test_reviews_processed_count(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        adb.save_absa_result(222, 1, _ASPECTS, "gemini-2.0-flash")
        assert adb.absa_stats(1)["reviews_processed"] == 2

    def test_scoped_to_appid(self, adb):
        adb.save_absa_result(111, 1, _ASPECTS, "gemini-2.0-flash")
        adb.save_absa_result(222, 2, _ASPECTS, "gemini-2.0-flash")
        assert adb.absa_stats(1)["reviews_processed"] == 1
