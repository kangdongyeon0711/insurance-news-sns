from news_alert.collectors.rss_collector import RssCollector


def test_rss_collector_placeholder():
    collector = RssCollector(feed_urls=["https://example.com/rss"])
    assert collector.feed_urls == ["https://example.com/rss"]
