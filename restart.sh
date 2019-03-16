#!/bin/sh

set -e
echo ':: restarting...'
docker-compose build
docker-compose down --remove-orphans
./backup.sh
docker-compose up -d
echo ':: done: restarting.'
