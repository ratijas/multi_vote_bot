"""
index
"""

from yoyo import step

__depends__ = {'20190315_01_bJUo8-existing-structure'}

steps = [
    step("""
        CREATE INDEX index_polls_owner_id ON polls (owner_id);
    """),
    step("""
        CREATE INDEX index_answers_poll_id ON answers (poll_id);
    """),
    # order of columns in index is important
    step("""
        CREATE INDEX index_votes ON votes (poll_id, answer_id, user_id);
    """),
]
