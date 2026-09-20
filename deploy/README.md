# Deploying AutoCard

```
push to main ─► CI (pytest · relay build · web build · weights URL)
                  │
                  └─► build engine/relay/web ─► GHCR ─► ssh deploy@vps deploy.sh
                                                          │
       pull ─► up -d ─► fetch checkpoint ─► unpack client ─► health ok? ─┬─ yes: done
                                                                       └─ no: previous tag back up, run fails
```

Three images; two of them run. The processes are the ones in
[`docs/BACKEND.md`](../docs/BACKEND.md):

| Image | Built from | What it is | Published on |
|---|---|---|---|
| `autocard-engine` | `deploy/engine.Dockerfile` | the authoritative Python engine | nothing — internal only |
| `autocard-relay` | `deploy/relay.Dockerfile` | the C# room server | `127.0.0.1:8180` |
| `autocard-web` | `deploy/web.Dockerfile` | the built client — static files, never run | unpacked to `/opt/autocard/web` |

`deploy/ansible/` is the other half: one-time (and re-runnable) server setup —
Docker, the `deploy` user, `/opt/autocard`, the nginx vhost and its certificate.
Releases do not go through it.

All three build from the repository root: the engine imports `core/` and `ml/`,
and the client needs the shared `assets/` directory.

Only two of them are containers on the VPS. `npm run build` emits a directory of
static files, not a server, and the host already runs nginx — so the client is
served off disk rather than through a second nginx in a container of its own.
The image is still how it travels: `deploy.sh` unpacks it with `docker cp` into
`/opt/autocard/web-<tag>` and swaps the `web` symlink, which is what keeps one
`IMAGE_TAG` naming one whole release, rollback included.

Nothing binds a public port — the host's nginx terminates TLS, serves the files
and proxies `/socket.io/` to the relay's loopback port, so this stack shares
80/443 with anything else on the box.

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
   the client and the relay — see the vhost for why.
2. **Deploy key**: `ssh-keygen -t ed25519 -f ~/.ssh/autocard-deploy -C autocard-deploy`.
   The playbook below authorizes the public half and creates `/opt/autocard`.
3. **Provision the VPS** — Docker, the `deploy` user, `/opt/autocard`, the
   nginx vhost (site at `/`, the relay's `/socket.io/` WebSocket endpoint, both
   over TLS) and unattended security upgrades:
   ```sh
   cd deploy/ansible
   cp inventory.example.ini inventory.ini   # host, domain, email, key path, ports
   ansible-galaxy collection install -r requirements.yml
   ansible-playbook -i inventory.ini playbook.yml
   ```
   It is idempotent and re-runnable, and it touches only its own vhost — other
   sites on the box, and `nginx.conf` itself, are left alone. Before DNS points
   at the server, set `tls_mode=selfsigned` in the inventory and switch to
   `letsencrypt` later.
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
  — the client has no logs of its own; it is in the host's nginx access log.
- **What is live**: `ssh deploy@vps 'readlink /opt/autocard/web'` — the release
  the vhost is serving right now. The previous one is kept beside it, and
  everything older is pruned on each deploy.
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

- **Two nginxes would have been one too many.** The host needs one anyway, for
  TLS and to share 80/443 with the other sites. An `nginx:alpine` container in
  front of `dist/` would only have added a proxy hop and a second config to keep
  in step. The trade is that `deploy.sh` owns an unpack-and-swap step instead —
  worth it here, and not worth it in a project whose frontend ships its own
  server (Next.js, say), where the container is already the server.
