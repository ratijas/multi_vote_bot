import logging
import sqlite3
from typing import List, Optional

from telegram import User

from answer import Answer
from fs import db_path

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Poll(object):
    def __init__(self, owner: User, topic: str):
        self.id: int = None
        self.owner: User = owner
        self.topic: str = topic
        self._answers: List[Answer] = []

    def answers(self) -> List[Answer]:
        """
        list of possible answers for the poll in order they were added.
        """
        return self._answers

    def add_answer(self, answer: str):
        a = Answer(self, answer)
        self._answers.append(a)

    def store(self):
        assert len(self.answers()) > 0

        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()

            if self.id is None:
                cur.execute("""INSERT INTO polls (owner_id, topic) VALUES (?, ?)""",
                            (self.owner.id, self.topic))
                self.id = cur.lastrowid

            else:
                cur.execute("""UPDATE polls SET owner_id = ?, topic = ? WHERE id = ?""",
                            (self.owner.id, self.topic, self.id))

            u = self.owner
            cur.execute("""SELECT * from users WHERE id = ?""", (u.id,))

            if cur.fetchone() is None:
                cur.execute("""
                    INSERT INTO users (first_name, last_name, username, id)
                    VALUES (?, ?, ?, ?)
                    """, (u.first_name, u.last_name, u.username, u.id))

            else:
                cur.execute("""
                    UPDATE users
                    SET first_name = ?, last_name = ?, username = ?
                    WHERE id = ?
                    """, (u.first_name, u.last_name, u.username, u.id))

            conn.commit()

        for answer in self.answers():
            answer.store()

        assert self.id is not None
        assert all(a.id is not None for a in self.answers())

    def total_voters(self) -> int:
        # TODO: replace with sql query
        return len(set(voter.id
                       for answer in self.answers()
                       for voter in answer.voters()))

    def __str__(self):
        footer = "\U0001f465 "
        total = self.total_voters()

        if total == 0:
            footer += "Nobody voted so far."

        else:
            footer += "{} people voted so far.".format(total)

        return "{}\n\n{}\n\n{}".format(self.topic,
                                       "\n\n".join(map(str, self.answers())),
                                       footer)

    def __eq__(self, other):
        return self.id == other.id

    @classmethod
    def load(cls, poll_id: int) -> Optional['Poll']:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute("""SELECT * FROM polls WHERE id = ?""", (poll_id,))
            row: sqlite3.Row = cur.fetchone()

        if row is not None:
            poll = cls(User(row['owner_id'], ''), row['topic'])
            poll.id = row['id']

            # next, load answers
            poll._answers = Answer.query(poll)

            return poll

    @classmethod
    def query(cls, user_id: int, text: str, limit: int = 5) -> List['Poll']:
        """
        query `Poll`s from the database, sort by last created, limit 50 (telegram limitation).

        :param user_id: only creator of a poll can post it
        :param text: query string
        :param limit: maximum results
        :return: list of polls matching query
        """
        polls: List[Poll] = []

        # cases:
        # - 0, id: add to results poll with id if valid
        # - 1, topic: extend results with list of 5 last created polls which topic matches query

        # case 0, id
        try:
            poll_id = int(text)
        except ValueError as e:
            pass
        else:
            poll = cls.load(poll_id)
            if poll is not None:
                if poll.owner.id == user_id:
                    polls.append(poll)

        # case 2, topic
        # kind of `unique` function.  has to be rewritten.
        polls.extend(p for p in
                     cls._query_topic(user_id, text, limit)
                     if p not in polls)

        logger.debug("query polls for user id %d, query '%s', found %d in total",
                     user_id, text, len(polls))

        return polls

    @classmethod
    def _query_topic(cls, user_id: int, text: str, limit: int) -> List['Poll']:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute("""
                SELECT id FROM polls
                WHERE owner_id = ? AND topic LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """, (user_id, '%{}%'.format(text), limit))
            ids = cur.fetchall()

        return list(filter(
            lambda x: x is not None,
            (Poll.load(poll_id) for (poll_id,) in ids)))
