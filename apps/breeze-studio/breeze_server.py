#!/usr/bin/env python3
"""Breeze / Nebula MCP demo — single-file stdlib server.

A small workflow UI that exercises the Quantum MCP media tools end-to-end:
Breeze TTS (list voices, generate, poll status, stream the MP3) and a
Nebula panel (list workflows, queue a run with a prompt override, poll
status, display image outputs).

Every tool call goes through the hub MCP gateway's own local endpoint
(127.0.0.1:8091/mcp, JSON-RPC, same protocol the Cooper bridge uses via
mcp.dsect.net). Auth: a gateway bearer key read at startup from the file
named by BREEZE_DEMO_MCP_KEY_FILE (default
/home/scott/.cooper/breeze-demo/mcp-key). The key never reaches the
browser. If the file is absent the page runs in a clearly-labelled
"not provisioned" mode instead of failing silently.

Binds 0.0.0.0:7656 (LAN + tailnet, same exposure as the tracker board
and PFML dashboard). Tailscale Serve (tailnet-only) fronts it on :8446.

New Voice creation (2026-10-27): the "New Voice" card designs a voice
from a plain-language description (hub tool quantum_breeze_design_voice)
and freezes it into a saved profile (quantum_breeze_save_voice). Those
two tools are NOT on this page's demo key: a second McpClient holds the
scoped breeze-creator key (BREEZE_CREATOR_KEY_FILE), and the create
endpoints additionally require the creator token the user types into
the form (checked against BREEZE_CREATOR_TOKEN_FILE, never sent anywhere
else). Without either secret the endpoints stay locked.
"""
import hmac
import html
import json
import os
import re
import sys
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs, quote

PORT = 7656
GATEWAY = os.environ.get("BREEZE_DEMO_GATEWAY", "http://127.0.0.1:8091/mcp")
KEY_FILE = os.environ.get(
    "BREEZE_DEMO_MCP_KEY_FILE", "/home/scott/.cooper/breeze-demo/mcp-key")
CREATOR_KEY_FILE = os.environ.get(
    "BREEZE_CREATOR_KEY_FILE", "/home/scott/.cooper/breeze-creator/mcp-key")
CREATOR_TOKEN_FILE = os.environ.get(
    "BREEZE_CREATOR_TOKEN_FILE", "/home/scott/.cooper/breeze-creator/ui-token")

# --- Solorion universal login (dsect-auth) ---------------------------------
# Voice creation is authorized per signed-in user: dsect-auth role "admin"
# or a "breeze-creator" entry in the user's services_allowed. The shared
# creator token above remains wired as a break-glass path only.
AUTH_DIR = "/home/scott/.config/dsect-auth"
AUTH_SERVICE = "breeze"
CREATOR_SERVICE_MARK = "breeze-creator"
SESSION_COOKIE = "breeze_session"
_dsect_auth = None


def _auth():
    """The shared dsect_auth module, or None when unavailable on this host."""
    global _dsect_auth
    if _dsect_auth is None:
        try:
            if AUTH_DIR not in sys.path:
                sys.path.insert(0, AUTH_DIR)
            import dsect_auth
            _dsect_auth = dsect_auth
        except Exception:
            _dsect_auth = False
    return _dsect_auth or None


def _session_claims(handler):
    """Verified dsect-auth JWT claims from the session cookie, or None."""
    auth = _auth()
    if auth is None:
        return None
    raw = handler.headers.get("Cookie") or ""
    token = None
    for part in raw.split(";"):
        part = part.strip()
        if part.startswith(SESSION_COOKIE + "="):
            token = unquote(part[len(SESSION_COOKIE) + 1:])
            break
    if not token:
        return None
    try:
        return auth.verify_token(token)
    except Exception:
        return None


def _can_create(claims):
    """Voice-creation permission: admin role, or an explicit services grant."""
    if not claims:
        return False
    if claims.get("role") == "admin":
        return True
    services = claims.get("services") or []
    return CREATOR_SERVICE_MARK in services or "breeze:create-voice" in services
BREEZE_DIR = Path("/mnt/fast/breeze-mcp")
NEBULA_OUTPUT_ROOTS = [Path("/home/scott/ComfyUI/output")]
MAX_BODY = 65536
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_]{2,80}$")
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
CTYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
          ".webp": "image/webp", ".gif": "image/gif", ".mp4": "video/mp4",
          ".webm": "video/webm", ".mp3": "audio/mpeg", ".wav": "audio/wav",
          ".flac": "audio/flac"}

# ---------------------------------------------------------------- MCP client

class McpError(Exception):
    pass

class McpNotProvisioned(McpError):
    pass

def _load_key(path):
    try:
        key = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return key or None

class McpClient:
    """Minimal streamable-HTTP MCP client for the hub gateway.

    Mirrors the bridge (mcp.py): initialize -> Mcp-Session-Id header,
    notifications/initialized, tools/call; unwraps SSE frames and
    structuredContent. Calls are serialized with a lock (the gateway
    session is shared); one re-init retry on session errors.
    """

    def __init__(self, key_file=None):
        self._lock = threading.Lock()
        self._session = None
        self._key_file = key_file or KEY_FILE
        self._key = _load_key(self._key_file)
        self._rid = 100

    @property
    def provisioned(self):
        return bool(self._key)

    def _post(self, payload, session=None):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(GATEWAY, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        req.add_header("Authorization", f"Bearer {self._key}")
        if session:
            req.add_header("Mcp-Session-Id", session)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode(errors="replace")
                ctype = r.headers.get("Content-Type", "")
                new_session = r.headers.get("Mcp-Session-Id")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:400]
            raise McpError(f"gateway HTTP {e.code}: {body}")
        except Exception as e:
            raise McpError(f"gateway unreachable: {e}")
        if "text/event-stream" in ctype:
            frames = [ln[5:].strip() for ln in raw.splitlines()
                      if ln.startswith("data:")]
            raw = frames[-1] if frames else raw
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            raise McpError(f"gateway returned non-JSON: {raw[:200]}")
        if isinstance(msg, dict) and msg.get("error"):
            err = msg["error"]
            raise McpError(err.get("message") or json.dumps(err)[:300])
        return msg.get("result"), new_session

    def _open_session(self):
        result, session = self._post({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "breeze-demo-page",
                                      "version": "1.0"}}})
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"},
                       session=session)
        except Exception:
            pass
        self._session = session
        return session

    def call(self, name, args):
        if not self._key:
            raise McpNotProvisioned(
                "MCP key not provisioned on Tritium yet "
                f"(expected a gateway key file at {self._key_file}).")
        with self._lock:
            for attempt in (1, 2):
                if not self._session:
                    self._open_session()
                self._rid += 1
                try:
                    result, _ = self._post(
                        {"jsonrpc": "2.0", "id": self._rid,
                         "method": "tools/call",
                         "params": {"name": name, "arguments": args}},
                        session=self._session)
                    break
                except McpError as e:
                    if attempt == 1 and ("session" in str(e).lower()
                                         or "HTTP 404" in str(e)
                                         or "HTTP 400" in str(e)):
                        self._session = None
                        continue
                    raise
        if not isinstance(result, dict):
            raise McpError("empty tool result")
        sc = result.get("structuredContent")
        if isinstance(sc, dict):
            parsed = sc
        else:
            text = ""
            for item in result.get("content") or []:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    break
            try:
                parsed = json.loads(text) if text else {}
            except json.JSONDecodeError:
                parsed = {"text": text}
        if result.get("isError") or (isinstance(parsed, dict)
                                     and parsed.get("ok") is False):
            msg = (parsed.get("error") or parsed.get("message")
                   or parsed.get("text") or "tool call failed")
            raise McpError(str(msg)[:400])
        return parsed

MCP = McpClient()
CREATOR = McpClient(CREATOR_KEY_FILE)


