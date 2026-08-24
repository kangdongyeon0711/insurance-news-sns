from dotenv import dotenv_values

from news_alert.utils.env import load_env


def test_load_env_sets_values_from_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("USE_MOCK=true\nANTHROPIC_API_KEY=sk-ant-from-file\n", encoding="utf-8")

    monkeypatch.delenv("USE_MOCK", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("news_alert.utils.env.ENV_PATH", env_file)

    load_env()

    import os

    assert os.environ["USE_MOCK"] == "true"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-from-file"


def test_load_env_does_not_override_existing_env_vars(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=from-file\n", encoding="utf-8")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-shell")
    monkeypatch.setattr("news_alert.utils.env.ENV_PATH", env_file)

    load_env()

    import os

    assert os.environ["ANTHROPIC_API_KEY"] == "from-shell"


def test_load_env_is_a_noop_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("news_alert.utils.env.ENV_PATH", tmp_path / "does_not_exist.env")

    load_env()  # 예외 없이 조용히 넘어가야 한다


def test_env_example_lists_the_same_keys_as_a_real_env_file_would():
    # .env.example이 dotenv 형식으로 파싱 가능한지(주석/빈 줄 포함) 확인한다.
    from pathlib import Path

    example_path = Path(__file__).resolve().parents[1] / ".env.example"
    values = dotenv_values(example_path)
    assert "USE_MOCK" in values
    assert "ANTHROPIC_API_KEY" in values
