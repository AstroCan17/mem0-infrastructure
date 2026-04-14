# Plan: Disable Ollama Provider in Agent CLIs and Put Ollama Behind `mem0-mcp` Only (English Docs)

## **Summary**
- Agent CLI containers will **not** use Ollama for chat/inference (`--provider ollama` removed entirely).
- Ollama will be used **only** as an embedding backend by `mem0-mcp-*` (Supergateway + `mem0-mcp`) services.
- Enforcement will be **two-layered**: (1) remove the provider from `mem0chat.py`, and (2) block direct network access from agent CLIs to the `ollama` service via Docker networks.
- All documentation/architecture notes/diagrams will be updated to **English only** (including converting existing Turkish sections).

---

## **Key Changes**

### 1) Remove Ollama provider from `mem0chat` (code-level enforcement)
**Goal:** There is no `--provider ollama` or any `--ollama-*` flags in `mem0chat.py`.

- Update `mem0chat/mem0chat.py`
  - Remove `ollama` from `--provider` choices.
  - Remove `--ollama-url` and `--ollama-model` arguments.
  - Remove the `elif args.provider == "ollama": ...` branch and the `_ollama_stream_response(...)` implementation.
  - Fix Nitro model selection (currently coupled to `--ollama-model`):
    - Add `--nitro-model` (env: `NITRO_MODEL`, default: `llama3`).
    - Use `args.nitro_model` when `--provider nitro`.
- Update `mem0chat/requirements-mem0chat.txt`
  - Remove the Python `ollama` dependency if it becomes unused after provider removal.

**Result:** No container (including agent CLIs) can accidentally run local Ollama chat via `mem0chat.py`.

---

### 2) Docker network isolation: prevent agent CLIs from reaching `ollama` directly (network-level enforcement)
**Goal:** Agent CLI containers cannot resolve/connect to `ollama:11434`, but `mem0-mcp-*` can.

- Update `docker-compose.yml`
  - Create two networks:
    - `mem0-core`: `ollama` + all `mem0-mcp-*` services
    - `mem0-client`: all `mem0-mcp-*` services + agent CLI containers (+ optionally `code-sandbox`)
  - Attach `ollama` **only** to `mem0-core`.
  - Attach each `mem0-mcp-*` to **both** networks (bridge role).
  - Attach agent CLI services **only** to `mem0-client`.
  - Keep `mem0-mcp-*` env: `OLLAMA_BASE_URL=http://ollama:11434` (works via `mem0-core`).
  - Remove any `OLLAMA_BASE_URL` env from agent CLIs (not needed anymore).

**Result:** The only valid path is `CLI → mem0-mcp-* → (Ollama embed + shared DB)`.

---

### 3) Update documentation and diagrams to English-only
**Goal:** No Turkish text remains in architecture docs/notes; everything reflects the new constraint “Ollama behind mem0-mcp only”.

- Update `ARCHITECTURE_PLAN.md`
  - Rewrite “Communication Flow” in English:
    - Memory search/save: `Agent CLI → Supergateway (per-agent) → mem0-mcp → Ollama(embed) + shared mem0_data DB`
    - Inference path: agent provider APIs only (OpenAI/Codex/Claude/Gemini/OpenCode/Copilot etc.), not Ollama
  - Add an explicit policy statement: “Agent CLIs must not access Ollama directly.”
  - Convert any justification sections to English (performance/token/persistence).
- Update `SETUP.md`
  - English-only steps and health checks.
  - Add a quick verification: “From agent CLI, `curl http://ollama:11434` should fail (expected).”
- Update diagrams:
  - `project_notes/docker_workflow*.puml` and `project_notes/docker_workflow.mermaid` to show Ollama only behind `mem0-mcp-*`.

---

## **Test Plan / Acceptance Criteria**

### A) CLI behavior
- `python3 mem0chat/mem0chat.py --help`:
  - `--provider` does **not** list `ollama`
  - no `--ollama-url` / `--ollama-model`
- Running with `--provider ollama` fails at argparse with “invalid choice”.

### B) Network isolation
- Inside an agent CLI container:
  - `curl http://ollama:11434/api/tags` fails (DNS or connection error) — **expected**
- From `mem0-mcp-*` container:
  - embeddings still work (Ollama reachable via `mem0-core`)
- Memory operations via `http://localhost:8766/…` (or per-agent ports) still succeed.

### C) Regression checks
- Save a memory via an agent CLI → search returns it later (same scope).
- `code-sandbox` direct Ollama access remains available (per your preference).

---

## **Assumptions / Defaults**
- Scope decision: **remove Ollama provider entirely** (not just “disable in agent CLIs”).
- Network decision: **enforce isolation** using separate Docker networks (`mem0-core` / `mem0-client`).
- `code-sandbox` is allowed to keep direct Ollama access.
- Nitro needs a new explicit model flag (`--nitro-model`) to replace the removed Ollama model argument.
