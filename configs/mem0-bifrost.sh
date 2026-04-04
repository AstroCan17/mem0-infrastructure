#!/bin/sh
# Supergateway wrapper for mem0-mcp
# Place at: ~/.bifrost/bin/mem0-bifrost
export HOME=/home/YOUR_USER
export PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export MEM0_STORE_PATH=$HOME/.copilot/mem0
export MEM0_EMBED_MODEL=mxbai-embed-large
export MEM0_OLLAMA_TIMEOUT_MS=60000
exec node /usr/local/lib/node_modules/mem0-mcp/dist/bin/mem0-mcp.js
