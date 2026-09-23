# Deploying AutoCard

```
push to main ─► CI (pytest · relay build · web build · weights URL)
                  │
                  └─► build engine/relay/web ─► GHCR ─► ssh deploy@vps deploy.sh
                                                          │
              pull ─► up -d ─► fetch checkpoint ─► health ok (through Traefik)? ─┬─ yes: done
                                                                                 └─ no: previous tag back up, run fails
```

Three images, three containers. The engine and relay are the processes in
[`docs/BACKEND.md`](../docs/BACKEND.md):

| Image | Built from | What it is | Reached through |
|---|---|---|---|
| `autocard-engine` | `deploy/engine.Dockerfile` | the authoritative Python engine | nothing — the relay only |
| `autocard-relay` | `deploy/relay.Dockerfile` | the C# room server | Traefik, `https://<domain>/socket.io/` |
| `autocard-web` | `deploy/web.Dockerfile` | the built client behind a small nginx | Traefik, `https://<domain>/` |

`deploy/ansible/` is the other half: one-time (and re-runnable) server setup —
Docker, the `deploy` user, `/opt/autocard`, and Traefik if the box does not run
one yet. Releases do not go through it.

All three build from the repository root: the engine imports `core/` and `ml/`,
and the client needs the shared `assets/` directory.

Nothing in the stack publishes a port. Traefik owns 80/443 for the whole box,
gets certificates from Let's Encrypt, and finds the relay and the client
through the labels in `docker-compose.prod.yml`, on the shared `traefik` Docker
network. The engine is not on that network at all. Because the client is an
image tag like the other two, one `IMAGE_TAG` names one whole release,
rollback included.

## The model weights

The checkpoint is a release artifact, not a file in git. `ml/fetch_weights.py`
downloads it, and the engine's entrypoint runs that script before the service
starts:

```bash
python -m ml.fetch_weights            # download if missing
python -m ml.fetch_weights --check    # is the URL reachable?   (CI runs this)
python -m ml.fetch_weights --force    # replace what is there
```

- **Where from**: `AUTOCARD_WEIGHTS_URL`, defaulting to the published Hugging
  Face file. A `/blob/` link — the one the website's address bar shows — is
  rewritten to the `/resolve/` download link, so either form works.
- **Where to**: `AUTOCARD_CHECKPOINT`, which is the same variable
  `engine/config.py` reads. In production it is `/models/autocard-bot.pth` on a
  named volume, so a redeploy reuses the file instead of downloading it again.
- **Integrity**: the download is written to a temporary file and moved into
  place only after it is confirmed to be a torch checkpoint, so an interrupted
  download cannot leave a half-written file for the engine to load. Set
  `AUTOCARD_WEIGHTS_SHA256` (from `sha256sum autocard-bot.pth`) and the exact
  file is pinned as well.
- **Private repository**: set `HF_TOKEN`, as a secret in the `production`
  environment and in `PROD_ENV_FILE`.
- **A new model**: upload it, then either point `AUTOCARD_WEIGHTS_URL` at the
  new file (a repository variable overrides the checked-in default) or bump
  `AUTOCARD_WEIGHTS_SHA256`, and redeploy. Either change makes the entrypoint
  download again; an unchanged URL with an unchanged digest does not.

**The download gates the service.** If it fails, the entrypoint exits non-zero
and the engine never binds its port; the container stays unhealthy, the relay
(`depends_on: service_healthy`) never starts, `deploy.sh` times out and puts the
previous release back. A broken `AUTOCARD_WEIGHTS_URL` is a red workflow run, not
an untrained opponent nobody noticed. Set `AUTOCARD_SKIP_WEIGHTS=1` to run
without a checkpoint on purpose — local work, or a box meant only for
player-versus-player.

The one case still soft: a checkpoint that downloads fine but does not fit the
current network. It is logged with the shape mismatch and the room stays
playable with an untrained agent, because by then the file has passed every
check the fetcher can make. Grep the engine log for `[weights]`, `[entrypoint]`
and `does not fit the current model`.

Because the fetch happens before the port opens, a cold `models` volume makes
the first boot slow — the image's `HEALTHCHECK` allows a five-minute start
period and `deploy.sh` polls for six minutes before calling a release bad.

## First-time setup

1. **DNS**: point `autocard.example.com` at the VPS. One hostname serves both
   the client and the relay: the bundle is built with `VITE_GAME_API` pointing
   at that same origin, so the relay's CORS allow-list is a single entry and the
   socket handshake needs no preflight.
2. **Deploy key**: `ssh-keygen -t ed25519 -f ~/.ssh/autocard-deploy -C autocard-deploy`.
   The playbook below authorizes the public half and creates `/opt/autocard`.
