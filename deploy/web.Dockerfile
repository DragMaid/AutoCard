# syntax=docker/dockerfile:1
# The browser client: the Vite build behind a small nginx that Traefik routes to.
#
# Traefik terminates TLS but cannot serve files, so the client ships as its own
# container. nginx here only serves dist/ and sets the cache headers; it knows
# nothing about TLS or the relay.
#
# Build context is the repository root because the card art lives in the shared
# assets/ directory outside web/. In a checkout web/public/assets is a symlink
# to it; here it is replaced by the real directory, so Vite copies the art into
# dist/assets exactly as `npm run dev` serves it.
#
#   docker build -f deploy/web.Dockerfile --build-arg VITE_GAME_API=https://autocard.example.com -t autocard-web .

FROM node:22-slim AS build

# Baked into the bundle at build time, which is why a change of API URL is a
# rebuild rather than a restart.
ARG VITE_GAME_API=http://localhost:8080
ARG VITE_ASSET_BASE=/assets
ENV VITE_GAME_API=$VITE_GAME_API \
    VITE_ASSET_BASE=$VITE_ASSET_BASE

WORKDIR /src
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
COPY assets/ /assets-src/
RUN rm -rf public/assets && cp -r /assets-src public/assets \
    && npm run build


FROM nginx:stable-alpine-slim AS runtime

COPY <<'EOF' /etc/nginx/conf.d/default.conf
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    # Hashed filenames, so they can be cached until the heat death of the
    # universe. index.html below must not be, or a deploy is invisible to
    # anyone holding a cached copy.
    location /assets/ {
        try_files $uri =404;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location = /index.html {
        add_header Cache-Control "no-cache";
    }

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;
}
EOF

COPY --from=build /src/dist /usr/share/nginx/html

# Traefik only routes to a container once it reports healthy, and deploy.sh
# waits on the same state.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --start-interval=1s \
    CMD wget -q --spider http://127.0.0.1/ || exit 1