def _creator_token():
    """The shared secret a human must present to create voices, or None.

    Read from disk per call so rotating the file needs no restart. The
    token itself is only ever compared, never logged or returned.
    """
    try:
        tok = Path(CREATOR_TOKEN_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return tok or None
_audio_paths = {}          # job_id -> Path of finished MP3 (from result call)
_audio_lock = threading.Lock()
_prompt_param_cache = {}   # workflow -> {"node","key"} or None

def remember_audio(job_id, path_str):
    p = Path(path_str)
    try:
        resolved = p.resolve()
    except OSError:
        return
    if BREEZE_DIR.resolve() in resolved.parents:
        with _audio_lock:
            _audio_paths[job_id] = resolved

def audio_path_for(job_id):
    with _audio_lock:
        p = _audio_paths.get(job_id)
    if p and p.exists():
        return p
    candidate = BREEZE_DIR / job_id / "output.mp3"
    if candidate.exists():
        return candidate
    return None

def locate_nebula_output(filename):
    """Find a Nebula output file by basename under the ComfyUI output tree."""
    base = os.path.basename(filename or "")
    if not base:
        return None
    for root in NEBULA_OUTPUT_ROOTS:
        direct = root / base
        if direct.exists():
            return direct
        try:
            for dirpath, _dirs, files in os.walk(root):
                if os.path.relpath(dirpath, root).count(os.sep) > 3:
                    continue
                if base in files:
                    return Path(dirpath) / base
        except OSError:
            continue
    return None

def prompt_param_for(workflow):
    """The positive-prompt node/key for a workflow, via the MCP params tool."""
    if workflow in _prompt_param_cache:
        return _prompt_param_cache[workflow]
    found = None
    try:
        res = MCP.call("quantum_nebula_workflow_params", {"workflow": workflow})
        params = res.get("params") or []
        texts = [p for p in params if p.get("kind") == "text"]
        for p in texts:
            label = f"{p.get('label', '')} {p.get('title', '')}".lower()
            if "positive" in label:
                found = {"node": p["node"], "key": p["key"]}
                break
        if not found:
            for p in texts:
                if p.get("node_type") == "CLIPTextEncode":
                    found = {"node": p["node"], "key": p["key"]}
                    break
        if not found and texts:
            found = {"node": texts[0]["node"], "key": texts[0]["key"]}
    except McpError:
        found = None
    _prompt_param_cache[workflow] = found
    return found

# --------------------------------------------------------------------- page

CSS = """
:root {
  --ink: #0f172a;
  --ink-secondary: #475569;
  --mut: #64748b;
  --line: #e2e8f0;
  --line-focus: #94a3b8;
  --bg: #f8fafc;
  --parchment: #faf5ea;
  --parchment-deep: #f2e9d8;
  --parchment-line: #e2d5ba;
  --card: #ffffff;
  --card-subtle: #f1f5f9;
  --violet: #7c3aed;
  --violet-light: #ede9fe;
  --violet-hover: #6d28d9;
  --teal: #0d9488;
  --teal-light: #ccfbf1;
  --ok: #15803d;
  --ok-bg: #f0fdf4;
  --ok-line: #bbf7d0;
  --warn: #b45309;
  --warn-bg: #fffbeb;
  --warn-line: #fde68a;
  --err: #b91c1c;
  --err-bg: #fef2f2;
  --err-line: #fecaca;
  --radius-sm: 8px;
  --radius: 14px;
  --radius-lg: 18px;
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.08), 0 1px 2px -1px rgba(0, 0, 0, 0.08);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.08);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
  line-height: 1.5;
}
.wrap {
  max-width: 960px;
  margin: 0 auto;
  padding: 32px 20px 64px;
}
header {
  margin-bottom: 24px;
}
.header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
header h1 {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 4px;
  letter-spacing: -0.02em;
  color: var(--ink);
}
header p {
  margin: 0;
  color: var(--ink-secondary);
  font-size: 15px;
}
.badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  color: var(--mut);
}
.badge.live {
  color: var(--ok);
  background: var(--ok-bg);
  border-color: var(--ok-line);
}
.badge.warn {
  color: var(--warn);
  background: var(--warn-bg);
  border-color: var(--warn-line);
}
.badge.brand {
  color: var(--violet);
  background: var(--violet-light);
  border-color: #ddd6fe;
}
.badge-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

/* Tabs Navigation */
.tabs-nav {
  display: flex;
  gap: 6px;
  background: var(--card-subtle);
  padding: 4px;
  border-radius: var(--radius);
  margin-top: 20px;
  overflow-x: auto;
  border: 1px solid var(--line);
}
.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-secondary);
  background: transparent;
  border: 0;
  border-radius: 10px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease;
}
.tab-btn:hover {
  color: var(--ink);
  background: rgba(255, 255, 255, 0.6);
}
.tab-btn.active {
  color: var(--ink);
  background: #fff;
  box-shadow: var(--shadow-sm);
}

/* Tab Panels */
.tab-panel {
  display: none;
  animation: fadeIn 0.18s ease forwards;
}
.tab-panel.active {
  display: block;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Cards */
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 24px;
  margin-top: 18px;
  box-shadow: var(--shadow);
}
.card h2 {
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card .sub {
  color: var(--ink-secondary);
  font-size: 14px;
  margin: 0 0 18px;
  line-height: 1.5;
}

/* Forms */
label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  margin: 16px 0 6px;
  color: var(--ink);
}
label:first-of-type { margin-top: 0; }
select, input[type=text], input[type=password], textarea {
  width: 100%;
  font: inherit;
  font-size: 14.5px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--ink);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
select:focus, input[type=text]:focus, input[type=password]:focus, textarea:focus {
  outline: none;
  border-color: var(--violet);
  box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.12);
}
textarea {
  resize: vertical;
  min-height: 100px;
  line-height: 1.5;
}
.row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.row > div {
  flex: 1;
  min-width: 220px;
}
.char-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--mut);
  margin-top: 5px;
}

/* Chips */
.chips-wrap {
  margin-top: 10px;
}
.chips-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--mut);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}
.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.chip {
  font-size: 13px;
  padding: 6px 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--card-subtle);
  color: var(--ink-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}
.chip:hover {
  border-color: var(--violet);
  color: var(--violet);
  background: #fff;
}
.chip.active {
  background: var(--violet-light);
  border-color: #ddd6fe;
  color: var(--violet);
  font-weight: 600;
}

/* Buttons */
.btn-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 20px;
}
button.primary {
  background: #0f172a;
  color: #fff;
  border: 0;
  font: inherit;
  font-weight: 600;
  font-size: 14.5px;
  padding: 12px 24px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
button.primary:hover:not(:disabled) {
  background: #1e293b;
  transform: translateY(-1px);
}
button.primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
}
button.secondary {
  background: #fff;
  color: var(--ink-secondary);
  border: 1px solid var(--line);
  font: inherit;
  font-weight: 600;
  font-size: 14.5px;
  padding: 11px 20px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
button.secondary:hover:not(:disabled) {
  border-color: var(--line-focus);
  color: var(--ink);
  background: var(--card-subtle);
}
button.secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
button.danger-text {
  background: transparent;
  color: var(--err);
  border: 0;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
}
button.danger-text:hover {
  background: var(--err-bg);
}

/* Status & Progress */
.status {
  margin-top: 16px;
  font-size: 14px;
  color: var(--ink-secondary);
  min-height: 22px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.status.err {
  color: var(--err);
}
.status.ok {
  color: var(--ok);
  font-weight: 600;
}
.bar {
  height: 8px;
  background: #e2e8f0;
  border-radius: 99px;
  overflow: hidden;
  margin-top: 10px;
  display: none;
}
.bar > i {
  display: block;
  height: 100%;
  width: 0%;
  background: var(--violet);
  transition: width 0.4s ease;
}

/* Audio Player Container */
.player-box {
  background: var(--parchment);
  border: 1px solid var(--parchment-line);
  border-radius: var(--radius-sm);
  padding: 16px;
  margin-top: 16px;
}
.player-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-secondary);
}
audio {
  width: 100%;
  outline: none;
}
.player-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 12px;
  flex-wrap: wrap;
}
.dl-link {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--violet);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.dl-link:hover {
  text-decoration: underline;
}

/* History */
.hist {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}
.hist-item {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 16px;
  transition: box-shadow 0.15s ease;
}
.hist-item:hover {
  box-shadow: var(--shadow-sm);
}
.hist-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12.5px;
  color: var(--mut);
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 6px;
}
.hist-badge {
  background: var(--violet-light);
  color: var(--violet);
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
  font-size: 12px;
}
.hist-txt {
  font-size: 14.5px;
  color: var(--ink);
  line-height: 1.5;
  margin-bottom: 12px;
}
.hist-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.hist-actions {
  display: flex;
  gap: 12px;
}

/* Notice */
.notice {
  border: 1px solid #ecd9a8;
  background: #fffaf0;
  border-radius: var(--radius);
  padding: 14px 18px;
  margin-top: 18px;
  font-size: 14px;
  line-height: 1.55;
}
.info-banner {
  background: #f8fafc;
  border: 1px solid var(--line);
  border-left: 4px solid var(--violet);
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 13.5px;
  color: var(--ink-secondary);
  margin-bottom: 18px;
}

/* Nebula Outputs */
.outputs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
  margin-top: 16px;
}
.outputs figure {
  margin: 0;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.outputs img {
  width: 100%;
  height: 220px;
  object-fit: cover;
  display: block;
  transition: transform 0.2s ease;
}
.outputs img:hover {
  transform: scale(1.02);
}
.outputs figcaption {
  font-size: 12px;
  color: var(--mut);
  padding: 8px 12px;
  word-break: break-all;
  border-top: 1px solid var(--line);
  background: #fafafa;
}

footer {
  color: var(--mut);
  font-size: 13px;
  margin-top: 36px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
  line-height: 1.6;
}
code {
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12.5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

/* Solorion parchment surfaces (TRK-0593): new components are light-first
   parchment, matching the Solorion auth pages. */
.auth-area {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
}
.auth-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--parchment);
  border: 1px solid var(--parchment-line);
  color: var(--ink);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 13px;
  font-weight: 600;
}
.auth-note {
  font-size: 13px;
  color: var(--mut);
}
.auth-btn {
  background: #0f172a;
  color: #fff;
  border: 0;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  padding: 7px 14px;
  border-radius: 999px;
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}
.auth-btn:hover { background: #1e293b; }
.auth-btn.ghost {
  background: #fff;
  color: var(--ink-secondary);
  border: 1px solid var(--line);
}
.auth-btn.ghost:hover { border-color: var(--line-focus); color: var(--ink); }

/* React voice player (TRK-0592) */
.vp {
  background: var(--parchment);
  border: 1px solid var(--parchment-line);
  border-radius: var(--radius);
  padding: 12px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.hist .vp { background: #fff; }
.vp-play {
  flex: 0 0 auto;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: 0;
  background: #0f172a;
  color: #fff;
  font-size: 15px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.12s ease, background 0.12s ease;
}
.vp-play:hover { background: #1e293b; transform: translateY(-1px); }
.vp-main { flex: 1; min-width: 0; }
.vp-label {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.vp-sub {
  font-size: 12px;
  color: var(--mut);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.vp-track {
  height: 8px;
  background: var(--parchment-deep);
  border-radius: 99px;
  margin-top: 7px;
  cursor: pointer;
}
.vp-fill {
  height: 100%;
  width: 0%;
  background: var(--ink);
  border-radius: 99px;
}
.vp-time {
  flex: 0 0 auto;
  font-size: 12px;
  color: var(--ink-secondary);
  font-variant-numeric: tabular-nums;
  min-width: 88px;
  text-align: right;
}
.vp-unavailable { font-size: 13px; color: var(--mut); }

@media (max-width: 640px) {
  .wrap { padding: 20px 14px 48px; }
  .card { padding: 18px 14px; }
  .btn-row { flex-direction: column; align-items: stretch; }
  button.primary, button.secondary { width: 100%; justify-content: center; }
  .hist-footer { flex-direction: column; align-items: flex-start; }
}
"""

JS = """
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function api(path, opts) {
  const r = await fetch(path, opts);
  const d = await r.json().catch(() => ({ error: "bad server response" }));
  if (!r.ok) throw new Error(d.message || d.error || ("HTTP " + r.status));
  return d;
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}

// ---------------- Voice Player (React, TRK-0592) ----------------
// One shared React component replaces every native audio-controls
// preview: TTS renders, New Voice samples, and History clips.
const vpRoots = new WeakMap();
function fmtTime(s) {
  if (!isFinite(s) || s == null) return "0:00";
  s = Math.max(0, Math.floor(s));
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
}
function VoicePlayer(props) {
  const audioRef = React.useRef(null);
  const [playing, setPlaying] = React.useState(false);
  const [cur, setCur] = React.useState(0);
  const [dur, setDur] = React.useState(0);
  React.useEffect(() => {
    const a = audioRef.current;
    if (!a) return undefined;
    const onTime = () => setCur(a.currentTime);
    const onMeta = () => setDur(a.duration || 0);
    const onEnd = () => { setPlaying(false); setCur(0); };
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("loadedmetadata", onMeta);
    a.addEventListener("ended", onEnd);
    return () => {
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("loadedmetadata", onMeta);
      a.removeEventListener("ended", onEnd);
    };
  }, [props.src]);
  const toggle = () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) { a.play(); setPlaying(true); }
    else { a.pause(); setPlaying(false); }
  };
  const seek = (e) => {
    const a = audioRef.current;
    if (!a || !dur) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    a.currentTime = ratio * dur;
    setCur(a.currentTime);
  };
  const pct = dur ? Math.min(100, 100 * cur / dur) : 0;
  return React.createElement("div", { className: "vp" },
    React.createElement("audio", { ref: audioRef, src: props.src, preload: "metadata" }),
    React.createElement("button", { type: "button", className: "vp-play", onClick: toggle, "aria-label": playing ? "Pause" : "Play" }, playing ? "❚❚" : "▶"),
    React.createElement("div", { className: "vp-main" },
      React.createElement("div", { className: "vp-label" }, props.label || "Voice clip"),
      props.sublabel ? React.createElement("div", { className: "vp-sub" }, props.sublabel) : null,
      React.createElement("div", { className: "vp-track", onClick: seek },
        React.createElement("div", { className: "vp-fill", style: { width: pct + "%" } }))),
    React.createElement("div", { className: "vp-time" }, fmtTime(cur) + " / " + fmtTime(dur)));
}
function mountPlayer(el, opts) {
  if (!el) return;
  if (!window.React || !window.ReactDOM) {
    el.innerHTML = '<div class="vp"><span class="vp-unavailable">Player unavailable (React CDN unreachable) - use the download link.</span></div>';
    return;
  }
  let root = vpRoots.get(el);
  if (!root) { root = ReactDOM.createRoot(el); vpRoots.set(el, root); }
  root.render(React.createElement(VoicePlayer, Object.assign({}, opts, { key: opts.src })));
}

// ---------------- Solorion sign-in state (TRK-0591) ----------------
let authState = { signed_in: false, can_create: false, email: null, role: null };
async function loadAuth() {
  try {
    authState = await api("/api/auth/me");
  } catch (e) { /* sign-in display is best-effort */ }
  const area = $("authArea");
  if (!area) return;
  if (authState.signed_in) {
    area.innerHTML =
      '<span class="auth-chip"><span class="badge-dot" style="color:var(--ok)"></span> ' +
      esc(authState.email || "Signed in") + (authState.role ? " · " + esc(authState.role) : "") + "</span>" +
      (authState.can_create
        ? '<span class="badge live"><span class="badge-dot"></span> Voice creator</span>'
        : '<span class="badge warn"><span class="badge-dot"></span> No creation permission</span>') +
      '<button type="button" class="auth-btn ghost" id="authOut">Sign out</button>';
    $("authOut").addEventListener("click", async () => {
      try { await fetch("/api/auth/logout", { method: "POST" }); } catch (e) {}
      await loadAuth();
      nvRefreshGate();
    });
  } else {
    area.innerHTML =
      '<span class="auth-note">Not signed in - sign-in is only needed to create voices.</span>' +
      '<a class="auth-btn" href="/login">Sign in with Solorion</a>';
  }
}

// ---------------- Tabs Navigation ----------------
function initTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  const panels = document.querySelectorAll(".tab-panel");
  
  function switchTab(targetId) {
    tabs.forEach(t => t.classList.toggle("active", t.dataset.target === targetId));
    panels.forEach(p => p.classList.toggle("active", p.id === targetId));
    window.location.hash = targetId.replace("tab-", "");
  }

  tabs.forEach(t => {
    t.addEventListener("click", () => switchTab(t.dataset.target));
  });

  const hash = window.location.hash.replace("#", "");
  if (hash && $("tab-" + hash)) {
    switchTab("tab-" + hash);
  }
}

// ---------------- Presets Catalogue ----------------
const DIRECTIONS = [
  { label: "Casual & Warm", text: "Speak casually and warmly, like a friend chatting over coffee. Relaxed and upbeat, gentle volume, never projected or announcer-like." },
  { label: "Calm Documentary", text: "Speak like a calm documentary narrator: measured pace, clear diction, warm low register, natural pauses between sentences." },
  { label: "Upbeat Morning", text: "Bright and energetic, like a morning radio host: upbeat and smiling, but never shouted." },
  { label: "Gentle & Soothing", text: "Soft, gentle, calm delivery with a slow and soothing pace, perfect for nighttime relaxation." }
];

const SAMPLES = [
  { label: "Fleet Greeting", text: "Good evening. This is the Breeze demo page, coming to you live through the Quantum MCP on Tritium." },
  { label: "Phonetic Test", text: "The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs." },
  { label: "Quantum Channel", text: "Welcome back to the Quantum Channel. Tonight we take a look back at how far the fleet has come." },
  { label: "Smart Home Brief", text: "Tritium server reports all 24 core services up and healthy. Indoor temperature is comfortable." }
];

const DESC_PRESETS = [
  { label: "Warm Baritone", text: "A warm, resonant masculine baritone voice with calm pacing and a friendly, confident tone." },
  { label: "Calm Narrator", text: "A composed and articulate storytelling voice with gentle warmth and crystal-clear pronunciation." },
  { label: "Energetic Host", text: "An upbeat, engaging, and dynamic conversational voice with bright energy and expressive pauses." },
  { label: "Thoughtful Guide", text: "A gentle, reassuring tone with an even cadence and soothing vocal texture." }
];

function buildChips() {
  $("dirChips").innerHTML = DIRECTIONS.map((d, i) =>
    `<button type="button" class="chip" data-idx="${i}">${esc(d.label)}</button>`
  ).join("");
  $("dirChips").querySelectorAll("button").forEach(b => {
    b.onclick = () => {
      $("bInstruction").value = DIRECTIONS[+b.dataset.idx].text;
      $("dirChips").querySelectorAll("button").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
    };
  });

  $("textChips").innerHTML = SAMPLES.map((s, i) =>
    `<button type="button" class="chip" data-idx="${i}">${esc(s.label)}</button>`
  ).join("");
  $("textChips").querySelectorAll("button").forEach(b => {
    b.onclick = () => {
      $("bText").value = SAMPLES[+b.dataset.idx].text;
      $("textChips").querySelectorAll("button").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      countChars();
    };
  });

  $("nvDescChips").innerHTML = DESC_PRESETS.map((p, i) =>
    `<button type="button" class="chip" data-idx="${i}">${esc(p.label)}</button>`
  ).join("");
  $("nvDescChips").querySelectorAll("button").forEach(b => {
    b.onclick = () => {
      $("nvDesc").value = DESC_PRESETS[+b.dataset.idx].text;
      $("nvDescChips").querySelectorAll("button").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
    };
  });
}

function countChars() {
  const len = $("bText").value.length;
  $("bCount").textContent = `${len} / 2000 characters`;
}

// ---------------- Voice Loading ----------------
let loadedVoices = [];
async function loadVoices() {
  try {
    const d = await api("/api/voices");
    loadedVoices = d.voices || [];
    $("bVoice").innerHTML = loadedVoices.map(v => {
      const sizeKb = v.size_bytes ? Math.round(v.size_bytes / 1024) + " KB" : "";
      const isCanonical = v.name === "cooper-v3" ? " (Official Default)" : "";
      const label = `${v.name}${isCanonical}${sizeKb ? " · " + sizeKb : ""}`;
      return `<option value="${esc(v.name)}">${esc(label)}</option>`;
    }).join("");

    // Cooper-v3 is canonical official default
    const def = loadedVoices.find(v => v.name === "cooper-v3") || loadedVoices[0];
    if (def) $("bVoice").value = def.name;
    $("bVoiceInfo").textContent = `${loadedVoices.length} voices ready on Tritium GPU`;
  } catch (e) {
    $("bStatus").textContent = "Could not load voices: " + e.message;
    $("bStatus").className = "status err";
  }
}

// ---------------- Breeze TTS Generator ----------------
let activeBreezePoll = false;
let currentBreezeJobId = null;

function resetBreezeUi() {
  activeBreezePoll = false;
  currentBreezeJobId = null;
  $("bGo").disabled = false;
  $("bCancel").style.display = "none";
  $("bBar").style.display = "none";
  $("bFill").style.width = "0%";
}

async function breezeGenerate() {
  const text = $("bText").value.trim();
  const voice = $("bVoice").value;
  const instr = $("bInstruction").value.trim();
  const st = $("bStatus"), bar = $("bBar"), fill = $("bFill");

  st.className = "status";
  $("bPlayerBox").style.display = "none";

  if (!text) {
    st.textContent = "Please write or select some text to speak first.";
    st.className = "status err";
    return;
  }

  $("bGo").disabled = true;
  $("bCancel").style.display = "inline-flex";
  bar.style.display = "block";
  fill.style.width = "4%";
  st.textContent = "Submitting voice job to Breeze via Quantum MCP...";

  activeBreezePoll = true;
  const t0 = Date.now();

  try {
    const job = await api("/api/breeze/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice, instruction: instr || undefined })
    });
    const jobId = job.job_id;
    currentBreezeJobId = jobId;
    let state = job.state || "queued";

    while (activeBreezePoll) {
      if (Date.now() - t0 > 10 * 60 * 1000) {
        throw new Error("Job timed out after 10 minutes — the job may still finish on the hub.");
      }
      const s = await api("/api/breeze/status/" + encodeURIComponent(jobId));
      state = s.state;
      if (s.chunks_total) {
        const pct = Math.round(100 * (s.chunks_done || 0) / s.chunks_total);
        fill.style.width = Math.max(4, pct) + "%";
        st.textContent = `Rendering with ${voice} — chunk ${s.chunks_done || 0} of ${s.chunks_total} (${pct}%)...`;
      } else {
        st.textContent = `Breeze job: ${state}...`;
      }
      if (state === "done") break;
      if (state === "error") throw new Error(s.error || "Generation failed on the hub.");
      await sleep(2000);
    }

    if (!activeBreezePoll) return;

    fill.style.width = "100%";
    const res = await api("/api/breeze/result/" + encodeURIComponent(jobId));
    const url = "/audio/" + encodeURIComponent(jobId);
    mountPlayer($("bPlayer"), { src: url, label: voice, sublabel: "Breeze render" });
    $("bPlayerBox").style.display = "block";

    const dl = $("bDl");
    dl.href = url;
    dl.download = res.filename || `${voice}-${jobId}.mp3`;
    const kb = res.size_bytes ? ` (${Math.round(res.size_bytes / 1024)} KB)` : "";
    dl.textContent = `Download MP3${kb}`;

    const dur = Math.round((Date.now() - t0) / 1000);
    st.textContent = `Rendered successfully in ${dur}s with ${voice}.`;
    st.className = "status ok";

    addHistoryItem({
      jobId,
      voice,
      text,
      instruction: instr,
      url,
      timestamp: Date.now()
    });
  } catch (e) {
    if (activeBreezePoll) {
      st.textContent = "Generation failed: " + e.message;
      st.className = "status err";
    }
  } finally {
    resetBreezeUi();
  }
}

function cancelBreeze() {
  activeBreezePoll = false;
  $("bStatus").textContent = "Generation cancelled by user.";
  $("bStatus").className = "status err";
  resetBreezeUi();
}

// ---------------- Persistent History ----------------
const HISTORY_KEY = "breeze_history_v2";

function getHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch (e) {
    return [];
  }
}

function addHistoryItem(item) {
  const hist = getHistory();
  hist.unshift(item);
  if (hist.length > 50) hist.pop();
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(hist));
  } catch (e) {}
  renderHistory();
}

function clearAllHistory() {
  if (confirm("Clear all generation history in this browser?")) {
    localStorage.removeItem(HISTORY_KEY);
    renderHistory();
  }
}

function deleteHistoryItem(idx) {
  const hist = getHistory();
  hist.splice(idx, 1);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(hist));
  renderHistory();
}

function useHistoryText(idx) {
  const hist = getHistory();
  const item = hist[idx];
  if (item) {
    $("bText").value = item.text || "";
    if (item.voice && loadedVoices.some(v => v.name === item.voice)) {
      $("bVoice").value = item.voice;
    }
    if (item.instruction) {
      $("bInstruction").value = item.instruction;
    }
    countChars();
    document.querySelector('.tab-btn[data-target="tab-tts"]').click();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function renderHistory() {
  const hist = getHistory();
  const list = $("histList");
  if (!hist.length) {
    list.innerHTML = `<div class="sub" style="margin-top:10px;">No clips generated yet. Renders created in the TTS Studio will appear here with audio playback and download links.</div>`;
    return;
  }
  list.innerHTML = hist.map((h, i) => {
    const timeStr = new Date(h.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const dateStr = new Date(h.timestamp).toLocaleDateString([], { month: "short", day: "numeric" });
    return `
      <div class="hist-item">
        <div class="hist-meta">
          <div><span class="hist-badge">${esc(h.voice)}</span> · ${dateStr} at ${timeStr}</div>
          <button type="button" class="danger-text" onclick="deleteHistoryItem(${i})">Remove</button>
        </div>
        <div class="hist-txt">"${esc(h.text)}"</div>
        <div class="hist-player" data-src="${h.url}" data-label="${esc(h.voice)}" data-sub="History clip"></div>
        <div class="hist-footer" style="margin-top:12px;">
          <a class="dl-link" href="${h.url}" download="${esc(h.voice)}-clip.mp3">⬇ Download MP3</a>
          <button type="button" class="secondary" style="padding:6px 14px;font-size:13px;" onclick="useHistoryText(${i})">Use Text in Studio</button>
        </div>
      </div>
    `;
  }).join("");
  list.querySelectorAll(".hist-player").forEach(el => {
    mountPlayer(el, { src: el.dataset.src, label: el.dataset.label, sublabel: el.dataset.sub });
  });
}

// ---------------- New Voice Designer ----------------
let nvDesignJob = null;
const TOKEN_KEY = "breeze_creator_token";

function nvToken() {
  return $("nvToken").value.trim();
}

function nvCount() {
  $("nvSampleCount").textContent = `${$("nvSample").value.length} / 320 characters`;
}

function initTokenStorage() {
  const saved = localStorage.getItem(TOKEN_KEY);
  if (saved) {
    $("nvToken").value = saved;
    $("nvRemember").checked = true;
    updateTokenBadge(true);
  }
  $("nvToken").addEventListener("input", () => {
    if ($("nvRemember").checked) {
      localStorage.setItem(TOKEN_KEY, nvToken());
    }
    updateTokenBadge(Boolean(nvToken()));
  });
  $("nvRemember").addEventListener("change", () => {
    if ($("nvRemember").checked) {
      localStorage.setItem(TOKEN_KEY, nvToken());
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  });
}

function updateTokenBadge(hasToken) {
  const badge = $("nvTokenBadge");
  if (hasToken) {
    badge.className = "badge live";
    badge.innerHTML = `<span class="badge-dot"></span> Creator Token Set`;
  } else {
    badge.className = "badge warn";
    badge.innerHTML = `<span class="badge-dot"></span> Token Required`;
  }
}

async function nvRefreshGate() {
  try {
    const d = await api("/api/creator/status");
    if (!d.provisioned) {
      $("nvGate").innerHTML = `<span style="color:var(--err)">Voice creation is not provisioned on the server (no creator key file); form is locked.</span>`;
      $("nvGo").disabled = true;
      $("nvSave").disabled = true;
    } else if (d.can_create) {
      $("nvGate").innerHTML = `Signed in as ${esc(d.email || "your Solorion account")} - your account has voice-creation permission, so no creator token is needed. Renders sample on GPU, then freezes profile into Tritium's voices catalogue.`;
      $("nvGo").disabled = false;
    } else if (!d.token_set && !d.signed_in) {
      $("nvGate").innerHTML = `<span style="color:var(--warn)">No creator token is provisioned on Tritium yet - creation needs a signed-in creator account.</span>`;
      $("nvGo").disabled = true;
    } else if (d.signed_in) {
      $("nvGate").innerHTML = `Signed in as ${esc(d.email || "your account")} - this account does not have voice-creation permission, but the break-glass creator token below still works.`;
    } else {
      $("nvGate").innerHTML = `Creation is authorized per user: sign in with a Solorion account that has the creator permission, or use the break-glass creator token below. Creation is authenticated via scoped hub key & human creator token. Renders sample on GPU, then freezes profile into Tritium's voices catalogue.`;
    }
  } catch (e) {
    $("nvGate").textContent = "Could not check creation status: " + e.message;
  }
}

async function nvPoll(jobId, st, fill, t0) {
  while (true) {
    if (Date.now() - t0 > 5 * 60 * 1000) {
      throw new Error("Timed out after 5 minutes — the job may still finish on the hub.");
    }
    const s = await api("/api/breeze/status/" + encodeURIComponent(jobId));
    if (fill && s.chunks_total) {
      fill.style.width = Math.round(100 * (s.chunks_done || 0) / s.chunks_total) + "%";
    }
    st.textContent = `Job status: ${s.state || "rendering"}...`;
    if (s.state === "done") return s;
    if (s.state === "error") throw new Error(s.error || "The job failed on the hub.");
    await sleep(2000);
  }
}

async function nvDesign() {
  const instr = $("nvDesc").value.trim();
  const sample = $("nvSample").value.trim();
  const st = $("nvStatus"), bar = $("nvBar"), fill = $("nvFill");

  st.className = "status";
  $("nvPlayerBox").style.display = "none";
  $("nvSave").disabled = true;
  nvDesignJob = null;

  if (!authState.can_create && !nvToken()) {
    st.textContent = "Sign in with a creator account, or enter the break-glass creator token above.";
    st.className = "status err";
    return;
  }
  if (!instr) {
    st.textContent = "Please describe the desired voice characteristics.";
    st.className = "status err";
    return;
  }
  if (!sample) {
    st.textContent = "Please provide a sample reference line to speak.";
    st.className = "status err";
    return;
  }

  $("nvGo").disabled = true;
  bar.style.display = "block";
  fill.style.width = "6%";
  st.textContent = "Designing voice profile on Tritium GPU...";
  const t0 = Date.now();

  try {
    const seedRaw = $("nvSeed").value.trim();
    const designHeaders = { "Content-Type": "application/json" };
    if (nvToken()) designHeaders["X-Creator-Token"] = nvToken();
    const job = await api("/api/voices/design", {
      method: "POST",
      headers: designHeaders,
      body: JSON.stringify({ instruction: instr, sample_text: sample,
                             seed: seedRaw === "" ? undefined : Number(seedRaw) })
    });
    nvDesignJob = job.job_id;
    await nvPoll(nvDesignJob, st, fill, t0);
    fill.style.width = "100%";
    mountPlayer($("nvPlayer"), { src: "/audio/" + encodeURIComponent(nvDesignJob),
                                 label: $("nvName").value.trim() || "Designed voice",
                                 sublabel: "New Voice sample" });
    $("nvPlayerBox").style.display = "block";
    st.textContent = "Sample rendered! Listen above. If satisfied, specify a name and freeze the profile." +
      (job.seed_note ? " Seed: " + job.seed_note : "");
    st.className = "status ok";
    $("nvSave").disabled = false;
  } catch (e) {
    st.textContent = "Design failed: " + e.message;
    st.className = "status err";
  } finally {
    $("nvGo").disabled = false;
    bar.style.display = "none";
  }
}

async function nvSave() {
  const name = $("nvName").value.trim().toLowerCase().replace(/\\s+/g, "-");
  const st = $("nvStatus");
  st.className = "status";

  if (!nvDesignJob) {
    st.textContent = "Render a sample audio line first.";
    st.className = "status err";
    return;
  }
  if (!/^[a-z0-9][a-z0-9-]{0,39}$/.test(name)) {
    st.textContent = "Voice name must be lowercase alphanumeric with hyphens (max 40 chars, e.g. 'friendly-announcer').";
    st.className = "status err";
    return;
  }

  $("nvSave").disabled = true;
  $("nvGo").disabled = true;
  st.textContent = `Freezing '${name}' into permanent .breeze profile...`;
  const t0 = Date.now();

  try {
    const saveHeaders = { "Content-Type": "application/json" };
    if (nvToken()) saveHeaders["X-Creator-Token"] = nvToken();
    const job = await api("/api/voices/save", {
      method: "POST",
      headers: saveHeaders,
      body: JSON.stringify({ design_job_id: nvDesignJob, name })
    });
    await nvPoll(job.job_id, st, null, t0);
    st.textContent = `Voice '${name}' saved successfully! Available in Studio picker, Hub API, and Home Assistant tts.breeze.`;
    st.className = "status ok";
    await loadVoices();
    $("bVoice").value = name;
  } catch (e) {
    st.textContent = "Save failed: " + e.message;
    st.className = "status err";
    $("nvSave").disabled = false;
  } finally {
    $("nvGo").disabled = false;
  }
}

// ---------------- Nebula Workflows ----------------
let promptTargets = {};

async function loadWorkflows() {
  try {
    const d = await api("/api/workflows");
    const rawList = d.workflows || [];
    
    // Group workflows logically by prefix
    const groups = {};
    for (const w of rawList) {
      let clean = w.name.replace(/\\.json$/i, "");
      let cat = "General Workflows";
      if (clean.startsWith("3D -")) {
        cat = "3D Generation";
        clean = clean.replace(/^3D -\\s*/, "");
      } else if (clean.startsWith("Audio -")) {
        cat = "Audio & Music";
        clean = clean.replace(/^Audio -\\s*/, "");
      } else if (clean.startsWith("Image Edit -")) {
        cat = "Image Editing";
        clean = clean.replace(/^Image Edit -\\s*/, "");
      } else if (clean.startsWith("Image to Image -")) {
        cat = "Image to Image";
        clean = clean.replace(/^Image to Image -\\s*/, "");
      } else if (clean.startsWith("Image to Video -")) {
        cat = "Image to Video";
        clean = clean.replace(/^Image to Video -\\s*/, "");
      } else if (clean.startsWith("Text to Image -")) {
        cat = "Text to Image";
        clean = clean.replace(/^Text to Image -\\s*/, "");
      } else if (clean.startsWith("Text to Video -")) {
        cat = "Text to Video";
        clean = clean.replace(/^Text to Video -\\s*/, "");
      } else if (clean.startsWith("Video -")) {
        cat = "Video Generation";
        clean = clean.replace(/^Video -\\s*/, "");
      } else if (clean.startsWith("Upscale -")) {
        cat = "Upscaling";
        clean = clean.replace(/^Upscale -\\s*/, "");
      }
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push({ raw: w.name, clean });
    }

    let htmlOptions = "";
    for (const [cat, items] of Object.entries(groups)) {
      htmlOptions += `<optgroup label="${esc(cat)}">`;
      for (const it of items) {
        htmlOptions += `<option value="${esc(it.raw)}">${esc(it.clean)}</option>`;
      }
      htmlOptions += `</optgroup>`;
    }
    $("nWorkflow").innerHTML = htmlOptions;

    // Default to DreamShaper 8 fast
    const def = rawList.find(w => w.name.includes("DreamShaper 8")) || rawList[0];
    if (def) $("nWorkflow").value = def.name;
    notePromptTarget();
  } catch (e) {
    $("nStatus").textContent = "Could not load workflows: " + e.message;
    $("nStatus").className = "status err";
  }
}

async function notePromptTarget() {
  const wf = $("nWorkflow").value;
  if (!wf) return;
  if (!(wf in promptTargets)) {
    try {
      const d = await api("/api/workflow_prompt?workflow=" + encodeURIComponent(wf));
      promptTargets[wf] = d.prompt_param || null;
    } catch (e) {
      promptTargets[wf] = null;
    }
  }
  const note = $("nPromptNote");
  if (promptTargets[wf]) {
    note.innerHTML = `<span style="color:var(--ok)">✓ Prompt node mapped (${esc(promptTargets[wf].key || 'text')})</span>`;
  } else {
    note.innerHTML = `<span style="color:var(--mut)">ℹ Uses workflow defaults (no external prompt node)</span>`;
  }
}

async function nebulaGenerate() {
  const wf = $("nWorkflow").value;
  const backend = $("nBackend").value;
  const prompt = $("nPrompt").value.trim();
  const st = $("nStatus");

  st.className = "status";
  $("nOutputs").innerHTML = "";
  $("nGo").disabled = true;
  const t0 = Date.now();
  st.textContent = "Queuing execution on Nebula ComfyUI...";

  try {
    const job = await api("/api/nebula/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow: wf, backend, prompt: prompt || undefined })
    });
    if (job.state === "deferred" || job.deferred) {
      st.textContent = "The GPU backend is busy — job was deferred. Please retry shortly.";
      $("nGo").disabled = false;
      return;
    }
    const pid = job.prompt_id;
    let state = "queued";
    while (true) {
      if (Date.now() - t0 > 15 * 60 * 1000) {
        throw new Error("Timed out after 15 minutes — video workflows can run long.");
      }
      const s = await api("/api/nebula/status/" + encodeURIComponent(pid));
      state = s.state || state;
      st.textContent = `Nebula status: ${state} (${Math.round((Date.now() - t0) / 1000)}s elapsed)...`;
      if (s.done || state === "done" || state === "completed" || state === "success") {
        const outs = s.outputs || [];
        if (!outs.length) {
          st.textContent = "Execution completed — no output files reported.";
          break;
        }
        st.textContent = `Completed! ${outs.length} output file(s) generated.`;
        st.className = "status ok";
        $("nOutputs").innerHTML = outs.map(o => {
          const name = typeof o === "string" ? o : (o.filename || o.name || "");
          const url = "/nebula_output/" + encodeURIComponent(name);
          return /\\.(png|jpe?g|webp|gif)$/i.test(name)
            ? `<figure><a href="${url}" target="_blank"><img src="${url}" alt=""></a><figcaption>${esc(name)}</figcaption></figure>`
            : `<figure><figcaption><a href="${url}" target="_blank">⬇ ${esc(name)}</a></figcaption></figure>`;
        }).join("");
        break;
      }
      if (state === "error" || state === "failed") {
        throw new Error(s.error || "The Nebula workflow execution failed.");
      }
      await sleep(3500);
    }
  } catch (e) {
    st.textContent = "Execution failed: " + e.message;
    st.className = "status err";
  } finally {
    $("nGo").disabled = false;
  }
}

// ---------------- Initialization ----------------
window.addEventListener("DOMContentLoaded", () => {
  initTabs();
  buildChips();
  countChars();
  loadVoices();
  loadWorkflows();
  renderHistory();
  initTokenStorage();
  loadAuth();
  $("nvSeedDice").addEventListener("click", () => {
    $("nvSeed").value = Math.floor(Math.random() * 2147483647);
  });

  $("bText").addEventListener("input", countChars);
  $("bGo").addEventListener("click", breezeGenerate);
  $("bCancel").addEventListener("click", cancelBreeze);

  $("nGo").addEventListener("click", nebulaGenerate);
  $("nWorkflow").addEventListener("change", notePromptTarget);

  nvRefreshGate();
  nvCount();
  $("nvSample").addEventListener("input", nvCount);
  $("nvGo").addEventListener("click", nvDesign);
  $("nvSave").addEventListener("click", nvSave);
});
"""

def render_login_page(next_url="/"):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in - Breeze Studio - Solorion</title>
<style>{CSS}
.login-wrap {{ max-width: 420px; margin: 8vh auto 0; padding: 0 16px 40px; }}
.login-card {{ background: #fff; border: 1px solid var(--parchment-line); border-radius: var(--radius-lg); box-shadow: var(--shadow-md); padding: 28px 26px; }}
.login-brand {{ font-size: 13px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: var(--violet); margin-bottom: 6px; }}
</style>
</head>
<body style="background: var(--parchment);">
<div class="login-wrap">
  <div class="login-card">
    <div class="login-brand">Solorion</div>
    <h1 style="margin:0 0 6px; font-size:24px;">Sign in to Breeze Studio</h1>
    <p class="sub" style="margin:0 0 8px;">Use your Solorion account. Voice creation needs an account with the creator permission; speech generation stays open on the tailnet.</p>
    <label for="liEmail">Email</label>
    <input type="text" id="liEmail" autocomplete="username" placeholder="you@dsect.net">
    <label for="liPass">Password</label>
    <input type="password" id="liPass" autocomplete="current-password" placeholder="Your password">
    <div class="status err" id="liStatus"></div>
    <div class="btn-row">
      <button class="primary" id="liGo" style="flex:1; justify-content:center;">Sign in</button>
    </div>
    <p class="sub" style="margin:14px 0 0;"><a href="/" style="color:var(--violet); text-decoration:none;">&larr; Back to Breeze Studio</a></p>
  </div>
</div>
<script>
const NEXT = {json.dumps(next_url)};
async function doLogin() {{
  const email = document.getElementById("liEmail").value.trim();
  const password = document.getElementById("liPass").value;
  const st = document.getElementById("liStatus");
  st.textContent = "";
  try {{
    const r = await fetch("/api/auth/login", {{method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify({{email, password}})}});
    const d = await r.json().catch(() => ({{}}));
    if (!r.ok) throw new Error(d.message || "Sign-in failed.");
    window.location.href = NEXT || "/";
  }} catch (e) {{ st.textContent = e.message; }}
}}
document.getElementById("liGo").addEventListener("click", doLogin);
document.getElementById("liPass").addEventListener("keydown", e => {{ if (e.key === "Enter") doLogin(); }});
</script>
</body>
</html>"""


def render_page():
    if MCP.provisioned:
        badge = '<span class="badge live"><span class="badge-dot"></span> MCP Gateway Connected</span>'
        notice = ""
    else:
        badge = '<span class="badge warn"><span class="badge-dot"></span> MCP Key Unprovisioned</span>'
        notice = f"""<div class="notice"><strong>Configuration note:</strong> The gateway key file was not found at <code>{html.escape(KEY_FILE)}</code>. Once added, live media tools will connect automatically.</div>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Breeze Studio - Quantum Voice & Media</title>
<style>{CSS}</style>
<script crossorigin src="https://unpkg.com/react@18.3.1/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js"></script>
</head>
<body>
<div class="wrap">
  <header>
    <div class="header-row">
      <div>
        <h1>Breeze Studio</h1>
        <p>Quantum MCP Voice & Media Studio &mdash; Breeze text-to-speech synthesis &amp; Nebula generative workflows.</p>
      </div>
      <div class="badges">
        {badge}
        <span class="badge brand"><span class="badge-dot"></span> Tritium GPU</span>
        <span class="badge"><span class="badge-dot"></span> Tailnet Only</span>
      </div>
    </div>
    <div class="auth-area" id="authArea"><span class="auth-note">Checking sign-in...</span></div>
    <nav class="tabs-nav">
      <button type="button" class="tab-btn active" data-target="tab-tts">🎙️ TTS Studio</button>
      <button type="button" class="tab-btn" data-target="tab-creator">✨ Voice Creator</button>
      <button type="button" class="tab-btn" data-target="tab-nebula">🌌 Nebula Workflows</button>
      <button type="button" class="tab-btn" data-target="tab-history">📜 History</button>
    </nav>
  </header>
  {notice}

  <!-- TAB 1: TTS STUDIO -->
  <main id="tab-tts" class="tab-panel active">
    <section class="card">
      <h2>Breeze &mdash; Text to Speech Studio</h2>
      <p class="sub">Synthesize natural speech using high-fidelity Breeze voice models running on Tritium's dedicated GPU queue.</p>
      
      <div class="row">
        <div>
          <label for="bVoice">Voice Profile</label>
          <select id="bVoice"><option>Loading voices...</option></select>
          <div class="char-info" style="margin-top:4px;"><span id="bVoiceInfo">Checking models...</span></div>
        </div>
      </div>

      <label for="bText" style="margin-top:16px;">Text to Speak</label>
      <textarea id="bText" maxlength="2000" placeholder="Type or paste the text you want the voice to read aloud..."></textarea>
      <div class="char-info">
        <span style="font-size:11px;color:var(--mut);">Maximum 2,000 characters per render job</span>
        <span id="bCount">0 / 2000 characters</span>
      </div>

      <div class="chips-wrap">
        <div class="chips-label">Sample Passages</div>
        <div class="chips" id="textChips"></div>
      </div>

      <label for="bInstruction" style="margin-top:16px;">
        Direction / Tone Instruction <span style="color:var(--mut);font-weight:400">(optional)</span>
      </label>
      <input type="text" id="bInstruction" placeholder="e.g. warm and conversational, slight smile, calm unhurried pace">

      <div class="chips-wrap">
        <div class="chips-label">Tone &amp; Style Presets</div>
        <div class="chips" id="dirChips"></div>
      </div>

      <div class="btn-row">
        <button class="primary" id="bGo">
          <span>Generate Voice</span>
        </button>
        <button class="secondary" id="bCancel" style="display:none;">Cancel Job</button>
      </div>

      <div class="status" id="bStatus"></div>
      <div class="bar" id="bBar"><i id="bFill"></i></div>

      <div class="player-box" id="bPlayerBox" style="display:none;">
        <div class="player-header">
          <span>Rendered Audio Preview</span>
          <span style="color:var(--ok);font-weight:600;">Ready</span>
        </div>
        <div id="bPlayer"></div>
        <div class="player-actions">
          <a class="dl-link" id="bDl" href="#">⬇ Download MP3</a>
        </div>
      </div>
    </section>
  </main>

  <!-- TAB 2: VOICE CREATOR -->
  <main id="tab-creator" class="tab-panel">
    <section class="card" id="nvCard">
      <h2>New Voice &mdash; Design &amp; Freeze</h2>
      <p class="sub">Describe vocal characteristics in plain English, render a sample clone reference line, and save the profile permanently into Tritium's catalogue.</p>
      
      <div class="info-banner" id="nvGate">Checking creation authorization...</div>

      <div class="row">
        <div>
          <label for="nvToken">
            Creator Token <span style="font-weight:400;color:var(--mut);">(break-glass - not needed when signed in with a creator account)</span>
          </label>
          <input type="password" id="nvToken" placeholder="Enter creator authorization token" autocomplete="off">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">
            <label style="display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:400;margin:0;cursor:pointer;">
              <input type="checkbox" id="nvRemember"> Remember in this browser
            </label>
            <span class="badge" id="nvTokenBadge"><span class="badge-dot"></span> Checking...</span>
          </div>
        </div>
        <div>
          <label for="nvName">Voice Slug Name</label>
          <input type="text" id="nvName" maxlength="40" placeholder="e.g. calm-narrator, deep-scotty">
          <div class="char-info"><span>Lowercase alphanumeric &amp; hyphens only (max 40)</span></div>
        </div>
      </div>

      <label for="nvDesc" style="margin-top:16px;">Voice Description &amp; Characteristics</label>
      <textarea id="nvDesc" maxlength="1000" placeholder="Describe the voice: age, warmth, pacing, pitch, vocal fry, energy, accent..."></textarea>
      
      <div class="chips-wrap">
        <div class="chips-label">Description Presets</div>
        <div class="chips" id="nvDescChips"></div>
      </div>

      <label for="nvSample" style="margin-top:16px;">Clone Sample Line</label>
      <textarea id="nvSample" maxlength="320" style="min-height:60px;">Hello! This is a brand new Breeze voice, designed and saved through Breeze Studio.</textarea>
      <div class="char-info">
        <span style="font-size:11px;color:var(--mut);">Used as the permanent clone reference waveform</span>
        <span id="nvSampleCount">0 / 320 characters</span>
      </div>

      <div class="row" style="margin-top:4px;">
        <div>
          <label for="nvSeed">Design Seed <span style="font-weight:400;color:var(--mut)">(optional)</span></label>
          <input type="number" id="nvSeed" min="0" max="2147483647" step="1" placeholder="Blank = engine default">
          <div class="char-info"><span>Reproducibility seed for the design engine; each render reports whether the seed was honored.</span></div>
        </div>
        <div>
          <label aria-hidden="true">&nbsp;</label>
          <button type="button" class="secondary" id="nvSeedDice">&#127922; Random seed</button>
        </div>
      </div>

      <div class="btn-row">
        <button class="primary" id="nvGo">Render Sample</button>
        <button class="secondary" id="nvSave" disabled>Save &amp; Register Voice</button>
      </div>

      <div class="status" id="nvStatus"></div>
      <div class="bar" id="nvBar"><i id="nvFill"></i></div>

      <div class="player-box" id="nvPlayerBox" style="display:none;">
        <div class="player-header">
          <span>Voice Sample Preview</span>
          <span style="color:var(--ok);font-weight:600;">Sample Ready</span>
        </div>
        <div id="nvPlayer"></div>
      </div>
    </section>
  </main>

  <!-- TAB 3: NEBULA WORKFLOWS -->
  <main id="tab-nebula" class="tab-panel">
    <section class="card">
      <h2>Nebula &mdash; Generative Media Workflows</h2>
      <p class="sub">Run ComfyUI image, video, 3D, and audio generation pipelines on Tritium's local compute engines.</p>

      <div class="row">
        <div>
          <label for="nWorkflow">Pipeline Workflow</label>
          <select id="nWorkflow"><option>Loading workflows...</option></select>
        </div>
        <div>
          <label for="nBackend">Compute Backend</label>
          <select id="nBackend">
            <option value="nvidia">NVIDIA &mdash; RTX 2060 Super</option>
            <option value="amd">AMD &mdash; Radeon 890M</option>
          </select>
        </div>
      </div>

      <label for="nPrompt" style="margin-top:16px;">
        Prompt Override <span style="color:var(--mut);font-weight:400">(optional)</span>
      </label>
      <input type="text" id="nPrompt" placeholder="Describe the desired image, scene, or artistic style...">
      <div class="char-info" id="nPromptNote" style="margin-top:6px;">Detecting target node...</div>

      <div class="btn-row">
        <button class="primary" id="nGo">Run Workflow</button>
      </div>

      <div class="status" id="nStatus"></div>
      <div class="outputs" id="nOutputs"></div>
    </section>
  </main>

  <!-- TAB 4: HISTORY -->
  <main id="tab-history" class="tab-panel">
    <section class="card">
      <h2>
        <span>Generation History</span>
        <button type="button" class="danger-text" onclick="clearAllHistory()">Clear History</button>
      </h2>
      <p class="sub">Audio clips generated during your sessions, saved in your local browser storage for easy playback and download.</p>
      <div class="hist" id="histList"></div>
    </section>
  </main>

  <footer>
    <strong>Breeze Studio</strong> &mdash; Quantum MCP Media Interface &bull; Private &amp; Tailnet-Only &bull; Hosted on Tritium.
  </footer>
</div>
<script>{JS}</script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json; charset=utf-8")

    def _mcp_json(self, fn):
        try:
            self._json(200, fn())
        except McpNotProvisioned as e:
            self._json(503, {"ok": False, "error": "mcp_not_provisioned",
                             "message": str(e)})
        except McpError as e:
            self._json(502, {"ok": False, "error": "mcp_error",
                             "message": str(e)})
        except Exception as e:  # fail visibly, never hang
            self._json(500, {"ok": False, "error": "server_error",
                             "message": str(e)[:300]})

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    # -- GET --
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            try:
                self._send(200, render_page(), "text/html; charset=utf-8")
            except Exception as exc:
                self._send(500, f"<h1>Page error</h1><pre>{html.escape(str(exc))}</pre>",
                           "text/html; charset=utf-8")
        elif path == "/login":
            nxt = (parse_qs(parsed.query).get("next") or ["/"])[0]
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = "/"
            self._send(200, render_login_page(nxt),
                       "text/html; charset=utf-8")
        elif path == "/api/auth/me":
            claims = _session_claims(self)
            self._json(200, {"ok": True,
                             "signed_in": claims is not None,
                             "email": (claims or {}).get("email"),
                             "role": (claims or {}).get("role"),
                             "can_create": _can_create(claims),
                             "auth_available": _auth() is not None})
        elif path == "/healthz":
            self._send(200, "ok", "text/plain")
        elif path == "/api/voices":
            self._mcp_json(lambda: MCP.call("quantum_breeze_list_voices", {}))
        elif path == "/api/creator/status":
            claims = _session_claims(self)
            self._json(200, {"ok": True,
                             "provisioned": CREATOR.provisioned,
                             "token_set": _creator_token() is not None,
                             "signed_in": claims is not None,
                             "email": (claims or {}).get("email"),
                             "role": (claims or {}).get("role"),
                             "can_create": _can_create(claims)})
        elif path == "/api/workflows":
            self._mcp_json(lambda: MCP.call("quantum_nebula_list_workflows", {}))
        elif path == "/api/workflow_prompt":
            wf = (parse_qs(parsed.query).get("workflow") or [""])[0]
            self._mcp_json(lambda: {"ok": True, "workflow": wf,
                                    "prompt_param": prompt_param_for(wf)})
        elif path.startswith("/api/breeze/status/"):
            job_id = unquote(path[len("/api/breeze/status/"):])
            if not JOB_ID_RE.match(job_id):
                self._json(400, {"ok": False, "error": "bad job id"})
            else:
                self._mcp_json(lambda: MCP.call("quantum_breeze_status",
                                                {"job_id": job_id}))
        elif path.startswith("/api/breeze/result/"):
            job_id = unquote(path[len("/api/breeze/result/"):])
            if not JOB_ID_RE.match(job_id):
                self._json(400, {"ok": False, "error": "bad job id"})
            else:
                def _result():
                    res = MCP.call("quantum_breeze_result", {"job_id": job_id})
                    if res.get("file"):
                        remember_audio(job_id, res["file"])
                    return res
                self._mcp_json(_result)
        elif path.startswith("/api/nebula/status/"):
            pid = unquote(path[len("/api/nebula/status/"):])
            if not JOB_ID_RE.match(pid):
                self._json(400, {"ok": False, "error": "bad prompt id"})
            else:
                self._mcp_json(lambda: MCP.call("quantum_nebula_status",
                                                {"prompt_id": pid}))
        elif path.startswith("/audio/"):
            self._serve_audio(unquote(path[len("/audio/"):]))
        elif path.startswith("/nebula_output/"):
            self._serve_nebula(unquote(path[len("/nebula_output/"):]))
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_audio(self, job_id):
        if not JOB_ID_RE.match(job_id):
            self.send_response(404)
            self.end_headers()
            return
        p = audio_path_for(job_id)
        if not p:
            self._json(404, {"ok": False, "error": "audio_not_found",
                             "message": "No MP3 on disk for that job."})
            return
        try:
            data = p.read_bytes()
        except OSError:
            self._json(404, {"ok": False, "error": "audio_not_found",
                             "message": "No MP3 on disk for that job."})
            return
        self._send(200, data, "audio/mpeg",
                   {"Content-Disposition": f'inline; filename="{job_id}.mp3"'})

    def _serve_nebula(self, filename):
        p = locate_nebula_output(filename)
        if not p:
            self._json(404, {"ok": False, "error": "output_not_found",
                             "message": "That output file could not be located "
                                        "under the Nebula output folders."})
            return
        try:
            data = p.read_bytes()
        except OSError:
            self._json(404, {"ok": False, "error": "output_not_found",
                             "message": "That output file could not be read."})
            return
        ctype = CTYPES.get(p.suffix.lower(), "application/octet-stream")
        disp = "inline" if p.suffix.lower() in IMG_EXTS else "attachment"
        self._send(200, data, ctype,
                   {"Content-Disposition": f'{disp}; filename="{p.name}"'})

    # -- Solorion sign-in --
    def _auth_login(self):
        auth = _auth()
        if auth is None:
            self._json(503, {"ok": False, "error": "auth_unavailable",
                             "message": "The Solorion auth module is not "
                                        "available on this host."})
            return
        payload = self._read_body()
        if payload is None:
            self._json(400, {"ok": False, "error": "invalid JSON body"})
            return
        email = str(payload.get("email") or "").strip()
        password = str(payload.get("password") or "")
        if not email or not password:
            self._json(400, {"ok": False, "error": "bad_credentials",
                             "message": "Email and password are required."})
            return
        try:
            res = auth.authenticate(email, password, AUTH_SERVICE,
                                    ip=self.client_address[0],
                                    user_agent=self.headers.get("User-Agent"))
        except Exception as e:
            self._json(500, {"ok": False, "error": "server_error",
                             "message": str(e)[:200]})
            return
        if not res.get("success"):
            self._json(401, {"ok": False, "error": "login_failed",
                             "message": res.get("error") or "Sign-in failed."})
            return
        user = res.get("user") or {}
        raw_services = user.get("services_allowed")
        if isinstance(raw_services, str):
            try:
                services = json.loads(raw_services or "[]")
            except json.JSONDecodeError:
                services = []
        else:
            services = raw_services or []
        claims = {"role": user.get("role"), "services": services}
        cookie = (f"{SESSION_COOKIE}={res['token']}; Path=/; Max-Age=86400; "
                  "HttpOnly; SameSite=Lax")
        if (self.headers.get("X-Forwarded-Proto") or "").lower() == "https":
            cookie += "; Secure"
        self._send(200, json.dumps({"ok": True,
                                    "email": user.get("email"),
                                    "role": user.get("role"),
                                    "can_create": _can_create(claims)}),
                   "application/json; charset=utf-8",
                   {"Set-Cookie": cookie})

    # -- voice creation (creator-gated) --
    def _creator_gate(self):
        """None when the caller may create voices, else (code, obj).

        Authorization, in order:
        1. A Solorion (dsect-auth) session whose user holds the creation
           permission - admin role, or a "breeze-creator" services grant.
           Permitted users never type the token.
        2. Break-glass: the shared creator token typed into the form,
           compared here against the token file on Tritium, backed by the
           scoped breeze-creator gateway key when CREATOR.call runs (the
           hub refuses the demo key for these tools).
        """
        claims = _session_claims(self)
        if _can_create(claims):
            return None
        expected = _creator_token()
        given = self.headers.get("X-Creator-Token") or ""
        if expected is not None and given and hmac.compare_digest(given, expected):
            return None
        if given:
            return 403, {"ok": False, "error": "creator_unauthorized",
                         "message": "That creator token does not match."}
        if claims is not None:
            return 403, {"ok": False, "error": "creator_forbidden",
                         "message": "You are signed in, but your account "
                                    "does not have voice-creation permission."}
        if expected is None and _auth() is None:
            return 503, {"ok": False, "error": "creator_token_not_set",
                         "message": "No creator token is provisioned on "
                                    "Tritium yet, so voice creation is locked."}
        return 401, {"ok": False, "error": "login_required",
                     "message": "Sign in with a Solorion account that has "
                                "voice-creation permission, or present the "
                                "creator token."}

    def _creator_post(self, path):
        gate = self._creator_gate()
        if gate:
            self._json(gate[0], gate[1])
            return
        payload = self._read_body()
        if payload is None:
            self._json(400, {"ok": False, "error": "invalid JSON body"})
            return
        if path == "/api/voices/design":
            instruction = str(payload.get("instruction") or "").strip()
            sample = str(payload.get("sample_text") or "").strip()
            if not instruction or len(instruction) > 1000:
                self._json(400, {"ok": False, "error": "bad_instruction",
                                 "message": "Describe the voice (max 1000 chars)."})
                return
            if not sample or len(sample) > 320:
                self._json(400, {"ok": False, "error": "bad_sample_text",
                                 "message": "A sample line is required (max 320 "
                                            "chars - it becomes the clone reference)."})
                return
            seed = payload.get("seed")
            if seed is not None:
                try:
                    seed = int(seed)
                except (TypeError, ValueError):
                    self._json(400, {"ok": False, "error": "bad_seed",
                                     "message": "Seed must be an integer."})
                    return
                if seed < 0 or seed > 2147483647:
                    self._json(400, {"ok": False, "error": "bad_seed",
                                     "message": "Seed must be between 0 and "
                                                "2147483647."})
                    return
            args = {"instruction": instruction, "sample_text": sample}
            if seed is not None:
                args["seed"] = seed

            def _design():
                res = CREATOR.call("quantum_breeze_design_voice", args)
                if seed is not None:
                    # The engine (breeze-cli) accepts --seed, but the hub
                    # design tool does not forward it yet, so today the
                    # seed is recorded and forwarded but NOT honored. Say
                    # so plainly instead of pretending (TRK-0591).
                    res = dict(res)
                    res["seed_requested"] = seed
                    res["seed_honored"] = False
                    res["seed_note"] = ("Seed forwarded, but the hub design "
                                        "tool does not pass --seed to "
                                        "breeze-cli yet; this sample was "
                                        "rendered with the engine default.")
                return res
            self._mcp_json(_design)
        else:  # /api/voices/save
            design_job_id = str(payload.get("design_job_id") or "").strip()
            name = str(payload.get("name") or "").strip()
            if not JOB_ID_RE.match(design_job_id):
                self._json(400, {"ok": False, "error": "bad_design_job_id",
                                 "message": "Render a sample first."})
                return
            if not name:
                self._json(400, {"ok": False, "error": "bad_name",
                                 "message": "Name the voice."})
                return
            self._mcp_json(lambda: CREATOR.call(
                "quantum_breeze_save_voice",
                {"design_job_id": design_job_id, "name": name}))

    # -- POST --
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/auth/login":
            self._auth_login()
        elif path == "/api/auth/logout":
            self._send(200, json.dumps({"ok": True}),
                       "application/json; charset=utf-8",
                       {"Set-Cookie": f"{SESSION_COOKIE}=; Path=/; Max-Age=0; "
                                        "HttpOnly; SameSite=Lax"})
        elif path in ("/api/voices/design", "/api/voices/save"):
            self._creator_post(path)
        elif path == "/api/breeze/generate":
            payload = self._read_body()
            if payload is None:
                self._json(400, {"ok": False, "error": "invalid JSON body"})
                return
            text = str(payload.get("text") or "").strip()
            voice = str(payload.get("voice") or "").strip()
            instruction = str(payload.get("instruction") or "").strip()
            if not text or len(text) > 20000:
                self._json(400, {"ok": False, "error": "bad_text",
                                 "message": "Text is required (max 20000 chars)."})
                return
            if not voice or not JOB_ID_RE.match(voice.replace("-", "x")):
                self._json(400, {"ok": False, "error": "bad_voice",
                                 "message": "Pick a voice."})
                return
            args = {"text": text, "voice": voice}
            if instruction:
                args["instruction"] = instruction
            self._mcp_json(lambda: MCP.call("quantum_breeze_generate", args))
        elif path == "/api/nebula/generate":
            payload = self._read_body()
            if payload is None:
                self._json(400, {"ok": False, "error": "invalid JSON body"})
                return
            workflow = str(payload.get("workflow") or "").strip()
            backend = payload.get("backend")
            prompt = str(payload.get("prompt") or "").strip()
            if not workflow or len(workflow) > 300:
                self._json(400, {"ok": False, "error": "bad_workflow",
                                 "message": "Pick a workflow."})
                return
            args = {"workflow": workflow}
            if backend in ("nvidia", "amd"):
                args["backend"] = backend
            def _gen():
                if prompt:
                    target = prompt_param_for(workflow)
                    if target:
                        args["overrides"] = [{"node": target["node"],
                                              "key": target["key"],
                                              "value": prompt}]
                return MCP.call("quantum_nebula_generate", args)
            self._mcp_json(_gen)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):  # keep the journal quiet
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
