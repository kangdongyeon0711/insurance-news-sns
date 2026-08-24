"""USE_MOCK=true일 때 각 수집기가 반환하는 샘플 기사 데이터.

실제 네트워크 호출 없이 파이프라인(필터링/요약/조회 웹페이지)을 그대로
시연·테스트할 수 있도록, 추적 대상 보험사명이 포함된 기사를 미리 만들어 둔다.
"""

from datetime import datetime, timedelta, timezone

from news_alert.models.article import Article

_NAVER_SAMPLE_ARTICLES = [
    {
        "title": "삼성생명, 3분기 순이익 전년比 15% 증가",
        "source": "예시경제",
        "content": (
            "삼성생명이 3분기 실적을 발표했다. 순이익은 전년 동기 대비 15% 늘어난 "
            "3,200억원을 기록했다. 회사 측은 보장성 보험 판매 호조를 주요 원인으로 꼽았다."
        ),
        "hours_ago": 1,
    },
    {
        "title": "현대해상, AI 기반 자동차보험 신상품 출시",
        "source": "예시신문",
        "content": (
            "현대해상이 인공지능을 활용해 운전 습관에 따라 보험료를 산정하는 "
            "자동차보험 신상품을 출시했다고 밝혔다."
        ),
        "hours_ago": 3,
    },
    {
        "title": "한화생명·교보생명, 헬스케어 서비스 업무협약",
        "source": "예시데일리",
        "content": (
            "한화생명과 교보생명이 헬스케어 서비스 공동 개발을 위한 업무협약을 "
            "체결했다고 밝혔다. 양사는 디지털 헬스케어 플랫폼을 공동 운영할 계획이다."
        ),
        "hours_ago": 5,
    },
]

_PRESS_SAMPLE_ARTICLES = [
    {
        "title": "DB손해보험, 반려동물보험 가입자 100만명 돌파",
        "source": "예시경제",
        "content": "DB손해보험의 반려동물보험 누적 가입자가 100만명을 넘어섰다고 밝혔다.",
        "hours_ago": 2,
    },
    {
        "title": "메리츠화재, 3분기 영업이익 20% 증가",
        "source": "예시일보",
        "content": "메리츠화재가 3분기 영업이익이 전년 대비 20% 증가했다고 공시했다.",
        "hours_ago": 4,
    },
    {
        "title": "신한라이프, 상속·증여 특화 종신보험 출시",
        "source": "예시데일리",
        "content": "신한라이프가 고액자산가를 겨냥한 상속·증여 특화 종신보험을 선보였다.",
        "hours_ago": 6,
    },
]


def _build(samples: list[dict], namespace: str) -> list[Article]:
    now = datetime.now(timezone.utc)
    return [
        Article(
            source=item["source"],
            title=item["title"],
            url=f"https://mock.local/{namespace}/{i}",
            published_at=now - timedelta(hours=item["hours_ago"]),
            content=item["content"],
        )
        for i, item in enumerate(samples, start=1)
    ]


def naver_sample_articles() -> list[Article]:
    """mock 모드에서 NaverNewsRssCollector가 반환하는 샘플 기사."""
    return _build(_NAVER_SAMPLE_ARTICLES, "naver")


def press_sample_articles() -> list[Article]:
    """mock 모드에서 PressRssCollector가 반환하는 샘플 기사."""
    return _build(_PRESS_SAMPLE_ARTICLES, "press")
