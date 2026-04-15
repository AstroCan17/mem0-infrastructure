# Mem0 Infrastructure Setup Guide

## Quick Start

### Prerequisites
- Docker and Docker Compose installed
- OpenCode Zen API credentials available
- ~5GB free disk space (for models and data)

### 1. Start Services

```bash
# Start containers (Ollama + per-agent Mem0 Supergateways)
docker compose -f compose/docker-compose.yml up -d

# Verify services are healthy
docker compose -f compose/docker-compose.yml ps
docker compose -f compose/docker-compose.yml logs -f
```

### 2. Pull Embedding Model

```bash
# Pull mxbai-embed-large into Ollama (670MB, 1024-dims)
docker compose -f compose/docker-compose.yml exec ollama ollama pull mxbai-embed-large:latest

# Verify embeddings work
curl -s http://localhost:11435/api/embed \
  -d '{"model":"mxbai-embed-large:latest","input":"test"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK - {len(d[\"embeddings\"][0])} dims')"
```

### 3. Configure OpenCode Zen

If you are using the default hosted OpenCode Zen endpoint, no additional URL configuration is required.
Otherwise:
```bash
# Set OPENCODE_ZEN_URL to a custom endpoint
export OPENCODE_ZEN_URL=https://your-opencode-zen-host/v1/chat/completions

# Update .env
echo "OPENCODE_ZEN_URL=$OPENCODE_ZEN_URL" >> .env
```

### 4. Verify System Health

```bash
# Check Ollama
curl -s http://localhost:11435/api/tags | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(f'✓ Ollama: {len(d[\"models\"])} models')"

# Check Mem0 Supergateway
curl -s http://localhost:8766/healthz && echo "✓ Supergateway(mem0chat): healthy"

# Check a per-agent Supergateway
curl -s http://localhost:8767/healthz && echo "✓ Supergateway(codex): healthy"
```

## Service Details

### Ollama (Host Port 11435)
- **Image:** `ollama/ollama:latest`
- **Purpose:** Embedding model hosting (mxbai-embed-large)
- **Data:** `/root/.ollama` (persisted in `ollama_models` volume)
- **Commands:**
  ```bash
  docker compose exec ollama ollama list          # List models
  docker compose exec ollama ollama pull <model>  # Download model
  ```

### Mem0 Supergateway (Host Ports 8766-8772)
- **Image:** Custom Node.js + mem0-mcp
- **Purpose:** Memory bridge, MCP server, HTTP interface
- **Protocol:** streamableHttp (SSE-compatible)
- **Connects to:** Ollama (embeddings), OpenCode Zen
- **Data:** `/root/.copilot/mem0` (persisted in `mem0_data` volume)

### Agent CLIs (interactive)
Run an agent CLI container (examples):
```bash
docker compose -f compose/docker-compose.yml --profile agent-clis run --rm -it mem0chat-cli
docker compose -f compose/docker-compose.yml --profile agent-clis run --rm -it codex-cli
```

## Environment Variables

Create `.env` file to override defaults:

```env
# Mem0 configuration
MEM0_WORKSPACE=copernicus
MEM0_PROJECT=default
MEM0_STORE_PATH=/root/.copilot/mem0

# Ollama configuration
OLLAMA_BASE_URL=http://ollama:11434
MEM0_EMBED_MODEL=mxbai-embed-large:latest
MEM0_OLLAMA_TIMEOUT_MS=60000

# OpenCode Zen inference endpoint (custom if needed)
OPENCODE_ZEN_URL=https://opencode.ai/zen/v1/chat/completions
OPENCODE_ZEN_API_KEY=your_api_key_here
```

## Troubleshooting

### Services won't start
```bash
# Check logs
docker compose -f compose/docker-compose.yml logs ollama
docker compose -f compose/docker-compose.yml logs mem0-mcp

# Rebuild images
docker compose -f compose/docker-compose.yml build --no-cache
docker compose -f compose/docker-compose.yml up -d
```

### Ollama timeout errors
```bash
# Increase timeout in docker-compose.yml
# MEM0_OLLAMA_TIMEOUT_MS=60000 (default)
# Try 120000 for slower systems
docker compose -f compose/docker-compose.yml down
docker compose -f compose/docker-compose.yml up -d
```

### Memory persistence issues
```bash
# Check volume status
docker volume ls | grep mem0

# Backup data
docker run --rm -v mem0_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/mem0-backup.tar.gz -C /data .

# Restore data
docker volume rm mem0_data
docker run --rm -v mem0_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/mem0-backup.tar.gz -C /data
```

## Production Deployment

### 1. Remote OpenCode Zen Setup
- OpenCode Zen is hosted remotely and does not require local model serving.
- Ensure your API key and custom endpoint are configured securely.
- Set `OPENCODE_ZEN_URL` to your endpoint with HTTPS
- Use firewall rules or other network controls to restrict access to any private inference endpoint

### 2. Persistence
- Mem0 data persists in Docker volume `mem0_data`
- Ollama models persist in Docker volume `ollama_models`
- Backup volumes regularly:
  ```bash
  docker run --rm -v mem0_data:/data -v $(pwd):/backup \
    alpine tar czf /backup/mem0-$(date +%Y%m%d).tar.gz -C /data .
  ```

### 3. Scalability
- Code Sandbox can be replicated with different port mappings
- Use Docker Swarm or Kubernetes for multi-node deployments
- Keep single Ollama instance for cost efficiency

### 4. Monitoring
```bash
# Real-time stats
docker compose stats

# Service health
docker compose ps

# Detailed inspection
docker inspect <container-name>
```

## Next Steps

1. **Run agent CLIs:** `docker compose --profile agent-clis run --rm -it mem0chat-cli` (or `codex-cli`, `claude-cli`, `gemini-cli`, ...)
2. **Run hummusapiens browser:** `docker run -it hummusapiens --config` (browser automation)
3. **Deploy code sandbox:** Integrate with LLM for automated code execution
4. **Set up monitoring:** Use Docker events or container logs for observability

---
*Setup Version: 1.2.0*
*Compatible with: Docker Compose 3.8+, Docker Engine 20.10+*
