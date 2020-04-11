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
from os.path import expanduser, join

from yoyo import get_backend, read_migrations

from . import log

logger = log.getLogger('app.fs')

DATA_DIR: str = expanduser("~/.local/share/multi_vote_bot")
if not os.path.exists(DATA_DIR):
    logger.info("Creating data dir at path %s", DATA_DIR)
    os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH: str = join(DATA_DIR, "data.db")


def migrate():
    """ apply yoyo migrations """
    logger.info("Migrating to the latest schema")
    log.getLogger('yoyo').setLevel(log.DEBUG)

    backend = get_backend('sqlite:///' + DB_PATH)
    migrations = read_migrations('./migrations')
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))


# auto migrate when imported
migrate()
