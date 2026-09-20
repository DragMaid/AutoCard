# The authoritative Python engine. Build context is the repository root: the
# service imports core/ and ml/, and the card data in assets/ is what the rules
# are built from.
#
#   docker build -f deploy/engine.Dockerfile -t autocard-engine .

FROM python:3.13-slim AS deps

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /bin/uv

WORKDIR /src
COPY pyproject.toml uv.lock ./

# uv.lock is the single source of truth for versions, but it resolves the CUDA
# build of torch — four gigabytes of kernels for a GPU this server does not
# have. Exporting the lock, dropping the CUDA payload and pointing the install
# at PyTorch's CPU index keeps the pinned versions while cutting the image by
# roughly 3 GB. A GPU box (training) installs from the lock as usual.
RUN uv export --locked --format requirements-txt --no-hashes --no-emit-project \
    | grep -vE '^(nvidia-|triton)' > /tmp/requirements.txt

RUN uv venv /opt/venv \
    && VIRTUAL_ENV=/opt/venv uv pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        --index-strategy unsafe-best-match \
        -r /tmp/requirements.txt


FROM python:3.13-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # No display anywhere near this process: core/ imports pygame for the
    SDL_VIDEODRIVER=dummy \
    SDL_AUDIODRIVER=dummy \
    AUTOCARD_CHECKPOINT=/models/autocard-bot.pth

COPY --from=deps /opt/venv /opt/venv

WORKDIR /app
COPY core/ core/
COPY engine/ engine/
COPY ml/ ml/
COPY gui/ gui/
COPY assets/ assets/
COPY conftest.py ./
COPY deploy/engine-entrypoint.sh /usr/local/bin/entrypoint.sh

# Runs unprivileged, and owns only what it writes: its log directory and the
# volume the checkpoint is downloaded into.
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && useradd --system --uid 10001 --create-home autocard \
    && mkdir -p /app/logs /models \
    && chown -R autocard:autocard /app/logs /models
USER autocard

EXPOSE 9000

# Healthcheck
HEALTHCHECK --interval=15s --timeout=5s --start-period=300s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9000/health', timeout=4).status==200 else 1)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python", "-m", "engine"]
