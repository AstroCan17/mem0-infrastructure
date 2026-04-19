#!/bin/sh
# mem0-gateway wrapper script for Mem0 MCP server
# Sets environment variables and runs mem0-mcp with Ollama embeddings + Qdrant vector store
# Used by Supergateway to bridge MCP protocol to HTTP/streamableHttp

export HOME="${HOME:-/root}"
export PATH="${PATH}:/root/.local/bin:/usr/local/bin:/usr/bin:/bin"

# Ollama embedding service
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://ollama:11434}"
export MEM0_EMBED_MODEL="${MEM0_EMBED_MODEL:-mxbai-embed-large:latest}"
export MEM0_OLLAMA_TIMEOUT_MS="${MEM0_OLLAMA_TIMEOUT_MS:-60000}"

# Extraction LLM (fact extraction, not chat)
export MEM0_LLM_PROVIDER="${MEM0_LLM_PROVIDER:-ollama}"
export MEM0_LLM_MODEL="${MEM0_LLM_MODEL:-qwen3:1.7b}"
export MEM0_LLM_URL="${MEM0_LLM_URL:-http://ollama:11434}"

# Qdrant vector store
export QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
export QDRANT_COLLECTION="${QDRANT_COLLECTION:-mem0_memories}"

# Memory metadata storage
export MEM0_STORE_PATH="${MEM0_STORE_PATH:-$HOME/.copilot/mem0}"
export MEM0_WORKSPACE="${MEM0_WORKSPACE:-copernicus}"
export MEM0_PROJECT="${MEM0_PROJECT:-default}"

mkdir -p "$MEM0_STORE_PATH"

exec mem0-mcp "$@"
