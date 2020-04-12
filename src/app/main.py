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
import sys
import urllib.parse
from functools import partial
from io import BytesIO
from typing import Callable, List, Optional, TypeVar
from uuid import uuid4

from dotenv import load_dotenv
from telegram import (
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
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    Dispatcher,
    Filters,
    InlineQueryHandler,
    MessageHandler,
    Updater,
)

from . import log
from .config import Configuration
from .filters import FiltersExt
from .model.answer import Answer
from .model.poll import MAX_ANSWERS, MAX_POLLS_PER_USER, Poll
from .paginate import paginate
from .state import PersistentConversationHandler, StateManager
from .util import ignore_not_modified

T = TypeVar('T')

logger = log.getLogger(__name__)
logger.setLevel(log.INFO)

POLLS_PER_PAGE = 5

###############################################################################
# utils
###############################################################################

HandlerCallback = Callable[[Update, CallbackContext], Optional[int]]


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


###############################################################################
# handlers: global
###############################################################################

def error(update: Update, context: CallbackContext):
    import traceback
    logger.warning('Update "%s" caused error "%s"' % (update, context.error))
    traceback.print_exc(file=sys.stdout)


def about(update: Update, context: CallbackContext):
    message: Message = update.message
    message.reply_text(
        "This bot will help you create multiple-choice polls. "
        "Use /start to create a multiple-choice poll here, "
        "then publish it to groups or send it to individual friends.")


def manage(update: Update, context: CallbackContext):
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


def start_with_poll(update: Update, context: CallbackContext):
    message: Message = update.message

    poll_id = int(context.match.groups()[0])
    poll = Poll.load(poll_id)

    send_vote_poll(message, poll)


def view_poll(update: Update, context: CallbackContext):
    message: Message = update.message

    poll_id = int(context.match.groups()[0])
    poll = Poll.load(poll_id)

    if poll.owner.id == message.from_user.id:
        send_admin_poll(message, poll)


###############################################################################
# conversation: create new poll
###############################################################################

QUESTION, FIRST_ANSWER, ANSWERS, = range(3)

states = StateManager()


def start_from_command(update: Update, context: CallbackContext) -> int:
    message: Message = update.message
    user = message.from_user
    return start_with_user(user, context)


def start_from_callback_query(update: Update, context: CallbackContext) -> int:
    query: CallbackQuery = update.callback_query
    query.answer()
    user = query.from_user
    return start_with_user(user, context)


def start_with_user(user: User, context: CallbackContext) -> int:
    context.bot.send_message(user.id, "ok, let's create a new poll.  send me a question first.")
    states[user].reset()
    return QUESTION


def add_question(update: Update, context: CallbackContext) -> int:
    message: Message = update.message
    states[message.from_user].add_question(message.text)
    message.reply_text("creating a new poll: '{}'\n\n"
                       "please send me the first answer option".format(message.text))

    return FIRST_ANSWER


def entry_point_add_question(conv_handler: ConversationHandler, update: Update, context: CallbackContext):
    """
    Force conversation literally out of nothing, but only in private chats.

    The idea is to treat any text message as a question for a new poll.
    It works by tweaking with internals of the conversation handler, and re-queueing
    the current update, thus forcing the conversation handler to process it again
    from the perspective of a question text.
    """
    message: Message = update.message

    if message.chat.type == 'private':
        key = (message.chat.id, message.from_user.id)

        conv_handler.current_conversation = key
        conv_handler.current_handler = add_question
        conv_handler.conversations[key] = QUESTION

        context.update_queue.put(update, True, 1)


def add_answer(update: Update, context: CallbackContext) -> int:
    message: Message = update.message
    poll: Poll = states[message.from_user].add_answer(update.message.text)

    if len(poll.answers()) == MAX_ANSWERS:
        return create_poll(update, context)

    else:
        message.reply_text(
            "nice.  feel free to add more answer options.\n\n"
            "when you've added enough, simply send /done.")

        return ANSWERS


def create_poll(update: Update, context: CallbackContext) -> int:
    message: Message = update.message
    poll = states[message.from_user].create_poll()
    poll.store()
    logger.debug("user id %d created poll id %d", message.from_user.id, poll.id)
    message.reply_text(
        "poll created.  "
        "now you can publish it to a group or send it to your friend in a private message.")

    send_admin_poll(message, poll)

    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext) -> int:
    message: Message = update.message

    states[message.from_user].reset()
    message.reply_text(
        "the command has been cancelled. just send me something if you want to start.")

    return ConversationHandler.END


def cancel_nothing(update: Update, context: CallbackContext):
    message: Message = update.message

    message.reply_text(
        "nothing to cancel anyway.  just send me something if you want to start.")


###############################################################################
# handlers: inline
###############################################################################

def inline_query(update: Update, context: CallbackContext):
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

