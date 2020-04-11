"""
manager = StateManager()

manager[message.from_user.id].
"""

import json
import sqlite3

from telegram import User
from telegram.ext import ConversationHandler

from fs import DB_PATH
import log
from poll import Poll


logger = log.getLogger(__name__)


###################
# User-side state #
###################
class UserState:
    def __init__(self, user: User):
        self.user = user
        self.state = {}
        self.poll = Poll(self.user, '')

    def load(self) -> dict:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""SELECT state FROM user_states WHERE id = ?""", (self.user.id,))
            blob = cur.fetchone()

            self.state = {}
            if blob is not None:
                try:
                    self.state = json.loads(blob[0].decode('utf-8'))
                except ValueError:
                    pass

            logger.debug('loaded user %d state: %s', self.user.id, self.state)

            return self.state

    def load_poll(self) -> Poll:
        self.poll = Poll(self.user, self.state.get('topic', ''))
        for answer in self.state.get('answers', []):
            self.poll.add_answer(answer)
        return self.poll

    def store(self):
        blob = json.dumps(self.state).encode('utf-8')
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO user_states (id, state)
                VALUES (?, ?)
                """, (self.user.id, blob))

            logger.debug('wrote user %d state: %s', self.user.id, self.state)

    def reset(self):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""DELETE FROM user_states WHERE id = ?""", (self.user.id,))
        self.poll = Poll(self.user, '')

    def add_question(self, topic: str):
        data = self.load()
        data['topic'] = topic
        self.store()

    def add_answer(self, answer: str) -> Poll:
        data = self.load()
        data.setdefault('answers', []).append(answer)
        poll = self.load_poll()
        self.store()
        return poll

    def create_poll(self) -> Poll:
        self.load()
        poll = self.load_poll()
        self.reset()
        return poll


class StateManager:
    def __init__(self):
        pass

    def __getitem__(self, user: User) -> UserState:
        return UserState(user)


######################
# Conversation state #
######################
class SQLiteDictProxy(dict):
    table = "persistent_conversation_state"

    def __init__(self, db: str):
        super().__init__()
        self.db = db

    def __contains__(self, key):
        return self[key] is not None

    def __getitem__(self, key):
        logger.debug('load state for key %s hash %d', key, hash(key))

        with sqlite3.connect(self.db) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute("""
                SELECT * FROM {table} WHERE id = ?
                """.format(table=self.table),
                        (hash(key),))

            row = cur.fetchone()
            if row is not None:
                return row['state']

    def __setitem__(self, key, value: int):
        logger.debug('store state for key %s hash %d value %s', key, hash(key), value)

        with sqlite3.connect(self.db) as conn:
            cur = conn.cursor()

            cur.execute("""
                INSERT OR REPLACE
                  INTO {table} (id, state)
                VALUES (?, ?)
                """.format(table=self.table),
                        (hash(key), value))

    def __delitem__(self, key):
        logger.debug('clear state for key %s hash %d', key, hash(key))

        with sqlite3.connect(self.db) as conn:
            cur = conn.cursor()

            cur.execute("""
                DELETE FROM {table}
                 WHERE id = ?
                """.format(table=self.table),
                        (hash(key),))

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default

    def pop(self, key, default=None):
        value = self.get(key, default)
        del self[key]
        return value


class PersistentConversationHandler(ConversationHandler):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.conversations = SQLiteDictProxy(DB_PATH)
