# The authoritative Python engine. Build context is the repository root: the
# service imports core/ and ml/, and the card data in assets/ is what the rules
# are built from.
#
#   docker build -f deploy/engine.Dockerfile -t autocard-engine .

FROM python:3.13-slim AS deps

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /bin/uv

WORKDIR /src
COPY pyproject.toml uv.lock ./

RUN uv export --locked --format requirements-txt --no-hashes --no-emit-project \
    | grep -vE '^(nvidia-|triton|cuda-)' > /tmp/requirements.txt \
    && grep -E '^torch[=<>~ ]' /tmp/requirements.txt > /tmp/torch.txt

# torch on its own layer, everything else on the next. torch is most of the
# image and changes only when the lock's torch pin does
RUN uv venv /opt/venv \
    && VIRTUAL_ENV=/opt/venv uv pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        --index-strategy unsafe-best-match \
        -r /tmp/torch.txt

RUN VIRTUAL_ENV=/opt/venv uv pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        --index-strategy unsafe-best-match \
        -r /tmp/requirements.txt

# Pruning bullshit to reduce size
RUN rm -rf /opt/venv/lib/python3.13/site-packages/torch/test \
           /opt/venv/lib/python3.13/site-packages/torch/include \
    && find /opt/venv -name '__pycache__' -type d -prune -exec rm -rf {} + 


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
