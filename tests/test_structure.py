"""Enforce 1:1 mirror between source packages and tests/."""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TESTS_ROOT = Path(__file__).resolve().parent
_SOURCE_PACKAGES = ["steamtools", "steamtools_cli", "steamtools_mcp"]


def test_mirror_structure():
    """Every non-__init__ .py source file has a matching tests/<pkg>/test_<file>.py."""
    missing = []
    for pkg in _SOURCE_PACKAGES:
        for src in sorted((_PROJECT_ROOT / pkg).rglob("*.py")):
            if src.name == "__init__.py":
                continue
            rel = src.relative_to(_PROJECT_ROOT)
            expected = _TESTS_ROOT / rel.parent / f"test_{src.name}"
            if not expected.exists():
                missing.append(str(expected.relative_to(_TESTS_ROOT)))
    assert not missing, "Missing test files:\n" + "\n".join(missing)
