from typing import Callable

from telegram import InlineKeyboardMarkup, InlineKeyboardButton


def paginate(total: int, offset: int, items_per_page: int,
             callback_data_generator: Callable[[int], str]) -> InlineKeyboardMarkup:
    """
    make `InlineKeyboardMarkup` with "back" / "forward" buttons if appropriate.

    :param total: total number of items in a list.
    :param offset: current offset, starting at 0.
    :param items_per_page: maximum number of items displayed in a single message.
    :param callback_data_generator: function that generates `callback_data` for
        inline buttons that should switch to page with certain offset.
        :argument offset: page opened by button should start with item number `offset`.
    """
    assert offset <= total
    assert items_per_page >= 1

    row = []

    if offset > 0:
        row.append(
            InlineKeyboardButton(
                "\u25c0\ufe0f previous",
                callback_data=callback_data_generator(max(0, offset - items_per_page))))

    if offset + items_per_page < total:
        row.append(
            InlineKeyboardButton(
                "next \u25b6\ufe0f",
                callback_data=callback_data_generator(offset + items_per_page)))

    return InlineKeyboardMarkup([row])
