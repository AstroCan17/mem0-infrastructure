---
title: "Phase 1: Ollama behind mem0-mcp only"
nav_order: 11
---

# Phase 1: Ollama behind `mem0-mcp` only

## Policy
- Agent CLIs must **not** use Ollama directly for chat/inference.
- Ollama is used **only** as an embedding backend by `mem0-mcp-*`.

## Implementation
1. Remove `--provider ollama` and all `--ollama-*` flags from the agent CLI entrypoint (`mem0chat.py`).
2. Keep `OLLAMA_BASE_URL=http://ollama:11434` only inside `mem0-mcp-*` containers.
3. Enforce isolation via Docker networks:
   - `mem0-core`: `ollama` + `mem0-mcp-*`
   - `mem0-client`: `mem0-mcp-*` + agent CLIs

## Acceptance checks
- `mem0chat.py --help` shows no Ollama provider option.
- From an agent CLI container, `curl http://ollama:11434/...` fails (expected).
- Memory search/save still works via the per-agent `mem0-mcp-*` ports.
