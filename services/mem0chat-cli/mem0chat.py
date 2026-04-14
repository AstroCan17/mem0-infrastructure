#!/usr/bin/env python3
"""
mem0chat: terminal chat client that integrates:
- mem0 via Supergateway MCP (HTTP + SSE) for long-term per-project memory
- OpenAI for chat responses (streaming)
- NotebookLM via `nlm` CLI for source-grounded workflows

This repo's mem0 stack typically runs:
  Supergateway: http://127.0.0.1:8765/mcp  (SSE responses)
  Health:       http://127.0.0.1:8765/healthz
  Store:        ~/.copilot/mem0/memories.sqlite
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import textwrap
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text


DEFAULT_MEM0_MCP_URL = os.environ.get("MEM0_MCP_URL", "http://mem0-mcp:8765/mcp")
DEFAULT_MEM0_HEALTHZ_URL = os.environ.get("MEM0_HEALTHZ_URL", "http://mem0-mcp:8765/healthz")
DEFAULT_MEM0_DB = os.environ.get(
    "MEM0_DB_PATH", os.path.expanduser("~/.copilot/mem0/memories.sqlite")
)

DEFAULT_WORKSPACE = os.environ.get("MEM0_SCOPE_WORKSPACE", "copernicus")
DEFAULT_SEARCH_LIMIT = int(os.environ.get("MEM0_SEARCH_LIMIT", "5"))

DEFAULT_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
DEFAULT_OLLAMA_CHAT_MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "llama3")

DEFAULT_NITRO_URL = os.environ.get("NITRO_URL", "http://nitro:3928/v1")
DEFAULT_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")

DEFAULT_OPENCODE_ZEN_URL = os.environ.get("OPENCODE_ZEN_URL", "https://api.opencode.ai/v1")
DEFAULT_OPENCODE_ZEN_MODEL = os.environ.get("OPENCODE_ZEN_MODEL", "opencode/big-pickle")
DEFAULT_OPENCODE_ZEN_KEY_FILE = os.environ.get("OPENCODE_ZEN_KEY_FILE", os.path.expanduser("~/.config/opencode/zen-api-key.gpg"))


def _decrypt_gpg(file_path: str) -> Optional[str]:
    """Decrypt GPG-encrypted file and return contents."""
    if not os.path.exists(file_path):
        return None
    try:
        result = subprocess.run(
            ["gpg", "--decrypt", "--batch", "--yes", file_path],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


console = Console()


def _now_iso() -> str:
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _run(cmd: List[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _in_git_repo(cwd: str) -> bool:
    try:
        _run(["git", "-C", cwd, "rev-parse", "--is-inside-work-tree"])
        return True
    except Exception:
        return False


def _git_root_basename(cwd: str) -> Optional[str]:
    try:
        p = _run(["git", "-C", cwd, "rev-parse", "--show-toplevel"]).stdout.strip()
        if not p:
            return None
        return os.path.basename(p)
    except Exception:
        return None


def _default_project(cwd: str) -> str:
    n = _git_root_basename(cwd)
    if n:
        return n
    return os.path.basename(os.path.abspath(cwd))


def _safe_alias_component(s: str) -> str:
    # Keep aliases predictable for `nlm alias set`.
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "unknown"


def _make_nlm_alias(workspace: str, project: str) -> str:
    return f"ws-{_safe_alias_component(workspace)}--prj-{_safe_alias_component(project)}"


@dataclass
class Scope:
    workspace: str
    project: str
    campaign: Optional[str] = None
    task: Optional[str] = None
    run: Optional[str] = None

    def to_dict(self) -> Dict[str, str]:
        d: Dict[str, str] = {"workspace": self.workspace, "project": self.project}
        if self.campaign:
            d["campaign"] = self.campaign
        if self.task:
            d["task"] = self.task
        if self.run:
            d["run"] = self.run
        return d


class Mem0McpClient:
    def __init__(self, url: str, healthz_url: str, timeout_s: float = 30.0):
        self._url = url
        self._healthz_url = healthz_url
        self._timeout = timeout_s
        self._client = httpx.Client(timeout=self._timeout)
        self._next_id = 1
        self._tool_map: Dict[str, str] = {}

    def close(self) -> None:
        self._client.close()

    def healthz(self) -> bool:
        try:
            r = self._client.get(self._healthz_url)
            return r.status_code == 200 and r.text.strip() == "ok"
        except Exception:
            return False

    def _rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        rid = self._next_id
        self._next_id += 1

        headers = {
            "Content-Type": "application/json",
            # Supergateway requires Accept to include both.
            "Accept": "application/json, text/event-stream",
        }
        payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        try:
            r = self._client.post(self._url, headers=headers, json=payload)
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"RPC request failed: {e}")

        ctype = (r.headers.get("content-type") or "").lower()
        if "text/event-stream" not in ctype:
            # Some deployments may return JSON directly.
            return r.json()

        # SSE: parse first data: line containing JSON (robust for incomplete responses)
        data_json: Optional[Dict[str, Any]] = None
        try:
            for line in r.text.splitlines():
                if not line.startswith("data:"):
                    continue
                raw = line[len("data:") :].strip()
                if not raw:
                    continue
                try:
                    data_json = json.loads(raw)
                    break
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass
        
        if not data_json:
            raise RuntimeError("Failed to parse SSE response from Supergateway (incomplete or malformed)")
        return data_json

    def tools_list(self) -> List[Dict[str, Any]]:
        resp = self._rpc("tools/list", {})
        if resp.get("error"):
            raise RuntimeError(f"tools/list failed: {resp['error']}")
        return resp.get("result", {}).get("tools", []) or []

    def refresh_tool_map(self) -> None:
        tools = self.tools_list()
        names = {t.get("name") for t in tools}

        def pick(*candidates: str) -> Optional[str]:
            for c in candidates:
                if c in names:
                    return c
            return None

        # Older docs used mem0-* prefix; newer mem0-mcp exposes plain names.
        health = pick("health", "mem0-health")
        search = pick("memory_search", "mem0-memory_search")
        store = pick("memory_store", "mem0-memory_store")
        recall = pick("memory_recall", "mem0-memory_recall")
        forget = pick("memory_forget", "mem0-memory_forget")
        update = pick("memory_update", "mem0-memory_update")

        m: Dict[str, str] = {}
        if health:
            m["health"] = health
        if search:
            m["memory_search"] = search
        if store:
            m["memory_store"] = store
        if recall:
            m["memory_recall"] = recall
        if forget:
            m["memory_forget"] = forget
        if update:
            m["memory_update"] = update
        self._tool_map = m

    def tool_call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        real = self._tool_map.get(name, name)
        resp = self._rpc("tools/call", {"name": real, "arguments": arguments})
        if resp.get("error"):
            raise RuntimeError(f"tools/call {real} failed: {resp['error']}")
        return resp.get("result", {}) or {}

    def health(self) -> Dict[str, Any]:
        return self.tool_call("health", {})

    def memory_search(self, scope: Scope, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> Dict[str, Any]:
        return self.tool_call(
            "memory_search",
            {"query": query, "scope": scope.to_dict(), "limit": int(limit)},
        )

    def memory_store(
        self,
        scope: Scope,
        kind: str,
        content: str,
        checkpoint_id: str,
        metadata: Optional[Dict[str, str]] = None,
        provenance_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        prov: Dict[str, Any] = {"checkpointId": checkpoint_id}
        if provenance_note:
            prov["note"] = provenance_note
        args: Dict[str, Any] = {
            "kind": kind,
            "content": content,
            "scope": scope.to_dict(),
            "provenance": prov,
            "metadata": metadata or {},
        }
        return self.tool_call("memory_store", args)


def _extract_structured_content(tool_result: Dict[str, Any]) -> Any:
    # mem0-mcp returns {content:[...], structuredContent:{...}, isError:false}
    if isinstance(tool_result, dict) and "structuredContent" in tool_result:
        return tool_result.get("structuredContent")
    return tool_result


def _format_mem0_results(structured: Any) -> str:
    if not structured or not isinstance(structured, dict):
        return ""
    results = structured.get("results")
    if not results:
        return ""
    lines = ["Memory Context (mem0):"]
    for r in results:
        if not isinstance(r, dict):
            continue
        mid = r.get("memoryId") or r.get("id") or ""
        kind = r.get("kind") or ""
        score = r.get("score")
        content = r.get("content") or ""
        content = content.strip().replace("\n", " ")
        if len(content) > 280:
            content = content[:277] + "..."
        s = f"- [{kind}] {content}"
        if mid:
            s += f" (id={mid})"
        if score is not None:
            s += f" (score={score})"
        lines.append(s)
    return "\n".join(lines).strip()


def _openai_stream_response(model: str, system: str, user: str) -> str:
    # Import lazily so non-OpenAI commands still work without the dependency.
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError(f"OpenAI SDK not available: {e}")

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI()
    full_text: List[str] = []

    # Prefer the streaming helper when available.
    try:
        stream = client.responses.stream(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        with stream as s:
            for event in s:
                # SDK event types can vary by version; handle the common ones.
                et = getattr(event, "type", None) or event.get("type")  # type: ignore[attr-defined]
                if et in ("response.output_text.delta", "response.output_text.delta_event"):
                    delta = getattr(event, "delta", None) or event.get("delta", "")  # type: ignore[attr-defined]
                    if delta:
                        full_text.append(delta)
                        console.print(delta, end="")
                elif et in ("response.completed", "response.done"):
                    break
        console.print()
        return "".join(full_text)
    except Exception:
        # Fallback: create(stream=True) if present in installed SDK.
        resp_iter = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
        )
        for ev in resp_iter:
            t = ev.get("type")
            if t == "response.output_text.delta":
                delta = ev.get("delta", "")
                if delta:
                    full_text.append(delta)
                    console.print(delta, end="")
            elif t in ("response.completed", "response.done"):
                break
        console.print()
        return "".join(full_text)


def _nitro_stream_response(base_url: str, model: str, system: str, user: str, api_key: str = "nitro-local") -> str:
    """Stream chat output from Nitro's OpenAI-compatible API."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("Nitro desteği için 'pip install openai' gereklidir.")

    # Nitro veya harici sağlayıcı (OpenRouter vb.) için API anahtarı kullan
    client = OpenAI(base_url=base_url, api_key=api_key)
    full_text: List[str] = []

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
        )
        for chunk in response:
            if chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                full_text.append(delta)
                console.print(delta, end="")
        console.print()
        return "".join(full_text)
    except Exception as e:
        raise RuntimeError(f"Nitro request failed: {e}")


