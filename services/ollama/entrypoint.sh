#!/bin/bash
set -e

/bin/ollama serve &
OLLAMA_PID=$!

for i in {1..30}; do
  if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Ollama is ready"
    break
  fi
  echo "Waiting for Ollama... ($i/30)"
  sleep 2
done

echo "Pulling embedding model (mxbai-embed-large)..."
ollama pull mxbai-embed-large:latest

echo "Pulling extraction LLM (qwen3:1.7b)..."
ollama pull qwen3:1.7b

echo "All models downloaded. Ollama ready!"

wait $OLLAMA_PID
