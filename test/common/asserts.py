import logging
from contextlib import contextmanager


def assert_eq(actual, expected, **context):
    if actual != expected:
        msg = [f"Expected: {expected}", f"Actual:   {actual}"]

        for key, value in context.items():
            if isinstance(value, bytes):
                value = value.hex()
            msg.append(f"{key}: {value}")

        raise AssertionError("\n".join(msg))


@contextmanager
def logged_warnings(logger_name: str):
    """The WARNING+ messages *logger_name* logs inside the block (the test runner mutes pc_tool otherwise)."""
    messages: list[str] = []
    handler = logging.Handler(logging.WARNING)
    handler.emit = lambda record: messages.append(record.getMessage())
    logger = logging.getLogger(logger_name)
    saved = logger.level, logger.propagate
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        yield messages
    finally:
        logger.removeHandler(handler)
        logger.level, logger.propagate = saved
