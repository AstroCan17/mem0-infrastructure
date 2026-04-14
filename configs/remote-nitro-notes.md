# Remote OpenCode Zen Notes

This folder contains configuration for Mem0 services. OpenCode Zen is the project's hosted inference API.

## Key points

- Use the hosted OpenCode Zen API endpoint:
  ```bash
  export OPENCODE_ZEN_URL="https://opencode.ai/zen/v1/chat/completions"
  ```
- Set `OPENCODE_ZEN_API_KEY` with your API key, or use a GPG-encrypted file at `~/.config/opencode/zen-api-key.gpg`.
- Secure remote access with HTTPS, firewall rules, or SSH tunneling.
- This directory does not currently include a remote service manifest because OpenCode Zen is a hosted API.
