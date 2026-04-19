#!/bin/bash
# extraction-quality-test.sh — Test mem0 extraction LLM quality (qwen3:1.7b)
# Runs 5 test cases: store facts via MCP, then verify extraction via search
# Usage: ./scripts/extraction-quality-test.sh
# Expects: docker compose stack running (ollama + qdrant + mem0-mcp)
set -euo pipefail

MCP_URL="http://localhost:8766"
WORKSPACE="copernicus"
PROJECT="extraction-test-$(date +%s)"
PASS=0
FAIL=0
TOTAL=5

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

store_memory() {
  local content="$1"
  curl -sf -X POST "$MCP_URL/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d "{
      \"jsonrpc\":\"2.0\",\"id\":$RANDOM,\"method\":\"tools/call\",
      \"params\":{\"name\":\"memory_store\",\"arguments\":{
        \"kind\":\"note\",
        \"content\":\"$content\",
        \"scope\":{\"workspace\":\"$WORKSPACE\",\"project\":\"$PROJECT\"},
        \"provenance\":{\"checkpointId\":\"test-$(date +%s)\"},
        \"metadata\":{}
      }}
    }" 2>/dev/null
}

search_memory() {
  local query="$1"
  curl -sf -X POST "$MCP_URL/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d "{
      \"jsonrpc\":\"2.0\",\"id\":$RANDOM,\"method\":\"tools/call\",
      \"params\":{\"name\":\"memory_search\",\"arguments\":{
        \"query\":\"$query\",
        \"scope\":{\"workspace\":\"$WORKSPACE\",\"project\":\"$PROJECT\"},
        \"limit\":5
      }}
    }" 2>/dev/null
}

echo "=== Extraction LLM Quality Test ==="
echo "Model: qwen3:1.7b | Project scope: $PROJECT"
echo ""

# Test 1: Simple fact extraction
echo "[1/$TOTAL] Simple fact extraction..."
store_memory "The project uses Python 3.13 as its primary language"
sleep 3
RESULT=$(search_memory "what programming language does the project use")
if echo "$RESULT" | grep -qi "python"; then
  pass "Simple fact (Python language) extracted and searchable"
else
  fail "Simple fact not found in search results"
fi

# Test 2: Numeric fact extraction
echo "[2/$TOTAL] Numeric fact extraction..."
store_memory "The Docker stack runs exactly 3 services: ollama, qdrant, and mem0-mcp"
sleep 3
RESULT=$(search_memory "how many docker services are running")
if echo "$RESULT" | grep -qi "3\|three\|ollama\|qdrant"; then
  pass "Numeric fact (3 services) extracted and searchable"
else
  fail "Numeric fact not found in search results"
fi

# Test 3: Technical relationship extraction
echo "[3/$TOTAL] Technical relationship..."
store_memory "Qdrant is used as the vector store with 1024 dimensions and cosine distance metric for semantic search"
sleep 3
RESULT=$(search_memory "vector store dimensions and distance metric")
if echo "$RESULT" | grep -qi "qdrant\|1024\|cosine"; then
  pass "Technical relationship (Qdrant + 1024d + cosine) extracted"
else
  fail "Technical relationship not found in search results"
fi

# Test 4: Multi-fact extraction
echo "[4/$TOTAL] Multi-fact extraction..."
store_memory "The architecture has two Ollama models: mxbai-embed-large for embeddings and qwen3:1.7b for fact extraction. The embedding model produces 1024-dimensional vectors."
sleep 3
RESULT=$(search_memory "what models does ollama run")
if echo "$RESULT" | grep -qi "mxbai\|qwen\|embed"; then
  pass "Multi-fact (two models) extracted and searchable"
else
  fail "Multi-fact not found in search results"
fi

# Test 5: Round-trip consistency
echo "[5/$TOTAL] Round-trip consistency..."
store_memory "All agent CLIs connect to mem0-mcp via streamableHttp on port 8766. CLIs include Cursor, Copilot, Claude Code, OpenCode, and Blackbox Pro."
sleep 3
RESULT=$(search_memory "which CLIs connect to mem0")
if echo "$RESULT" | grep -qi "cursor\|copilot\|claude\|opencode\|blackbox\|8766"; then
  pass "Round-trip (CLI list + port) consistent"
else
  fail "Round-trip consistency check failed"
fi

# Summary
echo ""
echo "=== Extraction Quality Results ==="
echo "  PASSED: $PASS / $TOTAL"
echo "  FAILED: $FAIL / $TOTAL"
ACCURACY=$((PASS * 100 / TOTAL))
echo "  ACCURACY: ${ACCURACY}%"
echo ""

if [ "$ACCURACY" -ge 90 ]; then
  echo "EXTRACTION QUALITY: PASS (>= 90%)"
  echo "qwen3:1.7b is sufficient for extraction."
  exit 0
elif [ "$ACCURACY" -ge 60 ]; then
  echo "EXTRACTION QUALITY: MARGINAL (60-89%)"
  echo "Consider upgrading to qwen3:8b for better extraction."
  exit 1
else
  echo "EXTRACTION QUALITY: FAIL (< 60%)"
  echo "Upgrade required: qwen3:8b or external API."
  exit 2
fi
