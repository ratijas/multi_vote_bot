"""
file system and database initialization.

tables:
- polls:
  - id PRIMARY KEY
  - owner_id => users.id
  - topic

- users:
  - id PRIMARY KEY
  - first_name
  - last_name
  - username

- answers:
  - id PRIMARY KEY
  - poll_id => polls.id
  - text

- votes:
  - user_id => users.id
  - poll_id => polls.id
  - answer_id => answers.id
"""

import os
import sqlite3
from os.path import join, expanduser

data_dir: str = expanduser("~/.local/share/multi_vote_bot")
if not os.path.exists(data_dir):
    os.makedirs(data_dir, exist_ok=True)

db_path: str = join(data_dir, "data.db")

with sqlite3.connect(db_path) as conn:
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS polls (
            id       INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            owner_id INTEGER                           NOT NULL,
            topic    TEXT                              NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY NOT NULL,
            first_name TEXT,
            last_name  TEXT,
            username   TEXT
        );
        CREATE TABLE IF NOT EXISTS answers (
            id      INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            poll_id INTEGER                           NOT NULL,
            txt     TEXT                              NOT NULL
        );
        CREATE TABLE IF NOT EXISTS votes (
            user_id   INTEGER NOT NULL,
            poll_id   INTEGER NOT NULL,
            answer_id INTEGER NOT NULL
        );
    """)
    conn.commit()
