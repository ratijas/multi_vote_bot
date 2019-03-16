"""
persistent conversation handler
"""

from yoyo import step

__depends__ = {'20190316_02_lKEUa-user-state'}

steps = [
    step("""
        CREATE TABLE persistent_conversation_state (
            id      INTEGER PRIMARY KEY NOT NULL,
            state   INTEGER             NOT NULL
        );
    """),
]
