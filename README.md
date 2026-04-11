# Vantage

Vantage is an AI-powered quantitative analysis terminal.

## Running with Docker

You can easily spin up the entire application stack: the React frontend, the FastAPI backend, and the local Ollama LLM provider.

### Prerequisites
- Docker ≥ 24
- Docker Compose v2
- (Optional) NVIDIA Container Toolkit if you plan to use GPU acceleration for Ollama.

### Step-by-Step Startup

1. **Build and start the cluster in the background:**
   ```bash
   docker-compose up --build -d
   ```

2. **Preload the local LLM model:**
   Since the Ollama container expects the model to be downloaded, run the preload script:
   ```bash
   ./backend/scripts/preload_model.sh vantage-fin
   ```
   *(Note: you can substitute `vantage-fin` with any other model name you have configured. Due to connection setup, this may require a few minutes to download the model layers).*

3. **Verify Health:**
   ```bash
   curl http://localhost:8000/health
   ```
   If everything responds with status ok, the system is fully up.
   The frontend is available at `http://localhost:5173`.

### Teardown

To bring the stack down and stop all containers without losing downloaded models:
```bash
docker-compose down
```

To bring the stack down **and completely wipe the datastore (Ollama models)**:
```bash
docker-compose down -v
```

### Environment Variables

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `OLLAMA_BASE_URL` | Base URL used by the backend to hit Ollama. | `http://ollama:11434` (in Compose) |
| `VANTAGE_AI_DIR` | Used for local gguf models (if not using remote registry) | `./vantage_ai` |

