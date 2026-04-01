"""Tests for config loading."""

from fantrax_weekly.config import Settings


def test_defaults():
    """Settings should have empty defaults so the app doesn't crash without .env."""
    s = Settings()
    assert s.fantrax_user_secret_id == ""
    assert s.fantrax_league_id == ""
    assert s.anthropic_api_key == ""


def test_override_via_env(monkeypatch):
    monkeypatch.setenv("FANTRAX_USER_SECRET_ID", "abc123")
    monkeypatch.setenv("FANTRAX_LEAGUE_ID", "league456")
    s = Settings()
    assert s.fantrax_user_secret_id == "abc123"
    assert s.fantrax_league_id == "league456"
