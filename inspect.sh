#!/usr/bin/env sh
set -e
./backup.sh
sqlite3 ./backup/multi_vote_bot/data.db -column -header
