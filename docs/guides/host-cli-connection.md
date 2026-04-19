---
title: Host CLI Connection Guide
---

# Host CLI Connection Guide

All agent CLIs run on the host machine and connect to the mem0-mcp Supergateway at `http://127.0.0.1:8766/mcp` via streamableHttp.

## Prerequisites

Ensure the Docker stack is running:

```bash
docker compose -f compose/docker-compose.yml up -d
curl -sf http://localhost:8766/healthz && echo "mem0-mcp ready"
```

---

## Cursor IDE

Add to `.cursor/mcp.json` in your project root (or global `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "mem0": {
      "url": "http://127.0.0.1:8766/mcp",
      "transport": "streamableHttp"
    }
  }
}
```

Cursor will auto-detect the MCP server on next startup. Memory operations are available as tools in Agent mode.

---

## VS Code Copilot

Add to `~/.copilot/mcp-config.json`:

```json
{
  "mcpServers": {
    "mem0": {
      "tools": ["*"],
      "url": "http://127.0.0.1:8766/mcp",
      "transport": "streamableHttp"
    }
  }
}
```

Restart Copilot CLI or VS Code after editing.

---

## Claude Code CLI

Add to `~/.claude/mcp_servers.json` (or use `claude mcp add`):

```json
{
  "mem0": {
    "type": "streamableHttp",
    "url": "http://127.0.0.1:8766/mcp"
  }
}
```

Or via CLI:

```bash
claude mcp add mem0 --transport streamableHttp --url http://127.0.0.1:8766/mcp
```

---

## OpenCode CLI

OpenCode uses Nemotron (free) for chat inference. Memory access is via MCP configuration.

Add to your OpenCode MCP config:

```json
{
  "mcpServers": {
    "mem0": {
      "url": "http://127.0.0.1:8766/mcp",
      "transport": "streamableHttp"
    }
  }
}
```

---

## Blackbox Pro CLI

Blackbox Pro uses its own model for chat inference. Memory access is via MCP configuration.

Add to your Blackbox MCP config:

```json
{
  "mcpServers": {
    "mem0": {
      "url": "http://127.0.0.1:8766/mcp",
      "transport": "streamableHttp"
    }
  }
}
```

---

## Memory Scoping

Each CLI should pass `workspace` and `project` parameters in memory operations to isolate contexts:

```json
{
  "scope": {
    "workspace": "copernicus",
    "project": "my-project"
  }
}
```

All CLIs share the same memory store. Use different `project` values to separate per-project memories, or the same `project` to share context across CLIs working on the same codebase.

---

## Verification

After configuring any CLI, verify the connection:

```bash
curl -sf -X POST http://127.0.0.1:8766/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -c 200
```

You should see a JSON response listing available memory tools (`memory_store`, `memory_search`, etc.).

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Connection refused on port 8766 | Ensure Docker stack is running: `docker compose -f compose/docker-compose.yml up -d` |
| "Already connected to a transport" | Use `streamableHttp` transport, NOT SSE |
| Timeout errors | Check Ollama health: `curl http://localhost:11435/api/tags` |
| No memory results | Verify scope (workspace/project) matches between store and search |
