#!/usr/bin/env bash
# Usage: ./backend/scripts/preload_model.sh <model-name>
# Example: ./backend/scripts/preload_model.sh llama3
#
# Ollama runs under the Compose `local` profile. No service declares a fixed
# `container_name`, so Compose creates project-scoped names and this script
# addresses the service through Compose rather than guessing the container.
set -euo pipefail

MODEL=${1:-llama3}
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
READY_TIMEOUT_SECONDS=${READY_TIMEOUT_SECONDS:-60}

if docker compose version >/dev/null 2>&1; then
    compose() { docker compose --profile local "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
    compose() { docker-compose --profile local "$@"; }
else
    echo "Error: neither 'docker compose' nor 'docker-compose' is available." >&2
    exit 1
fi

cd "$REPO_ROOT"

container=$(compose ps --quiet ollama 2>/dev/null || true)
if [ -z "$container" ] ||
    [ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null)" != "true" ]; then
    echo "Error: the 'ollama' service is not running. Start it with:" >&2
    echo "  docker compose --profile local up -d ollama" >&2
    exit 1
fi

# The service reports running before its API accepts requests, so wait for the
# API itself rather than for the container state.
echo "Waiting up to ${READY_TIMEOUT_SECONDS}s for Ollama to accept requests..."
ready=""
for _ in $(seq 1 "$READY_TIMEOUT_SECONDS"); do
    if compose exec -T ollama ollama list >/dev/null 2>&1; then
        ready="yes"
        break
    fi
    sleep 1
done

if [ -z "$ready" ]; then
    echo "Error: the 'ollama' service did not become ready in time." >&2
    exit 1
fi

echo "Pulling model: $MODEL into the ollama service..."
compose exec -T ollama ollama pull "$MODEL"
echo "Done."
