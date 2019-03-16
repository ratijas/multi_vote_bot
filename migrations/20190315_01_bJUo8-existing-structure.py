"""
existing structure
"""

from yoyo import step

__depends__ = {}

steps = [
    step("""
        CREATE TABLE IF NOT EXISTS polls (
            id       INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            owner_id INTEGER                           NOT NULL,
            topic    TEXT                              NOT NULL
        );
    """),
    step("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY NOT NULL,
            first_name TEXT,
            last_name  TEXT,
            username   TEXT
        );
    """),
    step("""
        CREATE TABLE IF NOT EXISTS answers (
            id      INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            poll_id INTEGER                           NOT NULL,
            txt     TEXT                              NOT NULL
        );
    """),
    step("""
        CREATE TABLE IF NOT EXISTS votes (
            user_id   INTEGER NOT NULL,
            poll_id   INTEGER NOT NULL,
            answer_id INTEGER NOT NULL
        );
    """),
]
