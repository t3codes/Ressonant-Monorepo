import pytest
from app.config.settings import ConfigurationError, get_settings


def test_missing_or_short_secret_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_SECRET", "curto")
    with pytest.raises(ConfigurationError):
        get_settings()

    get_settings.cache_clear()
    monkeypatch.delenv("AUTH_SECRET")
    with pytest.raises(ConfigurationError):
        get_settings()
    get_settings.cache_clear()
