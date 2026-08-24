from datetime import timezone

from news_alert.utils.feed import parse_published_at, strip_html


def test_strip_html_removes_tags_and_trims():
    assert strip_html("<b>삼성화재</b>  신제품 출시  ") == "삼성화재  신제품 출시"


def test_strip_html_handles_empty():
    assert strip_html("") == ""
    assert strip_html(None) == ""


def test_parse_published_at_uses_published_parsed():
    entry = {"published_parsed": (2026, 8, 24, 3, 0, 0, 0, 0, 0)}
    dt = parse_published_at(entry)
    assert dt.tzinfo == timezone.utc
    assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 8, 24, 3)


def test_parse_published_at_falls_back_to_now():
    dt = parse_published_at({})
    assert dt.tzinfo == timezone.utc
