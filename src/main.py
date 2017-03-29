#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Notes:
    InlineKeyboardButton:
        callback_data:
            comes in exactly one of two forms:
            - "#<poll id>/<answer id>":
                used to vote.
            - ".method_name" or ".method_name param1 param2 ...":
                call registered inline callback method with optional
                space-separated parameters.
"""
import json
import logging
import os
import sys
from io import BytesIO
from os.path import join, dirname
from typing import Dict, List, Tuple, Callable, TypeVar
from uuid import uuid4

from dotenv import load_dotenv
from telegram import (Message, InlineKeyboardMarkup, InlineKeyboardButton,
                      InlineQueryResultArticle, InputTextMessageContent)
from telegram.bot import Bot
from telegram.callbackquery import CallbackQuery
from telegram.error import TelegramError
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, ConversationHandler,
                          InlineQueryHandler)
from telegram.ext.callbackqueryhandler import CallbackQueryHandler
from telegram.inlinequery import InlineQuery
from telegram.update import Update
from telegram.user import User

from answer import Answer
from poll import Poll

T = TypeVar('T')

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


###############################################################################
# utils
###############################################################################

def inline_keyboard_markup_answers(poll: Poll) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(
            "{} - {}".format(answer.text, len(answer.voters())),
            callback_data=".vote {} {}".format(poll.id, answer.id))]
        for answer in poll.answers()]
    return InlineKeyboardMarkup(keyboard)


def inline_keyboard_markup_admin(poll: Poll) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("publish", switch_inline_query=str(poll.id))],
        [InlineKeyboardButton("update", callback_data=".update {}".format(poll.id))],
        [InlineKeyboardButton("vote", callback_data=".admin_vote {}".format(poll.id))],
        [InlineKeyboardButton("statistics", callback_data=".stats {}".format(poll.id))],
    ]

    return InlineKeyboardMarkup(keyboard)


def send_admin_poll(message: Message, poll: Poll):
    markup = inline_keyboard_markup_admin(poll)

    message.reply_text(
        str(poll),
        parse_mode=None,
        disable_web_page_preview=True,
        reply_markup=markup)


def maybe_not_modified(call: Callable[..., T], *args, **kwargs) -> T:
    try:
        return call(*args, **kwargs)

    except TelegramError as e:
        # TODO: add `change_count` field to poll in db
        if e.message != "'Bad Request: message is not modified'":
            raise


###############################################################################
# handlers: global
###############################################################################

def error(bot, update, error):
    import traceback
    logger.warning('Update "%s" caused error "%s"' % (update, error))
    traceback.print_exc(file=sys.stdout)


def about(bot: Bot, update: Update):
    message: Message = update.message
    message.reply_text(
        "This bot will help you create multiple-choice polls. "
        "Use /start to create a multiple-choice poll here, "
        "then publish it to groups or send it to individual friends.")


###############################################################################
# conversation: create new poll
###############################################################################

QUESTION, FIRST_ANSWER, ANSWERS, = range(3)

# TODO: use `user_data` for that
UNFINISHED: Dict[int, Poll] = {}


def start(bot: Bot, update: Update) -> int:
    update.message.reply_text("ok, let's create a new poll.  send me a question first.")
    message: Message = update.message
    UNFINISHED[message.from_user.id] = None

    return QUESTION


def add_question(bot: Bot, update: Update) -> int:
    message: Message = update.message
    UNFINISHED[message.from_user.id] = Poll(message.from_user, message.text)
    message.reply_text("creating a new poll: '{}'\n\n"
                       "please send me the first answer option".format(message.text))

    return FIRST_ANSWER


def add_answer(bot: Bot, update: Update) -> int:
    message: Message = update.message
    UNFINISHED[message.from_user.id].add_answer(update.message.text)
    message.reply_text(
        "nice.  feel free to add more answer options.\n\n"
        "when you've added enough, simply send /done.")

    return ANSWERS


def create_poll(bot: Bot, update: Update) -> int:
    message: Message = update.message
    poll = UNFINISHED.pop(message.from_user.id)
    poll.store()
    logger.debug("user id %d created poll id %d", message.from_user.id, poll.id)
    message.reply_text(
        "poll created.  "
        "now you can publish it to a group or send it to your friend in a private message.")

    send_admin_poll(message, poll)

    return ConversationHandler.END


def cancel(bot: Bot, update: Update) -> int:
    message: Message = update.message

    UNFINISHED.pop(message.from_user.id, None)
    message.reply_text(
        "the command has been cancelled. just send me something if you want to start.")

    return ConversationHandler.END


def cancel_nothing(bot: Bot, update: Update):
    message: Message = update.message

    message.reply_text(
        "nothing to cancel anyway.  just send me something if you want to start.")


###############################################################################
# handlers: inline
###############################################################################

def inline_query(bot: Bot, update: Update):
    inline_query: InlineQuery = update.inline_query
    query: str = inline_query.query

    polls: List[Poll] = Poll.query(inline_query.from_user.id, query)

    results = []
    for poll in polls:
        results.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=poll.topic,
                input_message_content=InputTextMessageContent(
                    message_text=str(poll),
                    parse_mode=None,
                    disable_web_page_preview=True),
                description=" / ".join(answer.text for answer in poll.answers()),
                reply_markup=inline_keyboard_markup_answers(poll)))

    inline_query.answer(
        results,
        is_personal=True,
        cache_time=30,
        switch_pm_text="Create new poll",
        switch_pm_parameter="new_poll")


###############################################################################
# handlers: callback query
###############################################################################

def callback_query_vote(bot: Bot, update: Update, groups: Tuple[str, str]):
    query: CallbackQuery = update.callback_query
    poll_id, answer_id = map(int, groups)
    answer: Answer

    # cases:
    # - 0, error: poll / answer not found due to system fault of fraud attempt
    # - 1, set: user don't have active vote in this answer in this poll
    # - 2, reset: user has active vote in this answer in this poll.
    poll = Poll.load(poll_id)
    if poll is not None:
        answer: Answer = next((a for a in poll.answers() if a.id == answer_id), None)

    if answer is None:
        # case 0, error
        logger.debug("poll not found, button data: '%s'", query.data)
        query.answer(text="sorry, this poll not found.  probably it has been closed.")
        query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([]))

    else:
        poll: Poll = answer.poll()
        user: User = query.from_user
        user_old = next(iter(u for u in answer.voters() if u.id == user.id), None)

        if user_old is None:
            # case 1, set
            logger.debug("user id %d voted for answer id %d in poll id %d",
                         query.from_user.id, answer.id, answer.poll().id)
            answer.voters().append(user)
            answer.store()
            query.answer(text="you voted for '{}'.".format(answer.text))

        else:
            # case 2, reset
            logger.debug("user id %d took his/her reaction back from answer id %d in poll id %d",
                         query.from_user.id, answer.id, answer.poll().id)
            answer.voters().remove(user_old)
            answer.store()
            query.answer(text="you took your reaction back.")

        # in both cases 1 and 2 update the view
        if query.message is not None and poll.owner.id == query.message.chat.id:
            markup = inline_keyboard_markup_admin(poll)

        else:
            markup = inline_keyboard_markup_answers(poll)

        maybe_not_modified(
            query.edit_message_text,
            text=str(poll),
            parse_mode=None,
            disable_web_page_preview=True,
            reply_markup=markup)


def callback_query_admin_vote(bot: Bot, update: Update, groups: Tuple[str]):
    query: CallbackQuery = update.callback_query

    poll_id = int(groups[0])
    poll = Poll.load(poll_id)

    query.edit_message_reply_markup(
        reply_markup=inline_keyboard_markup_answers(poll))


def callback_query_update(bot: Bot, update: Update, groups: Tuple[str]):
    query: CallbackQuery = update.callback_query

    poll_id = int(groups[0])
    poll = Poll.load(poll_id)

    query.answer(text='\u2705 results updated.')

    maybe_not_modified(
        query.edit_message_text,
        text=str(poll),
        parse_mode=None,
        disable_web_page_preview=True,
        reply_markup=inline_keyboard_markup_admin(poll))


def callback_query_stats(bot: Bot, update: Update, groups: Tuple[str]):
    """
    generate json file and send it back to poll's owner.
    """
    query: CallbackQuery = update.callback_query

    poll_id = int(groups[0])
    poll = Poll.load(poll_id)

    if poll.owner.id != query.from_user.id:
        logger.debug("user id %d attempted to access stats on poll id %d owner %d",
                     query.from_user.id, poll.id, poll.owner.id)
        return

    message: Message = query.message

    # select
    data = {
        'answers': [
            {
                'id': answer.id,
                'text': answer.text,
                'voters': {
                    'total': len(answer.voters()),
                    '_': [
                        {
                            k: v
                            for k, v in {
                                'id': voter.id,
                                'first_name': voter.first_name,
                                'last_name': voter.last_name,
                                'username': voter.username,
                            }.items()
                            if v}
                        for voter in answer.voters()]}}
            for answer in poll.answers()]
    }

    content = json.dumps(data, indent=4, ensure_ascii=False)
    raw = BytesIO(content.encode('utf-8'))
    name = "statistics for poll #{}.json".format(poll.id)

    bot.send_document(poll.owner.id, raw, filename=name)
    query.answer()


def main():
    dotenv_path = join(dirname(dirname(__file__)), '.env')
    load_dotenv(dotenv_path)

    # Create the EventHandler and pass it your bot's token.
    updater = Updater(os.environ['TOKEN'])

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(Filters.text, add_question)
        ],
        allow_reentry=True,
        states={
            QUESTION: [
                MessageHandler(Filters.text, add_question)],
            FIRST_ANSWER: [
                MessageHandler(Filters.text, add_answer)],
            ANSWERS: [
                MessageHandler(Filters.text, add_answer),
                CommandHandler("done", create_poll)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
    )

    dp.add_handler(conv_handler)

    dp.add_handler(CommandHandler("help", about))
    dp.add_handler(CommandHandler("cancel", cancel_nothing))

    dp.add_handler(InlineQueryHandler(inline_query))

    dp.add_handler(
        CallbackQueryHandler(
            callback_query_vote,
            pattern=r"#(\d+)/(\d+)",
            pass_groups=True))
    dp.add_handler(
        CallbackQueryHandler(
            callback_query_vote,
            pattern=r"\.vote (\d+) (\d+)",
            pass_groups=True))
    dp.add_handler(
        CallbackQueryHandler(
            callback_query_admin_vote,
            pattern=r"\.admin_vote (\d+)",
            pass_groups=True))
    dp.add_handler(
        CallbackQueryHandler(
            callback_query_update,
            pattern=r"\.update (\d+)",
            pass_groups=True))
    dp.add_handler(
        CallbackQueryHandler(
            callback_query_stats,
            pattern=r"\.stats (\d+)",
            pass_groups=True))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
