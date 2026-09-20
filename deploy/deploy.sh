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
site_domain="$(env_value SITE_DOMAIN)"
image_prefix="$(env_value IMAGE_PREFIX)"

# Where the vhost's `root` points. A symlink, swapped in one atomic rename, so
# nginx never serves a half-copied release.
web_link="web"
web_dir="web-${new_tag}"

echo "==> Deploying ${new_tag} (previous: ${previous_tag:-none})"

# Read from stdin rather than $1, so the token never appears in `ps` or in a log.
token="$(cat)"
if [[ -n "$token" ]]; then
    echo "$token" | docker login ghcr.io -u "$ghcr_user" --password-stdin >/dev/null
fi

# NOTE: here we are storing the frontend files in a docker container, this allow auto versoning
pull_started=$SECONDS
pull_status=0
"${compose[@]}" pull --quiet || pull_status=$?
(( pull_status == 0 )) && { docker pull --quiet "${image_prefix}/autocard-web:${new_tag}" >/dev/null || pull_status=$?; }
[[ -n "$token" ]] && docker logout ghcr.io >/dev/null
(( pull_status == 0 )) || { echo "!! pull failed"; exit "$pull_status"; }
echo "==> Pull took $((SECONDS - pull_started))s"

publish_web() {
    local tag="$1" target=".web-${tag}.partial" container
    # If the extracted directory already exists, then just update the symlink
    # the ln command with the following parameters:
    # -s: create a symlink
    # -f: force overwrite
    # -n: treat .web.tmp as a file if it is a symlink to a dir
    # mv -T .web.tmp "$web_link" rename to $web_link (-T treat target as a file)
    [[ -d "web-${tag}" ]] && { ln -sfn "web-${tag}" .web.tmp && mv -T .web.tmp "$web_link"; return; }

    rm -rf "$target"
    mkdir -p "$target"
    # Create a container from the image without starting it, before extracting the data and destroying it
    container="$(docker create "${image_prefix}/autocard-web:${tag}")"
    docker cp "${container}:/dist/." "$target"
    docker rm -f "$container" >/dev/null

    # Checking if index.html is actually there
    [[ -f "${target}/index.html" ]] || { echo "!! no index.html in the web image"; rm -rf "$target"; return 1; }
    # Rename the whole thing from partial to real deployed (done so nginx doesn't read
    # incomplete deployments)
    mv -T "$target" "web-${tag}"
    ln -sfn "web-${tag}" .web.tmp && mv -T .web.tmp "$web_link"
}

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
           curl -fsS -o /dev/null "http://127.0.0.1:${relay_port}/health"; then
            return 0
        fi
        sleep 2
    done
    return 1
}

# Testing for frontend reachability
site_reachable() {
    # -f: force return non-zero exit code if http code returned is within 4XX
    # -s: silent the progress meter
    # -S: show error if the request were to fail
    # -k: allows insecure (no TLS/SSL mode) for self-signed test
    curl -fsSk -o /dev/null --max-time 10 \
        --resolve "${site_domain}:443:127.0.0.1" "https://${site_domain}/"
}

rollback() {
    echo "!! Release ${new_tag} failed"
    "${compose[@]}" logs --tail 80 engine relay || true

    if [[ -z "$previous_tag" || "$previous_tag" == "$new_tag" ]]; then
        echo "!! No previous release to roll back to"
        exit 1
    fi

    echo "==> Rolling back to ${previous_tag}"
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${previous_tag}/" .env
    "${compose[@]}" up -d --remove-orphans
    publish_web "$previous_tag" || echo "!! could not restore the previous client"
    exit 1
}

"${compose[@]}" up -d --remove-orphans || rollback
healthy || rollback

publish_web "$new_tag" || rollback
site_reachable || rollback

echo "$new_tag" > .current-tag

# Only keep current / previous deployment folders, the rest gets eradicated (except for files and symlinks)
for stale in web-*; do
    [[ -d "$stale" ]] || continue
    [[ "$stale" == "$web_dir" || "$stale" == "web-${previous_tag}" ]] && continue
    rm -rf "$stale"
done

# Only this stack's images (labelled at build time) and only ones no container
# uses, so the other sites' images are never touched.
docker image prune --all --force \
    --filter "label=org.opencontainers.image.vendor=autocard" \
    --filter "until=240h" >/dev/null

echo "==> ${new_tag} is live"
