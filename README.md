# multi_vote_bot
multiple-choice polls in telegram.  quite like @vote bot, but allows multiple choice.

## set up
place `TOKEN` in the environment file `.env`.

for webhooks:

 - set `WEBHOOK_URL` in the `.env`;
 - optionally set `IP` and `PORT` (defaults to '127.0.0.1' and 80);
 - when running from docker, consider setting `IP` to '0.0.0.0';
 - set up reverse proxy on that URL to forward traffic to the app's host and port.

## run
`$ docker-compose up`

## restart
`$ ./restart.sh`
