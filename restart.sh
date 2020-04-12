#!/bin/sh

set -e
echo ':: restarting...'

# @multi_vote_bot is now hosting on docker hub.
# But if you are developing your own fork, you would prefer to build from sources,
# or at least pull from another repository.
docker-compose pull
#docker-compose build

docker-compose down --remove-orphans
./backup.sh
docker-compose up -d
echo ':: done: restarting.'
