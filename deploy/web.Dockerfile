# The browser client, built once and shipped as static files.
#
# Vite emits a directory, not a server, and the VPS already runs nginx for TLS
# — so nothing here serves anything. The image is a delivery container: deploy.sh
# pulls the tag, `docker cp`s /dist onto the host and points the vhost at it.
# That is also what makes rollback work, since every release's files are still
# in GHCR under its own tag.
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


# Add basc shell for troubleshooting down the line
FROM busybox:1.37-musl AS runtime

COPY --from=build /src/dist /dist

CMD ["true"]
