#!/bin/sh
mkdir -p backup
docker run \
    --rm \
    -v multi_vote_bot:/multi_vote_bot \
    -v "$PWD"/backup:/backup \
    alpine cp -a /multi_vote_bot /backup/
