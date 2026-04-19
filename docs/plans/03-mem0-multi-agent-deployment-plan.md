### **Technical System Specification & Deployment Plan: Mem0 Multi-Agent Infrastructure**

This document serves as a machine-readable technical specification for the deployment and orchestration of a Mem0-based multi-agent system. It is designed to guide autonomous agents in configuring the infrastructure, enforcing network policies, and optimizing token consumption through **Dynamic Context Pruning**.

---

#### **1. Core System Policy & Architecture**
*   **Centralized Isolation:** Agent CLIs are strictly prohibited from accessing the **Ollama** service directly for chat or inference.
*   **Ollama Role:** Ollama functions exclusively as an embedding backend for the `mem0-mcp-*` (Supergateway) services.
*   **Orchestration Logic:** A lead **Inference Agent CLI** acts as the "Team Lead," coordinating specialized worker agents (Gemini, Codex, OpenCode) and managing the "Shared Brain" via Mem0 REST API.

#### **2. Infrastructure Setup (Dockerized Environment)**
The system must be deployed using **Docker Compose** to ensure modularity and network-level enforcement.

*   **Repository:** Clone Mem0 Open Source (OSS) for full infrastructure control.
    *   *Reference:* [Mem0 OSS GitHub](https://github.com/mem0ai/mem0)
*   **Network Topology:**
    *   `mem0-core`: Includes `ollama` and `mem0-mcp-*`. Only `mem0-mcp-*` can reach the Ollama API.
    *   `mem0-client`: Includes `mem0-mcp-*` and all **Agent CLIs**. Agents reach memory via `mem0-mcp` but cannot resolve the `ollama` hostname.

#### **3. Memory & Vector Configuration**
The system uses a hybrid cloud-local configuration via `Memory.from_config`.

| Component | Provider / Model | Cost / Tier |
| :--- | :--- | :--- |
| **Vector Store** | [Qdrant Cloud](https://qdrant.tech/) | Free Tier Cluster |
| **Embedder** | [OpenAI `text-embedding-3-small`](https://platform.openai.com/docs/guides/embeddings) | $0.02 / 1M tokens |
| **Reranker** | `zerank-2` | $0.02 / 1M tokens (Optional) |

#### **4. Multi-Agent Team Orchestration**
*   **Lead Agent:** Coordinates work, assigns tasks, and synthesizes results.
*   **Worker Agents:**
    *   **External APIs:** High-reasoning tasks (Gemini, Codex).
    *   **OpenCode Models:** Routed for simple, free inference to reduce costs.
    *   **Local Worker (Ollama):** Used via the Lead Agent for local summarization and data cleaning before external API calls.
*   **Communication:** Agents use a shared task list and mailbox for inter-agent messaging.

#### **5. Token Optimization: Dynamic Context Pruning**
To ensure an economic system, the **Inference Agent CLI** must execute the following "Inference Path":
1.  **Retrieve:** Fetch semantic memories from `mem0-mcp`.
2.  **Filter:** Apply a relevance threshold to raw memory results.
3.  **Prune/Summarize:** Use a local Ollama model or internal logic to summarize long contexts into a compressed format.
4.  **Execute:** Send the optimized prompt to the external LLM provider.

#### **6. Technical References**
*   **Mem0 Documentation:** [https://docs.mem0.ai/open-source/overview](https://docs.mem0.ai/open-source/overview)
*   **Claude Agent Teams (Architecture Inspiration):** [https://code.claude.com/docs/en/agent-teams](https://code.claude.com/docs/en/agent-teams)
*   **PlantUML/C4 Documentation:** [https://plantuml.com/guide](https://plantuml.com/guide)

---

### **System Acceptance Checklist**
- [ ] `mem0chat.py --help` shows no `--provider ollama` option.
- [ ] `curl http://ollama:11434` fails from inside an Agent CLI container.
- [ ] Memory operations succeed via `mem0-mcp` ports (e.g., `8766`).
- [ ] External inference routes to OpenCode/Gemini with pruned context.