3. **Provision the VPS**: Docker, the `deploy` user, `/opt/autocard`,
   unattended security upgrades, and Traefik:
   ```sh
   cd deploy/ansible
   cp inventory.example.ini inventory.ini   # host, email, key path
   ansible-galaxy collection install -r requirements.yml
   ansible-playbook -i inventory.ini playbook.yml
   ```
   It is idempotent and re-runnable. About Traefik:
   - **None running yet**: it installs one at `/opt/traefik` (HTTP→HTTPS
     redirect, Let's Encrypt over the TLS challenge, Docker provider) and keeps
     it up to date on later runs. It refuses to start while something else
     holds 80/443, and names what does.
   - **One already running**: it is left alone. The playbook only creates the
     `traefik` network (or `traefik_network`). Attach your Traefik to that
     network, set `TRAEFIK_NETWORK` / `TRAEFIK_ENTRYPOINT` /
     `TRAEFIK_CERTRESOLVER` in `PROD_ENV_FILE` if yours uses other names, and
     raise its HTTPS entrypoint's `respondingTimeouts.readTimeout` (see below).
   - **Coming from the nginx setup**: it removes the old `autocard` vhost and
     the unpacked `web-*` releases in `/opt/autocard`. Other nginx sites still
     on 80/443 have to move behind Traefik first.

   Before DNS points at the server, Traefik serves its own self-signed
   certificate. It requests the real one once the name resolves.
4. **GitHub** → Settings → Environments → `production`:

   | kind   | name                   | value                                                      |
   |--------|------------------------|------------------------------------------------------------|
   | secret | `VPS_SSH_KEY`          | contents of `~/.ssh/autocard-deploy`                        |
   | secret | `VPS_KNOWN_HOSTS`      | `ssh-keyscan -p 22 <host>` — compare to the server's own fingerprint |
   | secret | `PROD_ENV_FILE`        | `deploy/.env.example`, filled in                            |
   | secret | `HF_TOKEN`             | optional, only while the model repository is private        |
   | var    | `VPS_HOST`             | host or IP                                                  |
   | var    | `VPS_PORT`             | optional, default 22                                        |
   | var    | `PUBLIC_API_URL`       | `https://autocard.example.com` — baked into the bundle as `VITE_GAME_API` |
   | var    | `AUTOCARD_WEIGHTS_URL` | optional override of the checkpoint URL                     |

5. Push to `main`, or run **Deploy** by hand.

## Day to day

- **Release**: merge to `main`. Nothing else.
- **Roll back**: Actions → Deploy → Run workflow → `image_tag` = an earlier
  commit SHA. No rebuild; it redeploys what is already in GHCR.
- **Change a setting**: edit `PROD_ENV_FILE`, re-run the latest Deploy.
- **Logs**: `ssh deploy@vps 'cd /opt/autocard && docker compose -f docker-compose.prod.yml logs -f engine'`
  (or `relay`, `web`). Routing and certificate problems are in Traefik's:
  `cd /opt/traefik && docker compose logs -f`.
- **What is live**: `ssh deploy@vps 'cat /opt/autocard/.current-tag'`.
- **Check the live model**: the engine logs `Loaded AI checkpoint from …` the
  first time an AI room asks for it — lazily, so it appears on the first single
  player match rather than at boot.

## Worth knowing

- **CPU torch.** `uv.lock` resolves the CUDA build of torch, which is ~3 GB of
  kernels a CPU VPS cannot use. The engine image and the CI job both export the
  lock, drop the `nvidia-*` and `triton` wheels, and install from PyTorch's CPU
  index — same pinned versions, a fraction of the size. Training on a GPU box
  still installs from the lock in the usual way.
- **The engine image is the runtime set only.** `pyproject.toml` keeps training
  behind an extra, so mlflow, dagshub and the ~500 MB of pandas/scipy/pyarrow/
  scikit-learn behind them stay out of the image — nothing the engine imports
  touches them. Training and testing install them explicitly:
  `uv sync --extra dev --extra training`. With `torch/test` and `torch/include`
  stripped too, the image is about 1.1 GB rather than 2.1 GB.
- **Layer digests are the other half of a fast deploy.** The build is not
  reproducible — two identical builds give different layer digests — so a CI
  cache miss makes the VPS re-pull torch, ~700 MB, for a release that changed
  nothing in it. That is why the build caches to GHCR (`:buildcache`) rather
  than GitHub's 10 GB evicting cache. `deploy.sh` prints how long the pull took:
  seconds means the cache held, minutes means a heavy layer churned.
- **Live matches and redeploys.** `AUTOCARD_ROOM_TTL` (300s) is how long a room
  outlives its relay socket. A rollout inside that window resumes matches; a
  longer one drops them. There is no database and nothing else to migrate.
- **A missing checkpoint fails the rollout; an incompatible one does not.** The
  entrypoint refuses to start without the file, so a URL that has gone away is
  caught at deploy time. A file that loads but does not match the current
  network shape still degrades the AI seat quietly — `AIOpponent.__init__`
  catches it so a bad export cannot take player-versus-player rooms down with
  it. Pin `AUTOCARD_WEIGHTS_SHA256` if you want that case caught too.

- **WebSockets and Traefik's read timeout.** Since v3, Traefik closes a
  connection after 60s by default (`respondingTimeouts.readTimeout`). A match
  is a socket that can sit idle while a player thinks, so the Traefik the
  playbook installs raises it to 3600s. A Traefik you bring yourself needs the
  same, or matches drop every minute.
- **Why a web container.** Traefik routes but cannot serve files, so the client
  ships as `nginx:stable-alpine-slim` with `dist/` baked in. That nginx sets the
  cache headers: `/assets/` is immutable for 30 days, and `index.html` is
  `no-cache` so a deploy shows up straight away. It does nothing about TLS or
  proxying.
