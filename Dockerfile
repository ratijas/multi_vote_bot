FROM python:onbuild

VOLUME "/root/.local/share/multi_vote_bot"
CMD [ "python", "src/main.py" ]
