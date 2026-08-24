from news_alert.filters.keyword_filter import KeywordFilter


def test_keyword_filter_placeholder():
    f = KeywordFilter(include_keywords=["삼성화재"], exclude_keywords=["광고"])
    assert f.include_keywords == ["삼성화재"]
