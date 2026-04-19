---
layout: split-plan
title: Planning v2 — Ollama Embedding-Only Policy
diagram: diagrams/plan-v2-diagram.mermaid
---

# Plan: Ollama Embedding-Only Policy (v3 — Foundation)

## **Summary**

> **Note:** This plan has been superseded by the Foundation v3 cleanup. The original v2 plan's goals (Ollama behind mem0-mcp only, network isolation, remove Ollama chat provider) are fully achieved in the v3 architecture. This document is preserved for historical context.

### What v3 Foundation achieved:
- Agent CLIs **run on the host** (not in Docker containers) — no network isolation needed
- Ollama is used **only** for embeddings (`mxbai-embed-large`) and extraction LLM (`qwen3:1.7b`)
- `mem0chat.py` has been **completely removed** (1038 lines deleted)
- Single Supergateway instance replaces 7 separate instances
- Qdrant added as dedicated vector store (replacing SQLite for vector storage)

---

## **Current Architecture (v3)**

The only valid data path:

```
Host CLI → mem0-mcp Supergateway (port 8766) → Ollama (embed) + Qdrant (vectors) + SQLite (metadata)
```

- **Ollama** is only accessible within the Docker network (`mem0-network`)
- **Host CLIs** connect only to `http://127.0.0.1:8766/mcp`
- **No CLI container** exists that could bypass mem0-mcp to reach Ollama directly

---

## **Acceptance Criteria (all met by v3)**

| Criterion | Status |
|---|---|
| No CLI container can reach Ollama directly | PASS — no CLI containers exist |
| Ollama used only for embedding + extraction | PASS — `mxbai-embed-large` + `qwen3:1.7b` |
| Memory operations work via single endpoint | PASS — `http://127.0.0.1:8766/mcp` |
| mem0chat.py removed | PASS — `services/mem0chat-cli/` deleted |
| Nitro provider removed | PASS — no Nitro references remain |

---

## **References**
- Foundation plan: `.cursor/plans/mem0_foundation_cleanup_eac7a880.plan.md`
- Architecture: `docs/architecture/architecture-plan.md`
- Smoke test: `scripts/smoke-test.sh`
