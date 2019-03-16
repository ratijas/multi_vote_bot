#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Notes:
    InlineKeyboardButton:
        callback_data:
            has a common format of ".method_name param1 param2 ...".
            currently used methods are:
            - .vote <poll_id> <answer_id>
                vote for an answer <answer_id> in poll <poll_id>.
            - .update <poll_id>
                update poll view in private chat with poll's owner.
            - .admin_vote <poll_id>
                poll's owner want to vote him/herself, show keyboard with answers.
            - .stats <poll_id>
                upload statistics in json to poll's owner.
"""
import json
import os
import sys
from io import BytesIO
from os.path import join, dirname
from queue import Queue
from typing import Dict, List, Tuple, Callable, TypeVar
from uuid import uuid4

from dotenv import load_dotenv
from telegram import (
    Bot,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    Update,
    User,
)
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    Filters,
    InlineQueryHandler,
    MessageHandler,
    RegexHandler,
    Updater,
)

from answer import Answer
import log
from paginate import paginate
from poll import Poll, MAX_ANSWERS, MAX_POLLS_PER_USER

T = TypeVar('T')

logger = log.getLogger(__name__)
logger.setLevel(log.INFO)

POLLS_PER_PAGE = 5


###############################################################################
# utils
###############################################################################

def inline_keyboard_markup_answers(poll: Poll) -> InlineKeyboardMarkup:
    def text(title: str, count: int):
        if count == 0:
            return title
        else:
            return "{} - {}".format(title, count)

    keyboard = [
        [InlineKeyboardButton(
            text(answer.text, len(answer.voters())),
            callback_data=".vote {} {}".format(poll.id, answer.id))]
        for answer in poll.answers()]
    return InlineKeyboardMarkup(keyboard)


def inline_keyboard_markup_admin(poll: Poll) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("publish", switch_inline_query=str(poll.id))],
        [InlineKeyboardButton("share link", callback_data=".share {}".format(poll.id))],
        [
            InlineKeyboardButton("update", callback_data=".update {}".format(poll.id)),
            InlineKeyboardButton("vote", callback_data=".admin_vote {}".format(poll.id))],
        [InlineKeyboardButton("statistics", callback_data=".stats {}".format(poll.id))],
    ]

    return InlineKeyboardMarkup(keyboard)


def send_vote_poll(message: Message, poll: Poll):
    markup = inline_keyboard_markup_answers(poll)

    message.reply_text(
        str(poll),
        parse_mode=None,
        disable_web_page_preview=True,
        reply_markup=markup
    )


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
        if e.message != "Message is not modified":
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


def manage(bot: Bot, update: Update):
    message: Message = update.message
    user_id = message.from_user.id

    polls = Poll.query(user_id, limit=MAX_POLLS_PER_USER)

    if len(polls) == 0:
        message.reply_text(
            text="you don't have any polls yet.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("create new poll", callback_data=".start")]]))

    else:
        message.reply_text(
            manage_polls_message(polls, 0, POLLS_PER_PAGE),
            parse_mode=None,
            disable_web_page_preview=True,
            reply_markup=paginate(len(polls), 0, POLLS_PER_PAGE,
                                  manage_polls_callback_data))


def manage_polls_callback_data(offset):
    return '.manage {}'.format(offset)


def manage_polls_message(polls: List[Poll], offset: int, count: int) -> str:
    text = "your polls\n\n{}".format(
        "\n\n".join(
            "{}. {}\n/view_{}".format(i + 1, poll.topic, poll.id)
            for i, poll in
            enumerate(polls[offset: offset + count], start=offset))
    )
    return text


def start_with_poll(bot: Bot, update: Update, groups: Tuple[str]):
    message: Message = update.message

    poll_id = int(groups[0])
    poll = Poll.load(poll_id)

    send_vote_poll(message, poll)


def view_poll(bot: Bot, update: Update, groups: Tuple[str]):
    message: Message = update.message

    poll_id = int(groups[0])
    poll = Poll.load(poll_id)

    if poll.owner.id == message.from_user.id:
        send_admin_poll(message, poll)


###############################################################################
# conversation: create new poll
###############################################################################

QUESTION, FIRST_ANSWER, ANSWERS, = range(3)

# TODO: use `user_data` for that
UNFINISHED: Dict[int, Poll] = {}


def start(bot: Bot, update: Update) -> int:
    query: CallbackQuery = update.callback_query
    message: Message = update.message

    if query is not None:
        user_id = query.from_user.id
        query.answer()
    elif message is not None:
        user_id = message.from_user.id
    else:
        raise TypeError("unexpected type of update")

    bot.send_message(user_id, "ok, let's create a new poll.  send me a question first.")
    UNFINISHED[user_id] = None

    return QUESTION


def add_question(bot: Bot, update: Update) -> int:
    message: Message = update.message
    UNFINISHED[message.from_user.id] = Poll(message.from_user, message.text)
    message.reply_text("creating a new poll: '{}'\n\n"
                       "please send me the first answer option".format(message.text))

    return FIRST_ANSWER


def entry_point_add_question(conv_handler: ConversationHandler,
                             bot: Bot, update: Update, update_queue: Queue):
    message: Message = update.message

    if message.chat.type == 'private':
        key = (message.chat.id, message.from_user.id)

        conv_handler.current_conversation = key
        conv_handler.current_handler = add_question
        conv_handler.conversations[key] = QUESTION

        update_queue.put(update, True, 1)


def add_answer(bot: Bot, update: Update) -> int:
    message: Message = update.message
    poll: Poll = UNFINISHED[message.from_user.id]
    poll.add_answer(update.message.text)

    if len(poll.answers()) == MAX_ANSWERS:
        return create_poll(bot, update)

    else:
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
        logger.debug("poll not found, query data %r from user id %d", query.data, query.from_user.id)

        query.answer(text="sorry, this poll not found.  probably it has been closed.")
        maybe_not_modified(
            query.edit_message_reply_markup,
            reply_markup=InlineKeyboardMarkup([]))

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

    logger.debug("owner user id %d want to vote in poll id %d", query.from_user.id, poll.id)

    maybe_not_modified(
        query.edit_message_reply_markup,
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


def callback_query_manage(bot: Bot, update: Update, groups: Tuple[str]):
    query: CallbackQuery = update.callback_query

    offset = int(groups[0])

    polls: List[Poll] = Poll.query(query.from_user.id, limit=MAX_POLLS_PER_USER)

    maybe_not_modified(
        query.edit_message_text,
        text=manage_polls_message(polls, offset, POLLS_PER_PAGE),
        parse_mode=None,
        disable_web_page_preview=True,
        reply_markup=paginate(len(polls), offset, POLLS_PER_PAGE,
                              manage_polls_callback_data))


def callback_query_share(bot: Bot, update: Update, groups: Tuple[str]):
    query: CallbackQuery = update.callback_query

    poll_id = groups[0]

    bot.send_message(
        query.from_user.id,
        "https://t.me/{}?start=poll_id={}".format(bot.username, poll_id),
        parse_mode=None,
        disable_web_page_preview=True,
    )
    query.answer()


def callback_query_not_found(bot: Bot, update: Update):
    query: CallbackQuery = update.callback_query

    logger.debug("invalid callback query data %r from user id %d", query.data, query.from_user.id)

    query.answer("invalid query")
    # maybe_not_modified(
    #     query.edit_message_reply_markup,
    #     reply_markup=InlineKeyboardMarkup([]))


def main():
    dotenv_path = join(dirname(dirname(__file__)), '.env')
    load_dotenv(dotenv_path)

    # Create the EventHandler and pass it your bot's token.
    updater = Updater(os.environ['TOKEN'])

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(RegexHandler("/start poll_id=(.+)", start_with_poll, pass_groups=True))

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(start, pattern=r"\.start"),
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
    dp.add_handler(
        MessageHandler(
            Filters.text,
            lambda *args, **kwargs: entry_point_add_question(conv_handler, *args, **kwargs),
            pass_update_queue=True))

    dp.add_handler(CommandHandler("help", about))
    dp.add_handler(CommandHandler("cancel", cancel_nothing))
    dp.add_handler(CommandHandler("polls", manage))
    dp.add_handler(RegexHandler("/view_(.+)", view_poll, pass_groups=True))

    dp.add_handler(InlineQueryHandler(inline_query))

    for callback, pattern in [
        (callback_query_vote, r"#?(\d+)/(\d+)"),
        (callback_query_vote, r"\.vote (\d+) (\d+)"),
        (callback_query_admin_vote, r"\.admin_vote (\d+)"),
        (callback_query_update, r"\.update (\d+)"),
        (callback_query_stats, r"\.stats (\d+)"),
        (callback_query_manage, r"\.manage (\d+)"),
        (callback_query_share, r"\.share (\d+)"),
    ]:
        dp.add_handler(
            CallbackQueryHandler(callback, pattern=pattern, pass_groups=True))

    dp.add_handler(CallbackQueryHandler(callback_query_not_found))

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
