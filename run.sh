#!/usr/bin/env bash

set -euo pipefail

# Install uv if missing
if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found. Installing..."

    INSTALL_OUTPUT=$(curl -LsSf https://astral.sh/uv/install.sh | sh 2>&1)

    echo "$INSTALL_OUTPUT"

    UV_PATH=$(echo "$INSTALL_OUTPUT" | grep -oE '/[^ ]+/bin' | head -n 1)

    if [ -n "${UV_PATH:-}" ]; then
        export PATH="$UV_PATH:$PATH"
    else
        echo "Failed to detect uv install path"
        exit 1
    fi
fi

MODE="${1:-}"

shift || true

case "$MODE" in
    --server)
        PYTHONPATH=. uv run ml/distributed/server.py "$@"
        ;;

    --learner)
        DEVICE=""

        while [[ $# -gt 0 ]]; do
            case "$1" in
                --device)
                    DEVICE="$2"
                    shift 2
                    ;;
                *)
                    echo "Unknown learner arg: $1"
                    exit 1
                    ;;
            esac
        done

        if [[ -z "$DEVICE" ]]; then
            echo "--device is required"
            exit 1
        fi

        PYTHONPATH=. uv run ml/distributed/learner.py --device "$DEVICE" --debug
        ;;

    --actor)
        COUNT=1
        EXTRA_ARGS=()

        while [[ $# -gt 0 ]]; do
            case "$1" in
                --count)
                    COUNT="$2"
                    shift 2
                    ;;
                *)
                    EXTRA_ARGS+=("$1")
                    shift
                    ;;
            esac
        done

        trap 'kill 0' SIGINT SIGTERM
        for ((i=0; i<COUNT; i++)); do
            PYTHONPATH=. uv run ml/distributed/actor.py "${EXTRA_ARGS[@]}" --debug &
        done

        wait
        ;;

    *)
        echo "Usage:"
        echo "  ./run.sh --server"
        echo "  ./run.sh --learner --device cuda"
        echo "  ./run.sh --actor --count 4"
        exit 1
        ;;
esac
