from contextlib import contextmanager

from telegram.error import BadRequest


@contextmanager
def ignore_not_modified():
    """Context manager for catching Telegram API "bad requests" which are just "Message is not modified" errors."""
    try:
        yield
    except BadRequest as e:
        if e.message.startswith("Message is not modified"):
            pass
