import sqlite3
from typing import List, Optional

import logging
from telegram import User

from fs import db_path
from answer import Answer

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
                cur.execute("""INSERT INTO users (first_name, last_name, username, id) VALUES (?, ?, ?, ?)""",
                            (u.first_name, u.last_name, u.username, u.id))
            else:
                cur.execute("""UPDATE users SET first_name = ?, last_name = ?, username = ? WHERE id = ?""",
                            (u.first_name, u.last_name, u.username, u.id))

            conn.commit()

        for answer in self.answers():
            answer.store()

        assert self.id is not None
        assert all(a.id is not None for a in self.answers())

    def total_votes(self) -> int:
        return sum(len(ans.voters()) for ans in self.answers())

    def total_voters(self) -> int:
        # TODO: replace with sql query
        return len(set(voter.id
                       for answer in self.answers()
                       for voter in answer.voters()))

    def __str__(self, *args, **kwargs):
        footer = "\U0001f465 "
        total = self.total_voters()
        if total == 0:
            footer += "Nobody voted so far."
        else:
            footer += "{} people voted so far.".format(total)

        return "{}\n\n{}\n\n{}".format(self.topic,
                                       "\n\n".join(map(str, self.answers())),
                                       footer)

    @classmethod
    def load(cls, poll_id) -> Optional['Poll']:
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
    def query(cls, user_id: int, text: str) -> List['Poll']:
        """
        query `Poll`s from the database, sort by last created, limit 50 (telegram limitation).
        :param user_id: only creator of a poll can post it
        :param text: query string
        :return: list of polls matching query
        """
        polls: List[Poll] = []

        try:
            poll_id = int(text)
        except ValueError as e: pass
        else:
            poll = cls.load(poll_id)
            if poll is not None:
                polls.append(poll)

        polls = list(filter(lambda p: p.owner.id == user_id, polls))

        logger.debug("query polls for user id %d, query '%s', total %d", user_id, text, len(polls))
        for p in polls:
            logger.debug("\tdetails for poll id %d:", p.id)
            logger.debug("\t%s", str(p))

        return polls
