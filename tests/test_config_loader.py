from news_alert.utils.config_loader import load_yaml


def test_load_yaml_reads_nested_structure(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text(
        "pipeline:\n  log_level: INFO\nkeywords:\n  - 삼성생명\n  - 한화생명\n",
        encoding="utf-8",
    )

    data = load_yaml(path)

    assert data == {"pipeline": {"log_level": "INFO"}, "keywords": ["삼성생명", "한화생명"]}


def test_load_yaml_empty_file_returns_none(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")

    assert load_yaml(path) is None
