import logging

from news_alert.utils.logger import get_logger


def test_get_logger_sets_name_and_info_level():
    logger = get_logger("news_alert.test.module")

    assert logger.name == "news_alert.test.module"
    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1


def test_get_logger_does_not_duplicate_handlers_on_repeat_calls():
    first = get_logger("news_alert.test.repeat")
    second = get_logger("news_alert.test.repeat")

    assert first is second
    assert len(second.handlers) == 1
