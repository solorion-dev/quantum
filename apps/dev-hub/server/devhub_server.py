#!/usr/bin/env python3
"""Developer Hub — slice 1 backend (TRK-0075).

Single-file Python stdlib server, following the pattern of
apps/breeze-studio/breeze_server.py. Serves the built React app
(apps/dev-hub/dist) and same-origin, read-only JSON:

  GET /api/session      caller identity (tailnet whois + allowlist)
  GET /api/fleet/status live fleet aggregate (see sources object)

Auth model (mirrors hub-api docs/auth.md): being on the tailnet is the
credential. For a non-loopback peer the login is resolved with
`tailscale whois --json <peer_ip>` and checked against
server/allowed_logins.txt. A missing or empty allowlist admits NOBODY
(fail closed). Preview behaviour: a loopback peer is treated as the box
operator (the first non-comment allowlist entry) so the page can be
verified from the box itself — this is preview-only behaviour and is
documented in the README; the same preview treatment applies to a
self-connection from this host to its own tailnet address (Tritium is
a tagged device, so whois on its own IP returns a device name, not a
user login). Production sits behind `tailscale serve`, which presents
real tailnet peers.

All endpoints are GET-only; POST/PUT/DELETE/PATCH return 405.
Everything here is read-only: systemctl is-active, docker ps, /proc,
df via shutil, and SQLite opened with mode=ro. Nothing mutates the box.

Bind host/port come from DEVHUB_HOST / DEVHUB_PORT. The slice-1 preview
binds the tailnet IP only (100.66.182.7:8420) — never 0.0.0.0.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
APP_DIR = HERE.parent
DIST_DIR = Path(os.environ.get("DEVHUB_DIST", APP_DIR / "dist"))
ALLOWLIST = Path(os.environ.get("DEVHUB_ALLOWLIST", HERE / "allowed_logins.txt"))
HOST = os.environ.get("DEVHUB_HOST", "127.0.0.1")
PORT = int(os.environ.get("DEVHUB_PORT", "8420"))

HUB_API_STATUS = "http://127.0.0.1:8091/api/status"
BOOTCHECK_LATEST = Path("/home/scott/quantum-bootcheck-latest.txt")
TRACKER_DB = Path("/mnt/fast/tracker/tracker.db")
CORE_UNITS = ["dsect-hub-api", "cloudflared-dsect-web", "tailscaled", "docker"]
HTTP_PROBES = [
    ("hub-api", "http://127.0.0.1:8091/"),
    ("jellyfin", "http://127.0.0.1:8100/health"),
    ("nebula", "http://127.0.0.1:8092/"),
    ("webmail", "http://127.0.0.1:8097/"),
    ("embedder", "http://127.0.0.1:8082/health"),
]
DISK_MOUNTS = ["/", "/mnt/fast", "/mnt/mybook"]

CTYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".webmanifest": "application/manifest+json",
    ".txt": "text/plain; charset=utf-8",
    ".map": "application/json",
}


def load_allowlist():
    """Allowlist logins, one per line, '#' comments. Missing/empty -> []."""
    try:
        lines = ALLOWLIST.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def tailscale_whois_login(peer_ip):
    """Resolve a tailnet peer IP to its Tailscale LoginName, or None."""
    try:
        proc = subprocess.run(
            ["tailscale", "whois", "--json", peer_ip],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if proc.returncode != 0:
        return None, None
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return None, None
    profile = data.get("UserProfile") or {}
    if not profile:
        node = data.get("Node") or {}
        profile = node.get("UserProfile") or {}
    login = profile.get("LoginName") or data.get("LoginName")
    name = profile.get("DisplayName")
    return login, name


def caller_identity(peer_ip):
    """Return (identity_dict_or_None, reason). Fail closed."""
    allowlist = load_allowlist()
    if not allowlist:
        return None, "allowlist missing or empty — admitting nobody (fail closed)"
    if peer_ip in ("127.0.0.1", "::1"):
        # Preview behaviour: loopback == the box operator.
        login = allowlist[0]
        return {
            "login": login,
            "name": "Box operator (loopback preview)",
            "source": "loopback-preview",
            "peer": peer_ip,
        }, None
    if HOST not in ("0.0.0.0", "::", "") and peer_ip == HOST:
        # Preview behaviour: a connection from this host to its own
        # tailnet address (e.g. curl / Playwright running on the box
        # itself) is a self-connection — Tailscale authenticates the
        # source, and only local processes can source from this host's
        # own IP. Tritium itself is a *tagged device*, so `tailscale
        # whois` on its own IP returns the device DNS name, not a user
        # login; without this, on-box verification would 401. Real
        # remote peers can never present this host's address.
        login = allowlist[0]
        return {
            "login": login,
            "name": "Box operator (self-tailnet preview)",
            "source": "self-tailnet-preview",
            "peer": peer_ip,
        }, None
    login, name = tailscale_whois_login(peer_ip)
    if not login:
        return None, "could not resolve tailnet identity for peer"
    if login not in allowlist:
        return None, "tailnet login is not on the allowlist"
    return {
        "login": login,
        "name": name,
        "source": "tailscale whois",
        "peer": peer_ip,
    }, None


def run_probe(cmd, timeout=8):
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        latency = round((time.monotonic() - started) * 1000)
        return proc.stdout.strip(), proc.returncode, latency, None
    except subprocess.TimeoutExpired:
        return "", None, round((time.monotonic() - started) * 1000), "timeout"
    except OSError as exc:
        return "", None, round((time.monotonic() - started) * 1000), str(exc)


def http_probe(url, timeout=4):
    started = time.monotonic()
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(4096)
            code = resp.status
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.read(4096) if hasattr(exc, "read") else None
    except (urllib.error.URLError, OSError) as exc:
        return None, round((time.monotonic() - started) * 1000), str(exc)
    return code, round((time.monotonic() - started) * 1000), None


def hub_api_fleet():
    """Try hub-api /api/status first. Return (groups_or_None, source_note)."""
    started = time.monotonic()
    req = urllib.request.Request(HUB_API_STATUS, method="GET")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            raw = resp.read().decode(errors="replace")
            code = resp.status
    except urllib.error.HTTPError as exc:
        return None, f"hub-api {HUB_API_STATUS} returned HTTP {exc.code}; fallback probes used"
    except (urllib.error.URLError, OSError) as exc:
        return None, f"hub-api {HUB_API_STATUS} unreachable ({exc}); fallback probes used"
    latency = round((time.monotonic() - started) * 1000)
    if code != 200:
        return None, f"hub-api {HUB_API_STATUS} returned HTTP {code}; fallback probes used"
    try:
        payload = json.loads(raw)
    except ValueError:
        return None, "hub-api /api/status returned non-JSON; fallback probes used"
    services = payload.get("services") if isinstance(payload, dict) else None
    if not isinstance(services, list):
        return None, "hub-api /api/status JSON had no services list; fallback probes used"
    mapped = []
    for svc in services:
        if not isinstance(svc, dict):
            continue
        raw_status = str(svc.get("status", "unknown")).lower()
        status = raw_status if raw_status in ("up", "down", "degraded") else "unknown"
        mapped.append({
            "name": str(svc.get("name", "service")),
            "kind": "hub-api",
            "status": status,
            "latency_ms": svc.get("latency_ms", latency),
            "detail": str(svc.get("detail", "via hub-api")),
        })
    return [{"name": "hub-api", "services": mapped}], f"hub-api {HUB_API_STATUS}"


def fallback_fleet():
    groups = []
    units = []
    for unit in CORE_UNITS:
        out, code, latency, err = run_probe(["systemctl", "is-active", unit], timeout=5)
        active = (code == 0 and out == "active")
        units.append({
            "name": unit,
            "kind": "systemd",
            "status": "up" if active else "down",
            "latency_ms": latency,
            "detail": f"systemctl is-active -> {out or err or 'unknown'}",
        })
    groups.append({"name": "Core systemd units", "services": units})

    containers = []
    out, code, latency, err = run_probe(
        ["docker", "ps", "--format", "{{.Names}}|{{.Status}}"], timeout=10)
    if code == 0 and out:
        for line in out.splitlines():
            if "|" not in line:
                continue
            name, status_text = line.split("|", 1)
            up = status_text.strip().lower().startswith("up")
            healthy_bad = "unhealthy" in status_text.lower()
            containers.append({
                "name": name.strip(),
                "kind": "docker",
                "status": "degraded" if (up and healthy_bad) else ("up" if up else "down"),
                "latency_ms": latency,
                "detail": f"docker ps -> {status_text.strip()}",
            })
    elif err or code != 0:
        containers.append({
            "name": "docker ps",
            "kind": "docker",
            "status": "unknown",
            "latency_ms": latency,
            "detail": f"docker ps failed: {err or 'exit ' + str(code)}",
        })
    groups.append({"name": "Docker containers", "services": containers})

    http_services = []
    for name, url in HTTP_PROBES:
        code, latency, err = http_probe(url)
        if code is None:
            status, detail = "down", f"GET {url} -> {err}"
        elif code in (200, 401, 403):
            # 401/403 still prove the service is up and answering.
            status, detail = "up", f"GET {url} -> HTTP {code}"
        elif code < 500:
            status, detail = "degraded", f"GET {url} -> HTTP {code}"
        else:
            status, detail = "down", f"GET {url} -> HTTP {code}"
        http_services.append({
            "name": name, "kind": "http", "status": status,
            "latency_ms": latency, "detail": detail,
        })
    groups.append({"name": "HTTP services (loopback)", "services": http_services})
    return groups, "fallback probes: systemctl is-active + docker ps + loopback HTTP GETs (hub-api /api/status unavailable)"


def bootcheck_section():
    """Last quantum-bootcheck verdict.

    Surface found by inspecting /usr/local/sbin/quantum-bootcheck.sh
    (read-only): it writes LOG=/var/log/quantum-bootcheck.log and
    LATEST=/home/scott/quantum-bootcheck-latest.txt.
    """
    source = f"quantum-bootcheck latest summary file {BOOTCHECK_LATEST}"
    try:
        text = BOOTCHECK_LATEST.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "verdict": None, "fails": None, "warns": None, "at": None,
            "headline": None, "ok_count": 0, "fail_count": 0, "lines": [],
            "error": str(exc),
        }, source
    lines = [ln for ln in text.splitlines() if ln.strip()]
    headline = lines[0] if lines else None
    verdict, fails, warns, at = None, None, None, None
    if headline:
        m = re.search(r"quantum-bootcheck\s+(\S+\s+\S+)\s+—\s+verdict:\s+(\S+)\s+\(fails=(\d+)\s+warns=(\d+)\)", headline)
        if m:
            at, verdict = m.group(1), m.group(2)
            fails, warns = int(m.group(3)), int(m.group(4))
    ok_count = sum(1 for ln in lines if ln.startswith("OK"))
    fail_count = sum(1 for ln in lines if ln.startswith("FAIL"))
    return {
        "verdict": verdict, "fails": fails, "warns": warns, "at": at,
        "headline": headline, "ok_count": ok_count, "fail_count": fail_count,
        "lines": lines[:80],
    }, source


def host_section():
    uptime_seconds = 0.0
    load = [0.0, 0.0, 0.0]
    try:
        uptime_seconds = float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        pass
    try:
        load = [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]]
    except (OSError, ValueError):
        pass
    mem_total, mem_avail = 0, 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                mem_avail = int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    used_pct = round((1 - mem_avail / mem_total) * 100, 1) if mem_total else 0.0
    disks = []
    for mount in DISK_MOUNTS:
        try:
            usage = shutil.disk_usage(mount)
            disks.append({
                "mount": mount,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "used_pct": round(usage.used / usage.total * 100, 1) if usage.total else 0.0,
            })
        except OSError as exc:
            disks.append({
                "mount": mount, "total_bytes": None, "used_bytes": None,
                "free_bytes": None, "used_pct": None, "error": str(exc),
            })
    try:
        hostname = Path("/etc/hostname").read_text().strip()
    except OSError:
        hostname = "tritium"
    return {
        "hostname": hostname,
        "uptime_seconds": int(uptime_seconds),
        "load": load,
        "memory": {
            "total_bytes": mem_total,
            "available_bytes": mem_avail,
            "used_pct": used_pct,
        },
        "disks": disks,
    }


def tracker_section():
    source = f"sqlite3 read-only {TRACKER_DB} (items grouped by status)"
    try:
        conn = sqlite3.connect(f"file:{TRACKER_DB}?mode=ro", uri=True, timeout=5)
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM items GROUP BY status ORDER BY status"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"total": 0, "by_status": {}, "error": str(exc)}, source
    by_status = {str(status): int(count) for status, count in rows}
    return {"total": sum(by_status.values()), "by_status": by_status}, source


def fleet_status_payload():
    groups, fleet_source = hub_api_fleet()
    if groups is None:
        groups, fallback_note = fallback_fleet()
        fleet_source = fleet_source + " | " + fallback_note
    totals = {"up": 0, "down": 0, "degraded": 0, "unknown": 0}
    for group in groups:
        for svc in group["services"]:
            totals[svc["status"]] = totals.get(svc["status"], 0) + 1
    bootcheck, bootcheck_source = bootcheck_section()
    tracker, tracker_source = tracker_section()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "fleet": fleet_source,
            "bootcheck": bootcheck_source,
            "host": "/proc/uptime, /proc/loadavg, /proc/meminfo, shutil.disk_usage",
            "tracker": tracker_source,
        },
        "bootcheck": bootcheck,
        "fleet": {"groups": groups, "totals": totals},
        "host": host_section(),
        "tracker": tracker,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "DevHub/0.1"

    def log_message(self, fmt, *args):  # keep stdout quiet-ish
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _auth(self):
        identity, reason = caller_identity(self.client_address[0])
        if identity is None:
            self._json(401, {"error": "unauthorized", "detail": reason})
            return None
        return identity

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/session":
            identity = self._auth()
            if identity is not None:
                self._json(200, identity)
            return
        if path == "/api/fleet/status":
            identity = self._auth()
            if identity is None:
                return
            self._json(200, fleet_status_payload())
            return
        if path.startswith("/api/"):
            self._json(404, {"error": "not found", "path": path})
            return
        self._static(path)

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        candidate = (DIST_DIR / path.lstrip("/")).resolve()
        if DIST_DIR.resolve() not in candidate.parents and candidate != DIST_DIR.resolve():
            self._json(403, {"error": "forbidden"})
            return
        if not candidate.is_file():
            # SPA fallback for client-side routes.
            candidate = DIST_DIR / "index.html"
            if not candidate.is_file():
                self._json(503, {"error": "dev-hub dist not built yet — run npm run build in apps/dev-hub"})
                return
        data = candidate.read_bytes()
        ctype = CTYPES.get(candidate.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _method_not_allowed(self):
        self._json(405, {"error": "method not allowed — Developer Hub slice 1 is read-only (GET only)"})

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_PATCH = _method_not_allowed


def main():
    if not DIST_DIR.is_dir():
        print(f"warning: dist dir {DIST_DIR} does not exist yet (API still serves)")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"dev-hub slice 1 listening on http://{HOST}:{PORT} (dist={DIST_DIR}, allowlist={ALLOWLIST})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
