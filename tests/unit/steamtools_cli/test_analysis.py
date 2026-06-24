"""Unit tests for steamtools_cli.analysis — pipeline and DB fully mocked."""

from unittest.mock import patch

from typer.testing import CliRunner

from steamtools_cli.cli import app

runner = CliRunner()

_PIPELINE_RESULT = {"processed": 5, "skipped": 2, "failed": 1}
_ABSA_STATS = {
    "appid": 3283790,
    "reviews_processed": 7,
    "by_category": [
        {"category": "Gameplay", "count": 4},
        {"category": "Audio", "count": 2},
    ],
    "by_sentiment": [
        {"sentiment": "Positive", "count": 5},
        {"sentiment": "Negative", "count": 2},
    ],
}


class TestAbsaRun:
    def test_exits_zero(self):
        with (
            patch("steamtools_cli.analysis.StoDB"),
            patch("steamtools_cli.analysis.AnalysisDB"),
            patch("steamtools_cli.analysis.run_absa_pipeline", return_value=_PIPELINE_RESULT),
        ):
            result = runner.invoke(app, ["analysis", "absa", "run", "--appid", "3283790"])
        assert result.exit_code == 0

    def test_prints_stats_line(self):
        with (
            patch("steamtools_cli.analysis.StoDB"),
            patch("steamtools_cli.analysis.AnalysisDB"),
            patch("steamtools_cli.analysis.run_absa_pipeline", return_value=_PIPELINE_RESULT),
        ):
            result = runner.invoke(app, ["analysis", "absa", "run", "--appid", "3283790"])
        assert "processed=5" in result.output
        assert "skipped=2" in result.output
        assert "failed=1" in result.output

    def test_appid_required(self):
        result = runner.invoke(app, ["analysis", "absa", "run"])
        assert result.exit_code != 0

    def test_force_passed_to_pipeline(self):
        with (
            patch("steamtools_cli.analysis.StoDB"),
            patch("steamtools_cli.analysis.AnalysisDB"),
            patch("steamtools_cli.analysis.run_absa_pipeline", return_value=_PIPELINE_RESULT) as mock_pipeline,
        ):
            runner.invoke(app, ["analysis", "absa", "run", "--appid", "3283790", "--force"])
        assert mock_pipeline.call_args.kwargs["force"] is True

    def test_delay_passed_to_pipeline(self):
        with (
            patch("steamtools_cli.analysis.StoDB"),
            patch("steamtools_cli.analysis.AnalysisDB"),
            patch("steamtools_cli.analysis.run_absa_pipeline", return_value=_PIPELINE_RESULT) as mock_pipeline,
        ):
            runner.invoke(app, ["analysis", "absa", "run", "--appid", "3283790", "--delay", "2.0"])
        assert mock_pipeline.call_args.kwargs["delay"] == 2.0

    def test_batch_size_passed_to_pipeline(self):
        with (
            patch("steamtools_cli.analysis.StoDB"),
            patch("steamtools_cli.analysis.AnalysisDB"),
            patch("steamtools_cli.analysis.run_absa_pipeline", return_value=_PIPELINE_RESULT) as mock_pipeline,
        ):
            runner.invoke(app, ["analysis", "absa", "run", "--appid", "3283790", "--batch-size", "10"])
        assert mock_pipeline.call_args.kwargs["batch_size"] == 10

    def test_model_passed_to_pipeline(self):
        with (
            patch("steamtools_cli.analysis.StoDB"),
            patch("steamtools_cli.analysis.AnalysisDB"),
            patch("steamtools_cli.analysis.run_absa_pipeline", return_value=_PIPELINE_RESULT) as mock_pipeline,
        ):
            runner.invoke(app, ["analysis", "absa", "run", "--appid", "3283790", "--model", "gemini-1.5-pro"])
        assert mock_pipeline.call_args.kwargs["model"] == "gemini-1.5-pro"


class TestAbsaInfo:
    def test_exits_zero(self):
        with patch("steamtools_cli.analysis.AnalysisDB") as MockDB:
            MockDB.return_value.absa_stats.return_value = _ABSA_STATS
            result = runner.invoke(app, ["analysis", "absa", "info", "--appid", "3283790"])
        assert result.exit_code == 0

    def test_prints_reviews_processed(self):
        with patch("steamtools_cli.analysis.AnalysisDB") as MockDB:
            MockDB.return_value.absa_stats.return_value = _ABSA_STATS
            result = runner.invoke(app, ["analysis", "absa", "info", "--appid", "3283790"])
        assert "reviews_processed=7" in result.output

    def test_prints_categories(self):
        with patch("steamtools_cli.analysis.AnalysisDB") as MockDB:
            MockDB.return_value.absa_stats.return_value = _ABSA_STATS
            result = runner.invoke(app, ["analysis", "absa", "info", "--appid", "3283790"])
        assert "Gameplay" in result.output
        assert "Audio" in result.output

    def test_prints_sentiments(self):
        with patch("steamtools_cli.analysis.AnalysisDB") as MockDB:
            MockDB.return_value.absa_stats.return_value = _ABSA_STATS
            result = runner.invoke(app, ["analysis", "absa", "info", "--appid", "3283790"])
        assert "Positive" in result.output
        assert "Negative" in result.output

    def test_appid_required(self):
        result = runner.invoke(app, ["analysis", "absa", "info"])
        assert result.exit_code != 0
