# Root Dockerfile - mem0chat Terminal CLI Client
# Terminal-based chat interface that connects to Mem0 MCP and Nitro inference
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY services/mem0chat-cli/requirements-mem0chat.txt .
RUN pip install --no-cache-dir -r requirements-mem0chat.txt

# Copy mem0chat application
COPY services/mem0chat-cli/mem0chat.py .

# Create user home directory for history/config
RUN mkdir -p /root/.copilot/mem0

# Python output buffering disabled for real-time logs
ENV PYTHONUNBUFFERED=1

# mem0chat connects to MCP server via HTTP
# Default: mem0 MCP at http://localhost:8765/mcp
ENV MEM0_MCP_URL=http://mem0-mcp:8765/mcp
ENV MEM0_WORKSPACE=copernicus
ENV MEM0_PROJECT=default

# Default command - connect to mem0 MCP for memory, OpenCode Zen for inference
CMD ["python3", "mem0chat.py", "--provider", "opencode-zen"]
