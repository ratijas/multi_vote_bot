"""
manager = StateManager()

manager[message.from_user.id].
"""

import json
import sqlite3
from typing import Dict

from telegram import User

from fs import DB_PATH
import log
from poll import Poll


logger = log.getLogger(__name__)


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

    # def store_poll()
    # not implemented

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
        data['answers'] = data.get('answers', []) + [answer]
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
