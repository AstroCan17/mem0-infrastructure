# AGENTS.md

## Quick Start

```bash
# Start the foundation stack (3 services)
docker compose -f compose/docker-compose.yml up -d

# Verify health
curl -sf http://localhost:8766/healthz && echo " mem0-mcp ok"
curl -sf http://localhost:6333/healthz && echo " qdrant ok"
curl -sf http://localhost:11435/api/tags > /dev/null && echo " ollama ok"

# Run full smoke test
./scripts/smoke-test.sh
```

## Key Commands

- **Start services:** `docker compose -f compose/docker-compose.yml up -d`
- **Start with PlantUML:** `docker compose -f compose/docker-compose.yml --profile tools up -d`
- **List running containers:** `docker compose -f compose/docker-compose.yml ps`
- **View logs:** `docker compose -f compose/docker-compose.yml logs -f <service>`
- **Stop all:** `docker compose -f compose/docker-compose.yml down`

## Port Mapping

| Service | Host Port | Protocol |
|---------|-----------|----------|
| Ollama | 11435 | HTTP (embedding + extraction LLM) |
| Qdrant | 6333 | REST API (vector store) |
| Qdrant gRPC | 6334 | gRPC |
| Mem0 Supergateway | 8766 | streamableHttp (MCP) |
| PlantUML (tools profile) | 8888 | HTTP |

All ports bound to `127.0.0.1` only.

## Architecture

```
Host CLIs (Cursor, Copilot, Claude Code, OpenCode, Blackbox)
    │ streamableHttp + workspace/project scope
    ▼
┌─────────────────────────────────┐
│ mem0-mcp Supergateway :8766     │
│ /mcp (MCP endpoint)             │
│ /healthz (health check)         │
└──────┬──────────────┬───────────┘
       │              │
┌──────▼──────┐ ┌─────▼──────┐
│ Ollama      │ │ Qdrant     │
│ :11435      │ │ :6333      │
│ embed model │ │ vectors    │
│ extract LLM │ │ (cosine)   │
└─────────────┘ └────────────┘
```

## Critical Gotchas

1. **Use streamableHttp, NOT SSE** — Supergateway crashes with "Already connected to a transport" if multiple clients connect via SSE.

2. **Timeout is 60s, not default 10s** — `MEM0_OLLAMA_TIMEOUT_MS=60000` prevents cold-start failures.

3. **Use mxbai-embed-large, not larger models** — The 670MB model runs on CPU. Larger models cause high CPU and slow embeddings.

4. **Qdrant dimension must match embedding model** — `mxbai-embed-large` outputs 1024 dimensions. Qdrant collection must use `vector_size: 1024`.

5. **Extraction LLM != Chat LLM** — Ollama `qwen3:1.7b` inside mem0-mcp extracts facts from conversations (background). It does NOT chat with users. Chat is handled by each host CLI's own model.

## Environment

See `.env.example` for all configuration variables. Copy to `.env` before first run:
```bash
cp .env.example .env
```

## Volumes

- `ollama_models` — Persists Ollama model weights (mxbai-embed-large + qwen3:1.7b)
- `qdrant_storage` — Persists Qdrant vector data
- `mem0_data` — Persists mem0 SQLite metadata (`/root/.copilot/mem0`)

## References

- Architecture details: `docs/architecture/architecture-plan.md`
- Foundation plan: `.cursor/plans/mem0_foundation_cleanup_eac7a880.plan.md`
- Smoke test: `scripts/smoke-test.sh`
