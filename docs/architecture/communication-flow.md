---
title: Communication flow
nav_order: 20
---

# Communication flow

## Components
- **Agent CLIs**: interactive clients (mem0chat/codex/claude/gemini/opencode/copilot/docker-ai).
- **Supergateway (`mem0-mcp-*`)**: HTTP bridge for MCP over `streamableHttp`.
- **`mem0-mcp`**: memory service that reads/writes the persistent store.
- **Ollama**: embedding service (`mxbai-embed-large:latest`).
- **Persistent store**: shared Docker volume mounted at `/root/.copilot/mem0`.

## Query → response (memory-assisted)
1. User sends a prompt to a selected agent CLI container.
2. The CLI calls its dedicated MCP HTTP endpoint: `http://mem0-mcp-<agent>:8765/mcp` (container network).
3. `mem0-mcp-<agent>` requests embeddings from `ollama:11434` and performs vector search against the shared store.
4. The CLI builds the final LLM prompt using the retrieved memories.
5. The CLI sends the request to the chosen inference provider (OpenAI/Codex/Claude/Gemini/OpenCode/Copilot, etc.).

## Memory save
1. The CLI sends a standardized memory-save payload to `mem0-mcp-<agent>:8765/mcp`.
2. `mem0-mcp` persists it into the shared store and, when required, calls Ollama to compute embeddings.
