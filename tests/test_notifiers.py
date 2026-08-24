from news_alert.notifiers.slack_notifier import SlackNotifier


def test_slack_notifier_placeholder():
    n = SlackNotifier(webhook_url="https://hooks.slack.com/services/xxx")
    assert n.webhook_url.startswith("https://")
