# multi_vote_bot
multiple-choice polls in telegram.  quite like @vote bot, but allows multiple choice.

## set up
place `TOKEN` in the environment file `.env`.

for webhooks:

 - set `WEBHOOK_URL` in the `.env`;
 - optionally set `LISTEN` and `PORT` (defaults to '127.0.0.1' and 80);
 - when running from docker, `docker-compose.yml` sets `LISTEN` to '0.0.0.0';
 - set up reverse proxy on that URL to forward traffic to the app's host and port.

bot will listen set webhook and handle queries on `WEBHOOK_URL/TOKEN`.

## run
`$ docker-compose up`

## restart
`$ ./restart.sh`
