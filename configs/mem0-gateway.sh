#!/bin/sh
# Supergateway wrapper for mem0-mcp
# Place at: ~/.local/bin/mem0-gateway
# For remote OpenCode Zen usage, set OPENCODE_ZEN_URL and OPENCODE_ZEN_API_KEY in your shell before launching mem0chat.
export HOME="$HOME"
export PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export MEM0_STORE_PATH=$HOME/.copilot/mem0
export MEM0_EMBED_MODEL=mxbai-embed-large:latest
export MEM0_OLLAMA_TIMEOUT_MS=60000
exec /usr/local/bin/mem0-mcp
