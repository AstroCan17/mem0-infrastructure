---
title: "Phase 0: Repo cleanup + GitHub Pages"
nav_order: 10
---

# Phase 0: Repo cleanup + GitHub Pages

## Goals
- Standardize the repository layout for CI/CD.
- Ensure no private code is pushed (exclude `hummusapiens/`).
- Provide a stable default Docker Compose stack that builds in CI.
- Publish plans and architecture docs via GitHub Pages (from `/docs`).

## Deliverables
- New folder layout: `compose/`, `services/`, `scripts/`, `docs/`.
- Default stack: `ollama` + `mem0-mcp` + `mem0-mcp-*` (no `code-sandbox`).
- CI workflow that validates `docker compose` and blocks tracked `hummusapiens/`.
- Jekyll configuration under `docs/` using `just-the-docs`.

## Manual GitHub step (one-time)
In GitHub repo settings:
- **Settings → Pages → Build and deployment**
- Source: **Deploy from a branch**
- Branch: `main`
- Folder: `/docs`
