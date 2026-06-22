import steamtools.config as cfg


def test_config_has_required_attributes():
    assert hasattr(cfg, "STEAM_API_KEY")
    assert hasattr(cfg, "GEMINI_API_KEY")
    assert hasattr(cfg, "GEMINI_MODEL")
    assert hasattr(cfg, "MAX_SCORES")
    assert isinstance(cfg.MAX_SCORES, int)
    assert isinstance(cfg.GEMINI_MODEL, str)
