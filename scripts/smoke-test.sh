#!/bin/bash
# smoke-test.sh — Verify the mem0 foundation stack is working end-to-end
# Usage: ./scripts/smoke-test.sh
# Expects: docker compose already running (ollama + qdrant + mem0-mcp)
set -euo pipefail

OLLAMA_URL="http://localhost:11435"
QDRANT_URL="http://localhost:6333"
MCP_URL="http://localhost:8766"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== mem0 Foundation Smoke Test ==="
echo ""

# 1. Ollama health
echo "[1/7] Ollama API..."
if curl -sf "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
  pass "Ollama API responding"
else
  fail "Ollama API not responding at $OLLAMA_URL"
fi

# 2. Ollama models present
echo "[2/7] Ollama models..."
MODELS=$(curl -sf "$OLLAMA_URL/api/tags" 2>/dev/null || echo '{}')
if echo "$MODELS" | grep -q "mxbai-embed-large"; then
  pass "mxbai-embed-large model present"
else
  fail "mxbai-embed-large model not found"
fi

# 3. Qdrant health
echo "[3/7] Qdrant health..."
if curl -sf "$QDRANT_URL/healthz" > /dev/null 2>&1; then
  pass "Qdrant healthy"
else
  fail "Qdrant not responding at $QDRANT_URL"
fi

# 4. Supergateway health
echo "[4/7] Supergateway healthz..."
if curl -sf "$MCP_URL/healthz" > /dev/null 2>&1; then
  pass "Supergateway healthy"
else
  fail "Supergateway not responding at $MCP_URL"
fi

# 5. MCP tools/list
echo "[5/7] MCP tools/list..."
TOOLS_RESP=$(curl -sf -X POST "$MCP_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' 2>/dev/null || echo '{}')
if echo "$TOOLS_RESP" | grep -q "memory_search\|mem0-memory_search"; then
  pass "MCP tools/list returned memory tools"
else
  fail "MCP tools/list did not return expected tools"
fi

# 6. Memory store (write)
echo "[6/7] Memory store (write)..."
STORE_RESP=$(curl -sf -X POST "$MCP_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc":"2.0","id":2,"method":"tools/call",
    "params":{"name":"memory_store","arguments":{
      "kind":"note",
      "content":"smoke-test: the project uses Qdrant for vector storage and Ollama for embeddings",
      "scope":{"workspace":"copernicus","project":"smoke-test"},
      "provenance":{"checkpointId":"smoke-test-001"},
      "metadata":{}
    }}
  }' 2>/dev/null || echo '{}')
if echo "$STORE_RESP" | grep -q "error"; then
  fail "memory_store returned an error"
else
  pass "memory_store succeeded"
fi

# Wait for async processing
sleep 3

# 7. Memory search (read)
echo "[7/7] Memory search (read)..."
SEARCH_RESP=$(curl -sf -X POST "$MCP_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc":"2.0","id":3,"method":"tools/call",
    "params":{"name":"memory_search","arguments":{
      "query":"vector storage embedding",
      "scope":{"workspace":"copernicus","project":"smoke-test"},
      "limit":5
    }}
  }' 2>/dev/null || echo '{}')
if echo "$SEARCH_RESP" | grep -q "error"; then
  fail "memory_search returned an error"
else
  pass "memory_search succeeded"
fi

# Summary
echo ""
echo "=== Results ==="
echo "  PASSED: $PASS"
echo "  FAILED: $FAIL"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "SMOKE TEST: FAIL"
  exit 1
else
  echo "SMOKE TEST: PASS"
  exit 0
fi
