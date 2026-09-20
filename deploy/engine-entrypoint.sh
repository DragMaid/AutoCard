#!/usr/bin/env sh
# Puts the trained checkpoint in place, then hands over to the engine.
#
# The weights are a release artifact rather than part of the image: /models is a
# volume, so a redeploy reuses the file already on disk and only a new URL (or a
# new AUTOCARD_WEIGHTS_SHA256) costs a download.
#
# The download is a hard precondition. If it fails, this exits non-zero and the
# engine never starts: the container stays unhealthy, deploy.sh's health poll
# times out and the previous release is put back. That is louder than serving an
# untrained AI seat to every single-player match, which is what an optional
# fetch used to do — a broken model would have reached players silently.
#
# AUTOCARD_SKIP_WEIGHTS=1 is the way out for a machine that should run without
# the checkpoint at all (local rules work, player-versus-player rooms, CI).
# There the AI seat falls back to an untrained agent, on purpose.
set -eu

if [ "${AUTOCARD_SKIP_WEIGHTS:-0}" = "1" ]; then
    echo "[entrypoint] AUTOCARD_SKIP_WEIGHTS=1; not fetching the checkpoint" >&2
    echo "[entrypoint] the AI seat will play untrained" >&2
elif python -m ml.fetch_weights; then
    echo "[entrypoint] checkpoint ready at ${AUTOCARD_CHECKPOINT:-/models/autocard-bot.pth}"
else
    echo "[entrypoint] FATAL: could not fetch the checkpoint; refusing to start" >&2
    echo "[entrypoint] check AUTOCARD_WEIGHTS_URL, AUTOCARD_WEIGHTS_SHA256 and HF_TOKEN," >&2
    echo "[entrypoint] or set AUTOCARD_SKIP_WEIGHTS=1 to run without a trained AI." >&2
    exit 1
fi

exec "$@"
