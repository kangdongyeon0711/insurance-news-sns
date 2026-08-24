import os

_TRUE_VALUES = {"1", "true", "yes", "on"}


def is_mock_mode() -> bool:
    """USE_MOCK 환경변수가 참에 해당하는 값이면 True.

    mock 모드에서는 실제 API/네트워크를 호출하지 않고 미리 만들어둔 샘플
    데이터를 반환한다. collectors/summarizers의 각 구현체가 이 함수로
    모드를 판단한다.
    """
    return os.environ.get("USE_MOCK", "").strip().lower() in _TRUE_VALUES
