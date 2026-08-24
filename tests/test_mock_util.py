import pytest

from news_alert.utils.mock import is_mock_mode


@pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "on", "  true  "])
def test_is_mock_mode_true_for_truthy_values(monkeypatch, value):
    monkeypatch.setenv("USE_MOCK", value)
    assert is_mock_mode() is True


@pytest.mark.parametrize("value", ["false", "False", "0", "no", "off", ""])
def test_is_mock_mode_false_for_falsy_values(monkeypatch, value):
    monkeypatch.setenv("USE_MOCK", value)
    assert is_mock_mode() is False


def test_is_mock_mode_false_when_unset(monkeypatch):
    monkeypatch.delenv("USE_MOCK", raising=False)
    assert is_mock_mode() is False