def _opencode_zen_stream_response(base_url: str, model: str, system: str, user: str, api_key: str) -> str:
    """Stream chat output from OpenCode Zen API."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("OpenAI SDK required: pip install openai")

    if not api_key:
        raise RuntimeError("OPENCODE_ZEN_API_KEY is not set")

    client = OpenAI(base_url=base_url, api_key=api_key)
    full_text: List[str] = []

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
        )
        for chunk in response:
            if chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                full_text.append(delta)
                console.print(delta, end="")
        console.print()
        return "".join(full_text)
    except Exception as e:
        raise RuntimeError(f"OpenCode Zen request failed (base_url={base_url}, model={model}): {e}")


def _ollama_stream_response(base_url: str, model: str, system: str, user: str) -> str:
    """
    Stream chat output from Ollama's HTTP API.

    Uses /api/chat with stream=true, parsing one JSON object per line.
    """
    url = base_url.rstrip("/") + "/api/chat"
    full_text: List[str] = []

    payload: Dict[str, Any] = {
        "model": model,
        "stream": True,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    with httpx.Client(timeout=None) as c:
        try:
            with c.stream("POST", url, json=payload) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = (ev.get("message") or {}) if isinstance(ev, dict) else {}
                    delta = msg.get("content") if isinstance(msg, dict) else None
                    if isinstance(delta, str) and delta:
                        full_text.append(delta)
                        console.print(delta, end="")
                    if ev.get("done") is True:
                        break
        except httpx.HTTPStatusError as e:
            # Common cause: model not pulled.
            raise RuntimeError(
                f"Ollama chat failed ({e.response.status_code}). "
                f"Try: ollama pull {model} or set OLLAMA_CHAT_MODEL."
            ) from e
        except httpx.ConnectError as e:
            raise RuntimeError(
                f"Cannot connect to Ollama at {base_url}. Is it running on ollama:11434?"
            ) from e

    console.print()
    return "".join(full_text)


def _db_iter_memories(db_path: str) -> Iterable[Tuple[str, str, str, str, str, str]]:
    # id, kind, scope, metadata, content, created_at
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute(
            "SELECT id, kind, scope, metadata, content, created_at FROM memories ORDER BY created_at DESC"
        )
        for row in cur.fetchall():
            yield tuple(row)  # type: ignore[misc]
    finally:
        con.close()


def _projects_in_workspace(db_path: str, workspace: str) -> List[str]:
    projects: set[str] = set()
    for _id, _kind, scope_s, _meta_s, _content, _created in _db_iter_memories(db_path):
        try:
            scope = json.loads(scope_s)
        except Exception:
            continue
        if not isinstance(scope, dict):
            continue
        if scope.get("workspace") != workspace:
            continue
        p = scope.get("project")
        if isinstance(p, str) and p:
            projects.add(p)
    return sorted(projects)


def _find_latest_notebooklm_mapping(
    db_path: str, scope: Scope
) -> Optional[Dict[str, str]]:
    target = scope.to_dict()
    for _id, kind, scope_s, meta_s, _content, _created in _db_iter_memories(db_path):
        if kind != "artifact_context":
            continue
        try:
            s = json.loads(scope_s)
            m = json.loads(meta_s) if meta_s else {}
        except Exception:
            continue
        if not isinstance(s, dict) or not isinstance(m, dict):
            continue
        if s.get("workspace") != target.get("workspace") or s.get("project") != target.get("project"):
            continue
        nbid = m.get("notebooklm_notebook_id")
        alias = m.get("notebooklm_alias")
        if isinstance(nbid, str) and nbid:
            out: Dict[str, str] = {"notebooklm_notebook_id": nbid}
            if isinstance(alias, str) and alias:
                out["notebooklm_alias"] = alias
            prof = m.get("notebooklm_profile")
            if isinstance(prof, str) and prof:
                out["notebooklm_profile"] = prof
            return out
    return None


UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _nlm(cmd: List[str]) -> subprocess.CompletedProcess:
    return _run(["nlm", *cmd], check=False)


def _nlm_require() -> None:
    try:
        _run(["nlm", "--help"])
    except Exception:
        raise RuntimeError("`nlm` not found on PATH. Install `notebooklm-mcp-cli` (or notebooklm-cli).")


def _nlm_login(profile: Optional[str]) -> None:
    _nlm_require()
    cmd = ["login"]
    if profile:
        cmd += ["--profile", profile]
    p = _nlm(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "nlm login failed")
    console.print(p.stdout.strip())


def _nlm_auth_status(profile: Optional[str]) -> str:
    _nlm_require()
    cmd = ["auth", "status"]
    if profile:
        cmd += ["--profile", profile]
    p = _nlm(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "nlm auth status failed")
    return p.stdout.strip()


def _nlm_notebook_create(title: str, profile: Optional[str]) -> str:
    _nlm_require()
    cmd = ["notebook", "create", title]
    if profile:
        cmd += ["--profile", profile]
    p = _nlm(cmd)
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    if p.returncode != 0:
        raise RuntimeError(out.strip() or "nlm notebook create failed")
    m = UUID_RE.search(out)
    if not m:
        raise RuntimeError(f"Could not parse notebook id from nlm output:\n{out.strip()}")
    return m.group(0)


def _nlm_alias_set(alias: str, notebook_id: str, profile: Optional[str]) -> None:
    _nlm_require()
    cmd = ["alias", "set", alias, notebook_id]
    if profile:
        cmd += ["--profile", profile]
    p = _nlm(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "nlm alias set failed")


def _nlm_source_add_url(notebook_ref: str, url: str, profile: Optional[str]) -> str:
    _nlm_require()
    cmd = ["source", "add", notebook_ref, "--url", url]
    if profile:
        cmd += ["--profile", profile]
    p = _nlm(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "nlm source add --url failed")
    return p.stdout.strip()


def _nlm_source_add_text(notebook_ref: str, title: str, text: str, profile: Optional[str]) -> str:
    _nlm_require()
    cmd = ["source", "add", notebook_ref, "--text", text, "--title", title]
    if profile:
        cmd += ["--profile", profile]
    p = _nlm(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "nlm source add --text failed")
    return p.stdout.strip()


def _nlm_notebook_query(notebook_ref: str, question: str, profile: Optional[str]) -> str:
    _nlm_require()
    cmd = ["notebook", "query", notebook_ref, question]
    if profile:
        cmd += ["--profile", profile]
    p = _nlm(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "nlm notebook query failed")
    return p.stdout.strip()


def _print_help() -> None:
    txt = """\