def callback_query_vote(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    poll_id, answer_id = map(int, context.match.groups())
    answer: Optional[Answer] = None

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
        with ignore_not_modified():
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

        with ignore_not_modified():
            query.edit_message_text(
                text=str(poll),
                parse_mode=None,
                disable_web_page_preview=True,
                reply_markup=markup)


def callback_query_admin_vote(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    poll_id = int(context.match.groups()[0])
    poll = Poll.load(poll_id)

    logger.debug("owner user id %d want to vote in poll id %d", query.from_user.id, poll.id)

    with ignore_not_modified():
        query.edit_message_reply_markup(reply_markup=inline_keyboard_markup_answers(poll))


def callback_query_update(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query

    poll_id = int(context.match.groups()[0])
    poll = Poll.load(poll_id)

    query.answer(text='\u2705 results updated.')

    with ignore_not_modified():
        query.edit_message_text(
            text=str(poll),
            parse_mode=None,
            disable_web_page_preview=True,
            reply_markup=inline_keyboard_markup_admin(poll))


def callback_query_stats(update: Update, context: CallbackContext):
    """
    generate json file and send it back to poll's owner.
    """
    query: CallbackQuery = update.callback_query

    poll_id = int(context.match.groups()[0])
    poll = Poll.load(poll_id)

    if poll.owner.id != query.from_user.id:
        logger.debug("user id %d attempted to access stats on poll id %d owner %d",
                     query.from_user.id, poll.id, poll.owner.id)
        return

    message: Message = query.message

    # select
    data = {
        'answers': [{
            'id': answer.id,
            'text': answer.text,
            'voters': {
                'total': len(answer.voters()),
                '_': [{
                    k: v
                    for k, v in {
                        'id': voter.id,
                        'first_name': voter.first_name,
                        'last_name': voter.last_name,
                        'username': voter.username,
                    }.items()
                    if v
                } for voter in answer.voters()]
            }
        } for answer in poll.answers()]
    }

    content = json.dumps(data, indent=4, ensure_ascii=False)
    raw = BytesIO(content.encode('utf-8'))
    name = "statistics for poll #{}.json".format(poll.id)

    context.bot.send_document(poll.owner.id, raw, filename=name)
    query.answer()


def callback_query_manage(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query

    offset = int(context.match.groups()[0])

    polls: List[Poll] = Poll.query(query.from_user.id, limit=MAX_POLLS_PER_USER)

    with ignore_not_modified():
        query.edit_message_text(
            text=manage_polls_message(polls, offset, POLLS_PER_PAGE),
            parse_mode=None,
            disable_web_page_preview=True,
            reply_markup=paginate(len(polls), offset, POLLS_PER_PAGE,
                                  manage_polls_callback_data))


def callback_query_share(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query

    poll_id = context.match.groups()[0]

    context.bot.send_message(
        query.from_user.id,
        "https://t.me/{}?start=poll_id={}".format(context.bot.username, poll_id),
        parse_mode=None,
        disable_web_page_preview=True,
    )
    query.answer()


def callback_query_not_found(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query

    logger.debug("invalid callback query data %r from user id %d", query.data, query.from_user.id)

    query.answer("invalid query")


def get_updater(token: str) -> Updater:
    updater = Updater(token, use_context=True)
    return updater


def configure_updater(updater: Updater):
    # Get the dispatcher to register handlers
    dp: Dispatcher = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.regex(r"/start poll_id=(.+)"), start_with_poll))

    conv_handler = PersistentConversationHandler(
        entry_points=[
            CommandHandler("start", start_from_command),
            CallbackQueryHandler(start_from_callback_query, pattern=r"\.start"),
        ],
        allow_reentry=True,
        states={
            QUESTION: [
                MessageHandler(FiltersExt.non_command_text, add_question)],
            FIRST_ANSWER: [
                MessageHandler(FiltersExt.non_command_text, add_answer)],
            ANSWERS: [
                CommandHandler("done", create_poll),
                MessageHandler(FiltersExt.non_command_text, add_answer),
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        per_chat=True,
        per_user=True,
        # No, we don't need per_message, despite what warning says.
        # Conversation is global for chat with user, and CallbackQueryHandler is only used to
        # enter conversation from anywhere using "Start" inline button under an empty polls list.
        per_message=False,
    )

    dp.add_handler(conv_handler)
    dp.add_handler(
        MessageHandler(
            FiltersExt.non_command_text,
            partial(entry_point_add_question, conv_handler)))

    dp.add_handler(CommandHandler("help", about))
    dp.add_handler(CommandHandler("cancel", cancel_nothing))
    dp.add_handler(CommandHandler("polls", manage))
    dp.add_handler(MessageHandler(Filters.regex(r"/view_(.+)"), view_poll))

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
        dp.add_handler(CallbackQueryHandler(callback, pattern=pattern))

    dp.add_handler(CallbackQueryHandler(callback_query_not_found))

    # log all errors
    dp.add_error_handler(error)

    return updater


def start_updater(updater: Updater, config: Configuration) -> None:
    # Start the Bot
    webhook_url = config.webhook_url
    if webhook_url is not None:
        kw = {}

        # https://stackoverflow.com/questions/55202875/python-urllib-parse-urljoin-on-path-starting-with-numbers-and-colon
        webhook_url = urllib.parse.urljoin('{}/'.format(webhook_url), './{}'.format(config.token))
        kw['url_path'] = '/{}'.format(config.token)

        if config.port is not None:
            kw['port'] = config.port

        if config.listen is not None:
            kw['listen'] = config.listen

        logger.info("WEBHOOK_URL found, starting webhook on %s:%s url %s", config.listen, config.port, webhook_url)

        updater.bot.set_webhook(url=webhook_url)
        updater.start_webhook(**kw)

    else:
        logger.info("WEBHOOK_URL not found, starting long polling.")
        updater.start_polling()


def main():
    load_dotenv()
    config = Configuration.get()

    updater = get_updater(config.token)
    configure_updater(updater)
    start_updater(updater, config)
    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
