#!/bin/bash
set -e

# Start Ollama in background
/bin/ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
sleep 5
for i in {1..30}; do
  if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Ollama is ready"
    break
  fi
  echo "Waiting for Ollama... ($i/30)"
  sleep 2
done

# Pull embedding model
echo "Pulling mxbai-embed-large model..."
ollama pull mxbai-embed-large:latest

echo "Model downloaded. Ollama ready!"

# Keep process running
wait $OLLAMA_PID
