#!/usr/bin/env bash
# Rolls the stack at /opt/autocard forward to the IMAGE_TAG in .env. Run by the
# deploy workflow over SSH, after it has uploaded docker-compose.prod.yml and a
# fresh .env.
#
#   Usage: deploy.sh <ghcr-user>   (a registry token is read from stdin; empty = no login)
#
# On a failed health check it puts the previous tag back and exits non-zero, so
# the workflow run goes red while the site keeps serving the last good release.
# There is no database here: the only state that survives a rollout is the
# downloaded checkpoint, and live matches, which the relay resumes through the
# engine's room TTL if the roll forward is quick enough. The engine will not
# start at all without its checkpoint, so a broken AUTOCARD_WEIGHTS_URL shows up
# here as a failed health check and a rollback.
set -euo pipefail

cd "$(dirname "$0")"

compose=(docker compose -f docker-compose.prod.yml)
ghcr_user="${1:-}"

# Last assignment wins, and everything after the first '=' is the value.
env_value() {
    grep -E "^$1=" .env | tail -n1 | cut -d= -f2-
}

new_tag="$(env_value IMAGE_TAG)"
previous_tag="$(cat .current-tag 2>/dev/null || true)"
relay_port="$(env_value RELAY_PORT)"; relay_port="${relay_port:-8180}"
web_port="$(env_value WEB_PORT)"; web_port="${web_port:-3200}"

echo "==> Deploying ${new_tag} (previous: ${previous_tag:-none})"

# Read from stdin rather than $1, so the token never appears in `ps` or in a log.
token="$(cat)"
if [[ -n "$token" ]]; then
    echo "$token" | docker login ghcr.io -u "$ghcr_user" --password-stdin >/dev/null
fi

pull_status=0
"${compose[@]}" pull --quiet || pull_status=$?
[[ -n "$token" ]] && docker logout ghcr.io >/dev/null
(( pull_status == 0 )) || { echo "!! pull failed"; exit "$pull_status"; }

# The engine is not published, so it is checked through its container health
# state — which is the same /health endpoint, asked from inside.
engine_healthy() {
    local id
    id="$("${compose[@]}" ps --quiet engine)"
    [[ -n "$id" ]] && [[ "$(docker inspect -f '{{.State.Health.Status}}' "$id")" == "healthy" ]]
}

# Six minutes, not one: on a fresh volume the engine's entrypoint downloads the
# checkpoint before it binds its port, and it refuses to start without it.
healthy() {
    for _ in $(seq 1 180); do
        if engine_healthy &&
           curl -fsS -o /dev/null "http://127.0.0.1:${relay_port}/health" &&
           curl -fsS -o /dev/null "http://127.0.0.1:${web_port}/health"; then
            return 0
        fi
        sleep 2
    done
    return 1
}

rollback() {
    echo "!! Release ${new_tag} failed"
    "${compose[@]}" logs --tail 80 engine relay web || true

    if [[ -z "$previous_tag" || "$previous_tag" == "$new_tag" ]]; then
        echo "!! No previous release to roll back to"
        exit 1
    fi

    echo "==> Rolling back to ${previous_tag}"
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${previous_tag}/" .env
    "${compose[@]}" up -d --remove-orphans
    exit 1
}

"${compose[@]}" up -d --remove-orphans || rollback
healthy || rollback

echo "$new_tag" > .current-tag

# Only this stack's images (labelled at build time) and only ones no container
# uses, so the other sites' images are never touched.
docker image prune --all --force \
    --filter "label=org.opencontainers.image.vendor=autocard" \
    --filter "until=240h" >/dev/null

echo "==> ${new_tag} is live"
