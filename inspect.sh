#!/usr/bin/env sh
set -e
docker-compose up -d
docker run \
    -i -t --rm \
    $(for id in $(docker-compose ps -q);
        do echo --volumes-from ${id};
    done) \
    --workdir /root/.local/share/multi_vote_bot \
    nouchka/sqlite3 sqlite3 data.db -column -header