Commands:
  /help                         Show this help
  /exit                         Quit

Scope & mem0:
  /scope                         Show current scope
  /scope workspace=W project=P   Set current scope (workspace+project required)
  /projects                      List projects in the shared mem0 DB for current workspace
  /use PROJECT                   Switch project (workspace stays the same)
  /health                        Call mem0 health tool via MCP
  /search QUERY                  Search mem0 in current scope
  /save KIND TEXT                Store memory (KIND: decision|preference|summary|artifact_context|note)
  remember: TEXT                 Store memory as kind=note

NotebookLM (nlm):
  /nlm login [profile]           Authenticate (opens Chrome)
  /nlm auth [profile]            Show auth status
  /nlm init [profile]            Create or reuse a NotebookLM notebook for current scope, store mapping into mem0
  /nlm add-url URL               Add URL source to current scope notebook
  /nlm add-text TITLE :: TEXT    Add pasted text as a source (split at '::')
  /nlm ask QUESTION              Ask NotebookLM (one-shot) for current scope notebook

Chat:
  Any other input runs:
    mem0 memory_search -> chat response (OpenAI, Ollama, Nitro, or OpenCode Zen)
"""
    console.print(Panel.fit(Text(txt)))


def _parse_kv_args(parts: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for p in parts:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and v:
            out[k] = v
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="mem0chat: terminal chat + mem0 + NotebookLM")
    ap.add_argument("--mem0-url", default=DEFAULT_MEM0_MCP_URL)
    ap.add_argument("--healthz-url", default=DEFAULT_MEM0_HEALTHZ_URL)
    ap.add_argument("--db", default=DEFAULT_MEM0_DB, help="Read-only DB path for listing projects/mappings")
    ap.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    ap.add_argument("--project", default=None)
    ap.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT)
    ap.add_argument(
        "--provider",
        default=os.environ.get("CHAT_PROVIDER", "opencode-zen"),
        choices=["openai", "ollama", "nitro", "opencode-zen"],
        help="Chat backend: openai, ollama, nitro veya opencode-zen (varsayılan: opencode-zen).",
    )
    ap.add_argument("--model", default=DEFAULT_OPENAI_MODEL, help="OpenAI model (when --provider=openai)")
    ap.add_argument("--nitro-url", default=DEFAULT_NITRO_URL, help="Nitro base URL")
    ap.add_argument("--nitro-api-key", default=os.environ.get("NITRO_API_KEY", "nitro-local"), help="API Key for Nitro/External provider")
    ap.add_argument("--ollama-url", default=DEFAULT_OLLAMA_BASE_URL, help="Ollama base URL (when --provider=ollama)")
    ap.add_argument(
        "--ollama-model",
        default=DEFAULT_OLLAMA_CHAT_MODEL,
        help="Ollama chat model (when --provider=ollama). Example: llama3, mistral, qwen2.5:7b",
    )
    ap.add_argument("--opencode-zen-url", default=DEFAULT_OPENCODE_ZEN_URL, help="OpenCode Zen base URL")
    ap.add_argument("--opencode-zen-model", default=DEFAULT_OPENCODE_ZEN_MODEL, help="OpenCode Zen model")
    ap.add_argument(
        "--opencode-zen-api-key",
        default=os.environ.get("OPENCODE_ZEN_API_KEY", "") or _decrypt_gpg(DEFAULT_OPENCODE_ZEN_KEY_FILE) or "",
        help="OpenCode Zen API Key (or decrypt from GPG file)",
    )
    ap.add_argument("--opencode-zen-key-file", default=DEFAULT_OPENCODE_ZEN_KEY_FILE, help="GPG file with encrypted API key")
    ap.add_argument("--no-mem0", action="store_true", help="Disable mem0 calls (debug)")
    ap.add_argument("--no-openai", action="store_true", help="Disable OpenAI calls (debug)")
    args = ap.parse_args(argv)

    opencode_zen_api_key = args.opencode_zen_api_key
    if not opencode_zen_api_key and os.path.exists(args.opencode_zen_key_file):
        opencode_zen_api_key = _decrypt_gpg(args.opencode_zen_key_file) or ""

    cwd = os.getcwd()
    project = args.project or _default_project(cwd)
    scope = Scope(workspace=args.workspace, project=project)

    checkpoint_id = str(uuid.uuid4())
    provenance_note = f"mem0chat { _now_iso() }"

    mem0: Optional[Mem0McpClient] = None
    if not args.no_mem0:
        mem0 = Mem0McpClient(args.mem0_url, args.healthz_url)
        if not mem0.healthz():
            console.print(f"[yellow]Warning:[/] mem0 Supergateway healthz not OK at {args.healthz_url}")
        try:
            mem0.refresh_tool_map()
        except Exception as e:
            console.print(f"[yellow]Warning:[/] Could not list MCP tools ({e}). mem0 calls may fail.")

    history_path = os.path.expanduser("~/.copilot/mem0/mem0chat_history")
    os.makedirs(os.path.dirname(history_path), exist_ok=True)
    session = PromptSession(history=FileHistory(history_path))

    console.print(
        Panel.fit(
            Text(
                f"mem0chat\nscope: workspace={scope.workspace} project={scope.project}\n"
                f"mem0: {args.mem0_url}\nprovider: {args.provider}\n"
                + (
                    f"model: {args.model}"
                    if args.provider == "openai"
                    else f"model: {args.ollama_model}"
                    if args.provider in ("ollama", "nitro")
                    else f"model: {args.opencode_zen_model}"
                )
            )
        )
    )
    _print_help()

    nlm_profile: Optional[str] = None
    nlm_notebook_ref: Optional[str] = None

    def ensure_nlm_notebook() -> Tuple[str, Optional[str]]:
        nonlocal nlm_notebook_ref, nlm_profile
        # Prefer mapping stored in mem0 DB (read-only scan).
        mapping = _find_latest_notebooklm_mapping(args.db, scope)
        alias = _make_nlm_alias(scope.workspace, scope.project)
        if mapping:
            nbid = mapping.get("notebooklm_notebook_id", "")
            ali = mapping.get("notebooklm_alias") or alias
            prof = mapping.get("notebooklm_profile")
            if prof:
                nlm_profile = prof
            nlm_notebook_ref = ali or nbid
            return (nbid, ali)

        # Create new notebook and persist mapping into mem0 (explicit write).
        title = f"{scope.workspace}/{scope.project}"
        nbid = _nlm_notebook_create(title, nlm_profile)
        _nlm_alias_set(alias, nbid, nlm_profile)

        if mem0:
            content = (
                f"NotebookLM mapping for scope {scope.workspace}/{scope.project}: "
                f"notebook_id={nbid}, alias={alias}"
            )
            meta = {
                "notebooklm_notebook_id": nbid,
                "notebooklm_alias": alias,
            }
            if nlm_profile:
                meta["notebooklm_profile"] = nlm_profile
            mem0.memory_store(
                scope=scope,
                kind="artifact_context",
                content=content,
                checkpoint_id=checkpoint_id,
                metadata=meta,
                provenance_note=provenance_note,
            )
        nlm_notebook_ref = alias
        return (nbid, alias)

    while True:
        try:
            prompt = f"{scope.workspace}/{scope.project}> "
            line = session.prompt(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not line:
            continue

        # Explicit memory store shorthand.
        if line.lower().startswith("remember:"):
            txt = line.split(":", 1)[1].strip()
            if not txt:
                console.print("[yellow]Nothing to remember.[/]")
                continue
            if not mem0:
                console.print("[yellow]mem0 disabled.[/]")
                continue
            try:
                mem0.memory_store(
                    scope=scope,
                    kind="note",
                    content=txt,
                    checkpoint_id=checkpoint_id,
                    provenance_note=provenance_note,
                )
                console.print("[green]Saved to mem0.[/]")
            except Exception as e:
                console.print(f"[red]mem0 save failed:[/] {e}")
            continue

        if line.startswith("/"):
            parts = shlex.split(line)
            cmd = parts[0].lower()

            if cmd in ("/exit", "/quit"):
                break
            if cmd == "/help":
                _print_help()
                continue
            if cmd == "/scope":
                if len(parts) == 1:
                    console.print(json.dumps(scope.to_dict(), indent=2))
                    continue
                kv = _parse_kv_args(parts[1:])
                w = kv.get("workspace")
                p = kv.get("project")
                if not w or not p:
                    console.print("[red]Usage:[/] /scope workspace=W project=P")
                    continue
                scope = Scope(workspace=w, project=p)
                nlm_notebook_ref = None
                console.print(f"Scope set: {scope.workspace}/{scope.project}")
                continue
            if cmd == "/projects":
                try:
                    projs = _projects_in_workspace(args.db, scope.workspace)
                    if not projs:
                        console.print("(no projects found)")
                    else:
                        console.print("\n".join(projs))
                except Exception as e:
                    console.print(f"[red]Failed to list projects:[/] {e}")
                continue
            if cmd == "/use":
                if len(parts) != 2:
                    console.print("[red]Usage:[/] /use PROJECT")
                    continue
                scope = Scope(workspace=scope.workspace, project=parts[1])
                nlm_notebook_ref = None
                console.print(f"Scope set: {scope.workspace}/{scope.project}")
                continue
            if cmd == "/health":
                if not mem0:
                    console.print("[yellow]mem0 disabled.[/]")
                    continue
                try:
                    res = mem0.health()
                    structured = _extract_structured_content(res)
                    console.print(json.dumps(structured, indent=2))
                except Exception as e:
                    console.print(f"[red]mem0 health failed:[/] {e}")
                continue
            if cmd == "/search":
                if not mem0:
                    console.print("[yellow]mem0 disabled.[/]")
                    continue
                q = " ".join(parts[1:]).strip()
                if not q:
                    console.print("[red]Usage:[/] /search QUERY")
                    continue
                try:
                    res = mem0.memory_search(scope, q, limit=args.limit)
                    structured = _extract_structured_content(res)
                    console.print(json.dumps(structured, indent=2))
                except Exception as e:
                    console.print(f"[red]mem0 search failed:[/] {e}")
                continue
            if cmd == "/save":
                if not mem0:
                    console.print("[yellow]mem0 disabled.[/]")
                    continue
                if len(parts) < 3:
                    console.print("[red]Usage:[/] /save KIND TEXT")
                    continue
                kind = parts[1]
                txt = " ".join(parts[2:]).strip()
                try:
                    mem0.memory_store(
                        scope=scope,
                        kind=kind,
                        content=txt,
                        checkpoint_id=checkpoint_id,
                        provenance_note=provenance_note,
                    )
                    console.print("[green]Saved to mem0.[/]")
                except Exception as e:
                    console.print(f"[red]mem0 save failed:[/] {e}")
                continue

            # NotebookLM wrapper
            if cmd == "/nlm":
                if len(parts) < 2:
                    console.print("[red]Usage:[/] /nlm <login|auth|init|add-url|add-text|ask> ...")
                    continue
                sub = parts[1].lower()
                rest = parts[2:]
                try:
                    if sub == "login":
                        nlm_profile = rest[0] if rest else nlm_profile
                        _nlm_login(nlm_profile)
                        continue
                    if sub == "auth":
                        nlm_profile = rest[0] if rest else nlm_profile
                        console.print(_nlm_auth_status(nlm_profile))
                        continue
                    if sub == "init":
                        nlm_profile = rest[0] if rest else nlm_profile
                        nbid, alias = ensure_nlm_notebook()
                        console.print(f"NotebookLM ready: id={nbid} alias={alias}")
                        continue
                    if sub == "add-url":
                        if not rest:
                            console.print("[red]Usage:[/] /nlm add-url URL")
                            continue
                        ensure_nlm_notebook()
                        out = _nlm_source_add_url(nlm_notebook_ref or ensure_nlm_notebook()[1], rest[0], nlm_profile)
                        console.print(out)
                        continue
                    if sub == "add-text":
                        raw = " ".join(rest)
                        if "::" not in raw:
                            console.print("[red]Usage:[/] /nlm add-text TITLE :: TEXT")
                            continue
                        title, txt = [s.strip() for s in raw.split("::", 1)]
                        if not title or not txt:
                            console.print("[red]Usage:[/] /nlm add-text TITLE :: TEXT")
                            continue
                        ensure_nlm_notebook()
                        out = _nlm_source_add_text(
                            nlm_notebook_ref or ensure_nlm_notebook()[1], title, txt, nlm_profile
                        )
                        console.print(out)
                        continue
                    if sub == "ask":
                        q = " ".join(rest).strip()
                        if not q:
                            console.print("[red]Usage:[/] /nlm ask QUESTION")
                            continue
                        ensure_nlm_notebook()
                        ans = _nlm_notebook_query(nlm_notebook_ref or ensure_nlm_notebook()[1], q, nlm_profile)
                        console.print(Panel.fit(Markdown(ans) if ans else Text("(empty)"), title="NotebookLM"))
                        continue
                    console.print(f"[red]Unknown /nlm subcommand:[/] {sub}")
                except Exception as e:
                    console.print(f"[red]/nlm failed:[/] {e}")
                continue

            console.print(f"[red]Unknown command:[/] {cmd}")
            continue

        # Normal chat path: mem0 recall -> OpenAI response.
        mem_ctx = ""
        if mem0:
            try:
                res = mem0.memory_search(scope, line, limit=args.limit)
                structured = _extract_structured_content(res)
                mem_ctx = _format_mem0_results(structured)
                if mem_ctx:
                    console.print(Panel.fit(Text(mem_ctx), title="mem0"))
            except Exception as e:
                console.print(f"[yellow]mem0 recall failed:[/] {e}")

        system = (
            "You are a terminal assistant. Be concise, correct, and practical.\n"
            "If provided Memory Context (mem0), use it as background and do not invent details.\n"
        )
        user = line
        if mem_ctx:
            user = f"{mem_ctx}\n\nUser:\n{line}"

        try:
            if args.provider == "openai":
                if args.no_openai:
                    console.print("[yellow]OpenAI disabled (--no-openai).[/]")
                    continue
                _openai_stream_response(args.model, system, user)
            elif args.provider == "ollama":
                _ollama_stream_response(args.ollama_url, args.ollama_model, system, user)
            elif args.provider == "nitro":
                model_to_use = args.model if args.model != DEFAULT_OPENAI_MODEL else args.ollama_model
                _nitro_stream_response(args.nitro_url, model_to_use, system, user, args.nitro_api_key)
            elif args.provider == "opencode-zen":
                if not opencode_zen_api_key:
                    console.print("[red]OPENCODE_ZEN_API_KEY not set. Get your API key from https://opencode.ai/zen[/]")
                    continue
                _opencode_zen_stream_response(
                    args.opencode_zen_url,
                    args.opencode_zen_model,
                    system,
                    user,
                    opencode_zen_api_key,
                )
        except Exception as e:
            console.print(f"[red]Chat request failed:[/] {e}")

    if mem0:
        mem0.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
