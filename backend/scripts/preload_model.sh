#!/usr/bin/env bash
# Usage: ./scripts/preload_model.sh <model-name>
# Example: ./scripts/preload_model.sh vantage-fin

MODEL=${1:-"llama3"}
echo "Pulling model: $MODEL into Ollama container..."

if [ "$(docker ps -q -f name=vantage-ollama)" ]; then
    docker exec vantage-ollama ollama pull "$MODEL"
    echo "Done."
else
    echo "Error: vantage-ollama container is not running. Start it with docker-compose up first."
    exit 1
fi
