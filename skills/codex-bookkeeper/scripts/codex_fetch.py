#!/usr/bin/env python3
"""codex_fetch.py — checksum-verified retrieval of Quantum Codex files.

Why this exists
---------------
``quantum_codex_read`` serves a Codex file in line-paged chunks and reports
the file's true ``sha256`` and byte count alongside the text. Reassembling
those chunks naively is *not* byte-safe, in two independent ways (both
root-caused live on 2026-10-19 against a byte-exact base64 ground truth):

* Chunk contents are their lines joined with "\\n" and carry **no trailing
  newline**, so plain concatenation loses one byte per chunk boundary —
  on 2026-10-18 a 13,179-byte script
  (``Skills/codex-bookkeeper/scripts/codex_lint.py``) came back as exactly
  13,177 bytes that way.
* The server's paging **offset dialect is not stable across sessions**:
  in some sessions the request offset behaves as a 0-based split-line
  index, in others as a 1-based line number (0 clamped to line 1), and
  the ``next`` hint follows the response offset rather than the slice —
  so naive paging duplicates or drops a line at every chunk boundary
  (one paged read of the same file came back ~13,071 bytes). This tool
  runs each dialect as a whole sequence and lets the oracle judge.

The text *looks* right while being wrong, which is the worst kind of wrong
for code you are about to run or restore. The correct client behaviour —
advance by lines actually returned, join chunks with a single "\\n" — is
baked into this tool, and the sha256 oracle proves it on every fetch.

This tool treats the server-reported sha256 as an oracle:

1. Fetch the file chunk by chunk (sequentially — parallel bridge calls
   supersede each other's session).
2. Try a small, deterministic set of reassembly strategies
   (join-with-newline, join+trailing-newline, raw concatenation, ...).
3. Accept only a candidate whose sha256 *and* byte count match the oracle.
   Write the output file (atomically) only on a verified match.
4. If paging cannot produce a verified match, fall back to a byte-exact
   base64 transport (``dev_shell`` running ``base64 -w0`` on Tritium,
   where the vault lives at ``/home/scott/codex``) and verify that
   against the same oracle.
5. If no transport verifies, fail loudly with per-candidate diagnostics
   and write nothing.

Stdlib only. Transports are injectable, so the whole verification core is
unit-testable without a live bridge.

Usage
-----
    python3 codex_fetch.py Skills/codex-bookkeeper/scripts/codex_lint.py \\
        -o /tmp/codex_lint.py
    python3 codex_fetch.py <codex-path> --verify-only --json
    python3 codex_fetch.py <codex-path> -o out.py --transport base64

Exit codes: 0 = fetched and verified, 1 = verification failed on every
transport, 2 = usage / transport error.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

DEFAULT_MCP_SCRIPT = os.path.expanduser(
    "~/workspace/custom-connectors/custom.legacy-tritium-mcp/bin/mcp.py"
)
DEFAULT_VAULT_ROOT = "/home/scott/codex"
DEFAULT_CHUNK_LINES = 200
MAX_CHUNKS = 10_000  # sanity ceiling; a runaway pager must not loop forever


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class FetchError(Exception):
    """Transport-level failure (bridge down, file missing, bad reply)."""


class VerificationError(FetchError):
    """Bytes were fetched but no candidate matched the sha256 oracle."""

    def __init__(self, message: str, diagnostics: list[dict] | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or []


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class Chunk:
    content: str
    offset: int          # 1-based offset of the first line, as reported
    lines: int
    truncated: bool
    sha256: str          # oracle: sha256 of the *whole* file
    total_bytes: int     # oracle: byte size of the whole file
    total_lines: int
    next_offset: int | None = None  # parsed from the server's "next" hint


@dataclass
class FetchResult:
    data: bytes
    sha256: str
    total_bytes: int
    total_lines: int
    strategy: str        # reassembly strategy that verified, or "base64"
    transport: str       # transport that produced the verified bytes
    chunks: int


# --------------------------------------------------------------------------
# Reassembly strategies
# --------------------------------------------------------------------------

def _candidates(chunk_texts: list[str]):
    """Yield (strategy_name, text) reassembly candidates, best first.

    The server joins the lines inside one chunk with "\\n" and emits no
    trailing newline for the chunk, so the historically correct repair is
    joining chunks with a single "\\n". Whether the file itself ends with
    a newline is unknowable from the chunks — the sha256 oracle decides.
    Raw concatenation is included for transports that do preserve chunk
    trailing newlines. Candidates are deduplicated, order-stable.
    """
    seen: set[str] = set()

    def emit(name: str, text: str):
        if text not in seen:
            seen.add(text)
            return name, text
        return None

    joined = "\n".join(chunk_texts)
    concat = "".join(chunk_texts)
    raw = [
        ("join-newline", joined),
        ("join-newline+trailing", joined + "\n"),
        ("concat", concat),
        ("concat+trailing", concat + "\n"),
    ]
    for name, text in raw:
        got = emit(name, text)
        if got is not None:
            yield got


def reassemble_verified(chunks: list[Chunk]) -> tuple[bytes, str, list[dict]]:
    """Return (data, strategy, diagnostics); raise VerificationError."""
    if not chunks:
        raise VerificationError("no chunks fetched")
    oracle_sha = chunks[0].sha256
    oracle_bytes = chunks[0].total_bytes
    # Every chunk must agree on the oracle; a mid-fetch file change would
    # otherwise mix two versions into one plausible-looking file.
    for c in chunks[1:]:
        if c.sha256 != oracle_sha or c.total_bytes != oracle_bytes:
            raise VerificationError(
                "oracle changed mid-fetch (file modified while reading?): "
                f"first chunk sha {oracle_sha[:12]}… vs later {c.sha256[:12]}…"
            )
    diagnostics: list[dict] = []
    for name, text in _candidates([c.content for c in chunks]):
        data = text.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        diagnostics.append(
            {"strategy": name, "bytes": len(data), "sha256": digest,
             "match": digest == oracle_sha and len(data) == oracle_bytes}
        )
        if digest == oracle_sha and len(data) == oracle_bytes:
            return data, name, diagnostics
    raise VerificationError(
        f"no reassembly strategy matched the oracle "
        f"(expected {oracle_bytes} bytes, sha256 {oracle_sha})",
        diagnostics=diagnostics,
    )


# --------------------------------------------------------------------------
# Transports
# --------------------------------------------------------------------------

class PagedTransport:
    """Reads via quantum_codex_read chunks. Name used in reports."""

    name = "paged"

    def fetch_chunk(self, path: str, offset: int, limit: int) -> Chunk:
        raise NotImplementedError

    def _fetch_sequence(self, path: str, chunk_lines: int,
                        start_offset: int) -> list[Chunk]:
        chunks: list[Chunk] = []
        offset = start_offset
        while True:
            if len(chunks) >= MAX_CHUNKS:
                raise FetchError(f"exceeded {MAX_CHUNKS} chunks for {path}")
            chunk = self.fetch_chunk(path, offset, chunk_lines)
            chunks.append(chunk)
            if not chunk.truncated:
                break
            if chunk.lines == 0:
                raise FetchError("server returned a truncated empty chunk; "
                                 "cannot advance the pager")
            # Advance by the lines actually returned. Do NOT follow the
            # server's `next` hint: verified live 2026-10-19, following it
            # loses a whole line at chunk boundaries in one dialect and
            # duplicates one in the other.
            offset += chunk.lines
        return chunks

    def fetch_verified(self, path: str, chunk_lines: int) -> FetchResult:
        # The server's paging dialect is not stable across sessions
        # (observed live 2026-10-19): in some sessions the request offset
        # behaves as a 0-based split-line index (start at 0), in others as
        # a 1-based line number with 0 clamped to the first line (start
        # at 1). A sequence mixing dialects duplicates or drops a line at
        # every boundary. So run each dialect as a whole sequence and let
        # the sha256 oracle judge: first sequence that verifies wins.
        errors: list[str] = []
        diagnostics: list[dict] = []
        for start in (0, 1):
            chunks = self._fetch_sequence(path, chunk_lines, start)
            try:
                data, strategy, diags = reassemble_verified(chunks)
            except VerificationError as exc:
                errors.append(f"start-offset {start}: {exc}")
                diagnostics.extend(
                    {**d, "start_offset": start} for d in exc.diagnostics
                )
                continue
            first = chunks[0]
            return FetchResult(
                data=data, sha256=first.sha256,
                total_bytes=first.total_bytes,
                total_lines=first.total_lines,
                strategy=f"{strategy} (start-offset {start})",
                transport=self.name, chunks=len(chunks),
            )
        raise VerificationError(
            "paged reassembly failed in both offset dialects: "
            + "; ".join(errors),
            diagnostics=diagnostics,
        )


class BytesTransport:
    """A transport that returns whole-file bytes directly (e.g. base64).

    Verification still runs against the codex_read oracle, obtained from a
    one-line probe chunk fetched through a PagedTransport.
    """

    name = "bytes"

    def fetch_bytes(self, path: str) -> bytes:
        raise NotImplementedError

    def probe_oracle(self, path: str) -> tuple[str, int, int]:
        raise NotImplementedError

    def fetch_verified(self, path: str, chunk_lines: int = 0) -> FetchResult:
        sha, total_bytes, total_lines = self.probe_oracle(path)
        data = self.fetch_bytes(path)
        digest = hashlib.sha256(data).hexdigest()
        if digest != sha or len(data) != total_bytes:
            raise VerificationError(
                f"{self.name} transport bytes do not match the oracle "
                f"(expected {total_bytes} bytes, sha256 {sha}; "
                f"got {len(data)} bytes, sha256 {digest})",
                diagnostics=[{"strategy": self.name, "bytes": len(data),
                              "sha256": digest, "match": False}],
            )
        return FetchResult(
            data=data, sha256=sha, total_bytes=total_bytes,
            total_lines=total_lines, strategy="exact-bytes",
            transport=self.name, chunks=1,
        )


# --- Bridge-backed transports (the live ones) ------------------------------

def _bridge_call(mcp_script: str, tool: str, args: dict) -> dict:
    """One sequential call through the Tritium MCP bridge CLI."""
    cmd = ["python3", mcp_script, "call", tool, json.dumps(args)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FetchError(f"bridge call {tool} failed to run: {exc}") from exc
    if proc.returncode != 0:
        raise FetchError(
            f"bridge call {tool} exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout)[:400]}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise FetchError(f"bridge call {tool} returned non-JSON: {exc}") from exc
    if payload.get("isError"):
        raise FetchError(f"bridge call {tool} errored: {str(payload)[:400]}")
    structured = payload.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    # Fallback: the text content block carries the same JSON.
    try:
        text = payload["content"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise FetchError(f"bridge call {tool}: no structured content") from exc


def _parse_next_offset(next_hint) -> int | None:
    if not isinstance(next_hint, str):
        return None
    tail = next_hint.rsplit(" ", 1)[-1]
    try:
        return int(tail)
    except ValueError:
        return None


class BridgePagedTransport(PagedTransport):
    name = "paged"

    def __init__(self, mcp_script: str = DEFAULT_MCP_SCRIPT):
        self.mcp_script = mcp_script

    def fetch_chunk(self, path: str, offset: int, limit: int) -> Chunk:
        r = _bridge_call(
            self.mcp_script, "quantum_codex_read",
            {"path": path, "offset": offset, "limit": limit},
        )
        if not r.get("ok"):
            raise FetchError(f"quantum_codex_read not ok for {path}: "
                             f"{str(r)[:300]}")
        return Chunk(
            content=r["content"],
            offset=int(r["offset"]),
            lines=int(r["lines"]),
            truncated=bool(r["truncated"]),
            sha256=str(r["sha256"]),
            total_bytes=int(r["bytes"]),
            total_lines=int(r["totalLines"]),
            next_offset=_parse_next_offset(r.get("next")),
        )


class BridgeBase64Transport(BytesTransport):
    """Byte-exact fallback: base64 of the file, run on Tritium itself."""

    name = "base64"

    def __init__(self, mcp_script: str = DEFAULT_MCP_SCRIPT,
                 vault_root: str = DEFAULT_VAULT_ROOT,
                 probe: PagedTransport | None = None):
        self.mcp_script = mcp_script
        self.vault_root = vault_root.rstrip("/")
        self._probe = probe or BridgePagedTransport(mcp_script)

    def probe_oracle(self, path: str) -> tuple[str, int, int]:
        chunk = self._probe.fetch_chunk(path, 0, 1)
        return chunk.sha256, chunk.total_bytes, chunk.total_lines

    def fetch_bytes(self, path: str) -> bytes:
        validate_codex_path(path)
        remote = f"{self.vault_root}/{path}"
        command = f"base64 -w0 {shlex.quote(remote)}"
        r = _bridge_call(self.mcp_script, "dev_shell", {"command": command})
        if not r.get("ok") or r.get("exitCode") != 0:
            raise FetchError(
                f"dev_shell base64 failed for {remote}: "
                f"exit={r.get('exitCode')} stderr={str(r.get('stderr'))[:300]}"
            )
        if r.get("stdoutTruncated"):
            raise FetchError(
                "dev_shell base64 output was truncated by the bridge; "
                "file too large for this transport"
            )
        b64 = "".join(str(r.get("stdout", "")).split())
        try:
            return base64.b64decode(b64, validate=True)
        except ValueError as exc:
            raise FetchError(f"base64 decode failed: {exc}") from exc


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def validate_codex_path(path: str) -> str:
    if not path or path.startswith("/") or path.startswith("~"):
        raise FetchError(f"codex path must be vault-relative: {path!r}")
    parts = path.replace("\\", "/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise FetchError(f"codex path must not contain empty/dot/dotdot "
                         f"segments: {path!r}")
    return path


def fetch_with_fallback(transports: list, path: str,
                        chunk_lines: int) -> FetchResult:
    """Try transports in order; return the first *verified* result.

    A transport that fetches bytes failing verification does not stop the
    chain — the next transport gets its chance. All failures are reported
    together if none verifies.
    """
    validate_codex_path(path)
    failures: list[str] = []
    diagnostics: list[dict] = []
    for transport in transports:
        try:
            if isinstance(transport, BytesTransport):
                return transport.fetch_verified(path)
            return transport.fetch_verified(path, chunk_lines)
        except VerificationError as exc:
            failures.append(f"[{transport.name}] {exc}")
            diagnostics.extend(
                {**d, "transport": transport.name} for d in exc.diagnostics
            )
        except FetchError as exc:
            failures.append(f"[{transport.name}] {exc}")
    raise VerificationError(
        "no transport produced a verified copy of "
        f"{path}:\n" + "\n".join(failures),
        diagnostics=diagnostics,
    )


def write_atomic(dest: str, data: bytes) -> None:
    folder = os.path.dirname(os.path.abspath(dest))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".codex-fetch-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_transports(kind: str, mcp_script: str,
                     vault_root: str) -> list:
    paged = BridgePagedTransport(mcp_script)
    if kind == "paged":
        return [paged]
    if kind == "base64":
        return [BridgeBase64Transport(mcp_script, vault_root, probe=paged)]
    return [paged, BridgeBase64Transport(mcp_script, vault_root, probe=paged)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="codex_fetch.py",
        description="Fetch a Quantum Codex file with sha256 verification. "
                    "Writes output only when the bytes match the "
                    "server-reported sha256 and size.",
    )
    ap.add_argument("path", help="vault-relative Codex path")
    ap.add_argument("-o", "--output", help="destination file (required "
                                           "unless --verify-only)")
    ap.add_argument("--verify-only", action="store_true",
                    help="fetch and verify, write nothing")
    ap.add_argument("--chunk-lines", type=int, default=DEFAULT_CHUNK_LINES,
                    help=f"lines per paged chunk (default {DEFAULT_CHUNK_LINES})")
    ap.add_argument("--transport", choices=["auto", "paged", "base64"],
                    default="auto",
                    help="auto = paged, falling back to base64 (default)")
    ap.add_argument("--mcp-script", default=DEFAULT_MCP_SCRIPT,
                    help="path to the Tritium bridge mcp.py")
    ap.add_argument("--vault-root", default=DEFAULT_VAULT_ROOT,
                    help="vault root on Tritium for the base64 transport")
    ap.add_argument("--json", action="store_true",
                    help="emit a JSON report instead of human text")
    args = ap.parse_args(argv)

    if not args.verify_only and not args.output:
        ap.error("-o/--output is required unless --verify-only")
    if args.chunk_lines < 1:
        ap.error("--chunk-lines must be >= 1")

    try:
        transports = build_transports(args.transport, args.mcp_script,
                                      args.vault_root)
        result = fetch_with_fallback(transports, args.path, args.chunk_lines)
    except VerificationError as exc:
        report = {"ok": False, "path": args.path, "error": str(exc),
                  "diagnostics": exc.diagnostics}
        print(json.dumps(report, indent=2) if args.json else f"FAIL: {exc}",
              file=sys.stderr if not args.json else sys.stdout)
        return 1
    except FetchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not args.verify_only:
        write_atomic(args.output, result.data)

    report = {
        "ok": True,
        "path": args.path,
        "output": None if args.verify_only else args.output,
        "bytes": result.total_bytes,
        "sha256": result.sha256,
        "lines": result.total_lines,
        "transport": result.transport,
        "strategy": result.strategy,
        "chunks": result.chunks,
        "verified": True,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"OK {args.path}: {result.total_bytes} bytes, "
              f"sha256 {result.sha256[:16]}… verified "
              f"(transport={result.transport}, strategy={result.strategy}, "
              f"chunks={result.chunks})"
              + ("" if args.verify_only else f" -> {args.output}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
