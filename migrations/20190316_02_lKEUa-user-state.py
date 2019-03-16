"""
user state
"""

from yoyo import step

__depends__ = {'20190316_01_SLB6Y-index'}

steps = [
    step("""
        CREATE TABLE user_states (
            id      INTEGER PRIMARY KEY NOT NULL,
            state   BLOB
        );
    """),
]
