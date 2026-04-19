# System Architecture: AI Engineer Stack (v3 — Foundation)

## 1. Overview
Shared memory infrastructure for AI agent CLIs. Host-based CLIs (Cursor, Copilot, Claude Code, OpenCode, Blackbox Pro) connect to a single mem0-mcp Supergateway backed by Ollama (embeddings + extraction LLM) and Qdrant (vector store). Zero cost, all local containers.

**Environment:** Kali Linux 2026.1 | Node.js v22 | Docker Compose

---

## 2. Component Stack

### 2.1 Chat Inference (Host CLIs — not containerized)
- **Type:** Each host CLI uses its own LLM provider
- **Providers:**
  - Cursor (own model)
  - VS Code Copilot (own model)
  - Claude Code CLI (Claude model)
  - OpenCode CLI (Nemotron — free)
  - Blackbox Pro CLI (Pro model)
- **Deployment:** All run on the host machine, not in Docker containers
- **Memory access:** Each CLI connects to `http://127.0.0.1:8766/mcp` with workspace/project scope

### 2.2 Memory: Mem0 + Supergateway (MCP Bridge)
- **Mem0 Server:** Node.js MCP server (`mem0-mcp` npm package)
- **Supergateway Bridge:** Converts MCP protocol → HTTP (streamableHttp)
- **Topology (v3):** Single Supergateway instance, CLIs pass scope in requests
- **Transport:** streamableHttp (NOT SSE, supports multiple clients)
- **Metadata Backend:** SQLite at `/root/.copilot/mem0/`
- **Vector Backend:** Qdrant at `http://qdrant:6333` (collection: `mem0_memories`, 1024-dim cosine)
- **Extraction LLM:** Ollama `qwen3:1.7b` (background fact extraction, not user-facing)
- **Scoping:** `workspace` + `project` dimensions for context isolation
- **Health Check:** `http://localhost:8766/healthz`

### 2.3 Embedder + Extraction: Ollama (Local)
- **Container:** Custom build (`services/ollama/Dockerfile`)
- **Port:** `11434` (exposed as `127.0.0.1:11435` on host)
- **Models:**
  - `mxbai-embed-large:latest` — Embedding (670 MB, 1024 dimensions, <1s on CPU)
  - `qwen3:1.7b` — Extraction LLM for mem0 fact extraction (background, not user-facing)
- **Persistence:** `ollama_models` volume at `/root/.ollama`
- **Configuration:** `OLLAMA_KEEP_ALIVE=-1` (models always loaded)
- **Health Check:** `curl -sf http://localhost:11434/api/tags` (real API probe)

### 2.4 Vector Store: Qdrant (Local)
- **Container:** `qdrant/qdrant:latest`
- **Port:** `6333` REST (exposed as `127.0.0.1:6333`), `6334` gRPC
- **Collection:** `mem0_memories` (1024 dimensions, cosine distance)
- **Persistence:** `qdrant_storage` volume at `/qdrant/storage`
- **Configuration:** WAL enabled, telemetry disabled, no API key needed
- **Health Check:** `curl -sf http://localhost:6333/healthz`

### 2.5 Visualization: PlantUML Server
- **Container:** `plantuml/plantuml-server:jetty`
- **Port:** `8888` (exposed as `127.0.0.1:8888`)
- **Purpose:** Diagram/graph generation for documentation
- **Profile:** `tools` (not started by default)

---

## 3. Architecture Diagram

<div class="mermaid">
{% include diagrams/workflow-diagram-flowchart.mermaid %}
</div>

---

## 4. Communication Flow

### Memory Operations (v3 — Single Supergateway)
1. **Memory search:** Host CLI sends `memory_search` to `POST http://127.0.0.1:8766/mcp` with workspace/project scope
2. **Embedding:** mem0-mcp calls Ollama for query embedding (1024-dim vector)
3. **Vector search:** mem0-mcp searches Qdrant for similar vectors (top-K, cosine distance)
4. **Result:** Matching memories returned to CLI for context assembly
5. **Inference:** CLI calls its own LLM provider (Cursor model, Claude, Nemotron, etc.)
6. **Memory save:** CLI sends `memory_store` to same Supergateway endpoint
7. **Extraction:** mem0 extraction LLM (qwen3:1.7b) extracts facts in background
8. **Storage:** Facts stored as vectors in Qdrant, metadata in SQLite

### System Bootstrap Sequence
```
1. docker compose -f compose/docker-compose.yml up -d
2. Ollama starts, pulls mxbai-embed-large + qwen3:1.7b (first run)
3. Qdrant starts, health check passes
4. mem0-mcp starts after ollama + qdrant are healthy
5. Host CLIs connect to http://127.0.0.1:8766/mcp
```

---

## 5. Data Flow & Isolation

### Memory Scoping
- **Workspace:** Top-level context (e.g., `copernicus`)
- **Project:** Sub-context within workspace (e.g., `default`, `opencode`, `cursor`)
- **Benefits:** Multiple projects share embedder/vector DB but keep memories separate via scope filtering

### Container Isolation
- **Network:** `mem0-network` bridge (inter-container communication)
- **Host Access:** All ports bound to `127.0.0.1` only (no external exposure)
- **Volume Sharing:** `mem0_data` for SQLite metadata, `qdrant_storage` for vectors, `ollama_models` for weights

### Security Boundaries
- All services: Local-only bind (`127.0.0.1`) by default
- Qdrant: No API key needed (local container, no public access)
- Mem0 DB: No public network exposure (localhost only)

---

## 6. Key Deployment Rules

