#!/bin/sh
# mem0-gateway wrapper script for Mem0 MCP server
# Sets environment variables and runs mem0-mcp with Ollama embeddings
# Used by Supergateway to bridge MCP protocol to HTTP/streamableHttp

export HOME="${HOME:-/root}"
export PATH="${PATH}:/root/.local/bin:/usr/local/bin:/usr/bin:/bin"

# Ollama embedding service configuration
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://ollama:11434}"
export MEM0_EMBED_MODEL="${MEM0_EMBED_MODEL:-mxbai-embed-large:latest}"
export MEM0_OLLAMA_TIMEOUT_MS="${MEM0_OLLAMA_TIMEOUT_MS:-60000}"

# Memory storage configuration
export MEM0_STORE_PATH="${MEM0_STORE_PATH:-$HOME/.copilot/mem0}"
export MEM0_WORKSPACE="${MEM0_WORKSPACE:-copernicus}"
export MEM0_PROJECT="${MEM0_PROJECT:-default}"

# Ensure mem0 storage directory exists
mkdir -p "$MEM0_STORE_PATH"

# Execute mem0-mcp server
exec mem0-mcp "$@"
