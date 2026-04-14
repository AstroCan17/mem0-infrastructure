FROM ollama/ollama:latest

# Copy entrypoint script
COPY services/ollama/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Model will be pulled at runtime by the entrypoint script

ENTRYPOINT ["/entrypoint.sh"]