> [!IMPORTANT]
> **Rule 1: Host CLIs, containerized memory.**
> Agent CLIs run on the host. Only the memory layer (mem0-mcp + Ollama + Qdrant) runs in Docker.
>
> **Rule 2: Local embeddings always, extraction LLM local too.**
> Embeddings: Ollama mxbai-embed-large. Extraction: Ollama qwen3:1.7b. Both zero cost.
>
> **Rule 3: Single Supergateway, scope-based isolation.**
> One mem0-mcp instance. CLIs pass `workspace` + `project` in each request for memory isolation.
>
> **Rule 4: Workspace + Project = Memory Isolation.**
> Always set `MEM0_WORKSPACE` and `MEM0_PROJECT` to keep contexts clean.
>
> **Rule 5: Health checks are mandatory.**
> All containers have real API-level health checks. docker-compose uses `depends_on: condition: service_healthy`.
>
> **Rule 6: Volumes persist across restarts.**
> `ollama_models`, `qdrant_storage`, and `mem0_data` are permanent. Backup these volumes for disaster recovery.

---

## 7. Service Dependencies & Health Checks

| Service | Port | Depends On | Health Check | Start Period |
| :--- | :--- | :--- | :--- | :--- |
| **ollama** | 11435 | — | `curl -sf http://localhost:11434/api/tags` | 30s |
| **qdrant** | 6333 | — | `curl -sf http://localhost:6333/healthz` | 5s |
| **mem0-mcp** | 8766 | ollama, qdrant | `curl -sf http://localhost:8765/healthz` | 10s |
| **plantuml** | 8888 | — | (built-in) | — |

---

## 8. Port Mapping (localhost)

| Service | Container Port | Host Port | Protocol | Access |
| :--- | :--- | :--- | :--- | :--- |
| Ollama | 11434 | 11435 | HTTP/REST | `http://localhost:11435/api/tags` |
| Qdrant REST | 6333 | 6333 | HTTP/REST | `http://localhost:6333/healthz` |
| Qdrant gRPC | 6334 | 6334 | gRPC | — |
| Mem0 Supergateway | 8765 | 8766 | HTTP (streamableHttp) | `http://localhost:8766/mcp` |
| PlantUML (tools) | 8080 | 8888 | HTTP | `http://localhost:8888` |

---

## 9. Environment Configuration

See `.env.example` for all configuration variables.

### Ollama
```bash
OLLAMA_HOST=0.0.0.0:11434
OLLAMA_KEEP_ALIVE=-1
```

### Mem0 MCP
```bash
MEM0_WORKSPACE=copernicus
MEM0_PROJECT=default
MEM0_STORE_PATH=/root/.copilot/mem0
OLLAMA_BASE_URL=http://ollama:11434
MEM0_EMBED_MODEL=mxbai-embed-large:latest
MEM0_OLLAMA_TIMEOUT_MS=60000
MEM0_LLM_PROVIDER=ollama
MEM0_LLM_MODEL=qwen3:1.7b
MEM0_LLM_URL=http://ollama:11434
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=mem0_memories
```

---

## 10. Deployment Scenarios

### Scenario A: Docker Compose (recommended)
```bash
cp .env.example .env
docker compose -f compose/docker-compose.yml up -d
./scripts/smoke-test.sh
```

### Scenario B: Systemd User Services (Native)
```bash
sudo loginctl enable-linger $USER
systemctl --user start ollama mem0-supergateway
# Qdrant would need separate setup (docker or native binary)
```

---

## 11. Troubleshooting Quick Reference

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Supergateway crashes "Already connected to a transport" | Multiple clients on SSE mode | Use `--outputTransport streamableHttp` |
| mem0 timeout "10000ms Ollama" | Cold start or slow embeddings | Set `MEM0_OLLAMA_TIMEOUT_MS=60000` |
| Ollama high CPU | Large model + no GPU acceleration | Use `mxbai-embed-large` (670MB) not larger models |
| mem0-health reports `modelAvailable: false` | False negative (embeddings work anyway) | Verify with semantic search tool instead |
| Cannot reach mem0-mcp from host | Docker network isolation | Use `localhost:8766`, not container DNS |

---

## 12. Scaling & Future Enhancements

### Current Limits
- Single Ollama instance (embedding + extraction models)
- Single Supergateway (scope-based multi-tenancy)
- SQLite for metadata (WAL enabled, sufficient for current scale)
- Qdrant for vectors (local container, no clustering)

### Scaling Options
1. **Multiple Workspaces:** Add `MEM0_WORKSPACE=project2` scope for isolation
2. **Upgrade Extraction LLM:** Replace `qwen3:1.7b` with `qwen3:8b` or external API for better quality
3. **Enable Reranker:** Add Cohere/Jina reranker for improved search relevance
4. **Scale Qdrant:** Move to Qdrant Cloud or multi-node cluster
5. **Distributed Ollama:** Pull larger models, multi-GPU setup

---

## 13. Backup & Disaster Recovery

### Critical Artifacts
- `ollama_models` volume (model weights, 670MB+ per model)
- `qdrant_storage` volume (vector data, ~4KB per memory)
- `mem0_data` volume (SQLite metadata)
- `.env` file (configuration)

### Backup Command
```bash
tar czf mem0-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C / $(docker volume inspect mem0_data --format='{% raw %}{{.Mountpoint}}{% endraw %}') \
        $(docker volume inspect ollama_models --format='{% raw %}{{.Mountpoint}}{% endraw %}') \
        $(docker volume inspect qdrant_storage --format='{% raw %}{{.Mountpoint}}{% endraw %}')
```

### Restore Command
```bash
tar xzf mem0-backup-*.tar.gz -C /
docker compose -f compose/docker-compose.yml up -d
```

---

*Document Version: 3.0.0*
*Last Updated: 2026-04-18*
*System Target: Kali Linux 2026.1 | Docker 26+ | Node.js v22*
*Maintenance: Monitor health endpoints; backup volumes weekly; review logs for anomalies.*
