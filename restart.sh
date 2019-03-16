#!/usr/bin/env sh
set -e
docker-compose build
docker-compose down --remove-orphans
./backup.sh
docker-compose up -d
