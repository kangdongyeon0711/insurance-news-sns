from pathlib import Path

from news_alert.pipeline import Pipeline
from news_alert.utils.config_loader import load_yaml
from news_alert.utils.logger import get_logger

logger = get_logger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def build_pipeline() -> Pipeline:
    """config/settings.yaml을 읽어 등록된 컴포넌트로 Pipeline을 구성한다."""
    settings = load_yaml(CONFIG_DIR / "settings.yaml")
    raise NotImplementedError("wire collectors/filters/summarizer/notifiers from settings")


def main() -> None:
    pipeline = build_pipeline()
    pipeline.run()


if __name__ == "__main__":
    main()
