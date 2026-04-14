# Dockerfile for Mem0 Chat MCP Service
# Node.js service providing memory storage and MCP bridging via supergateway
# Port: 8765 (MCP via streamableHttp)
FROM node:20-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install supergateway and mem0 CLI with dependencies
RUN npm install -g supergateway @mem0/cli mem0-mcp

# Create app directories
RUN mkdir -p /app /root/.copilot/mem0 /root/.local/bin

# Copy mem0-gateway script
COPY services/mem0-mcp/mem0-gateway.sh /root/.local/bin/mem0-gateway
RUN chmod +x /root/.local/bin/mem0-gateway

# Copy config file
COPY configs/mcp-config.json /root/.copilot/mcp-config.json

# Port for MCP gateway
EXPOSE 8765

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=10s \
  CMD curl -f http://localhost:8765/healthz || exit 1

# Start supergateway with mem0-gateway
CMD ["sh", "-c", "supergateway --stdio /root/.local/bin/mem0-gateway --outputTransport streamableHttp --port 8765 --streamableHttpPath /mcp --healthEndpoint /healthz --logLevel info"]
