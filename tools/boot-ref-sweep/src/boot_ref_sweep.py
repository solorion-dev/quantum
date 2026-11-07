#!/usr/bin/env python3
"""boot-ref-sweep — pre-removal dangling-reference checker.

Before a drive is wiped, pulled, or decommissioned, sweep every surface
that might still reference its filesystems:

  * /etc/fstab (live) and its backups (classified separately)
  * /etc/crypttab
  * /etc/default/grub and /boot/grub/grub.cfg
  * /etc/kernel/cmdline, dracut config (/etc/dracut.conf, .d/*)
  * systemd *.mount units under /etc/systemd/system and /usr/lib/systemd/system
  * initramfs images under /boot — the CONTENTS are unpacked/scanned,
    because dracut bakes devexists wait-hooks into the image at build
    time (the Oct 24-25 Tritium outage: ghost UUIDs 037a1434 / E1C3-D1B2
    lived only inside Oct 10 initramfs images, satisfied until the
    AirDisk carrying the old /boot+ESP was wiped)
  * an efibootmgr dump (--efibootmgr FILE, or root/var/lib/... text)

Identifiers are matched case-insensitively (vfat UUIDs print upper-case,
configs may carry either case) and may be filesystem UUIDs, PARTUUIDs,
labels, serials, or /dev/disk/by-id fragments.

v2: identifiers can also be harvested from a device inventory instead
of being typed by hand — `--from-device FILE` (or `-` for stdin)
auto-detects an `lsblk -J` JSON dump or a `blkid -o export` dump and
harvests UUID/PARTUUID (uuid-class) plus LABEL/PARTLABEL/SERIAL/WWN
(id-class) from it, optionally restricted to one device's subtree with
`--device NAME`. Harvested identifiers merge with any explicit
`--uuid`/`--id` values (explicit values win on duplicates). A device
file that yields zero identifiers is INCOMPLETE, never a clean verdict:
"sweep nothing, find nothing" must not clear a drive for removal.

v3: `--live-device /dev/<name>` (a bare name such as `sda` is also
accepted) runs `lsblk` itself — read-only — and feeds its JSON output
through the same v2 harvest path, so no pre-captured file is needed.
Every live-probe failure (lsblk missing, non-zero exit, invalid JSON,
device absent from the output, zero identifiers harvested) is
INCOMPLETE with exit 2; a failed probe never falls through to CLEAN.
`--live-device` and `--from-device` are mutually exclusive.

Verdicts:
  BLOCKED    a live (non-backup) surface references an identifier
  INCOMPLETE a surface that should have been scanned could not be
             (e.g. an initramfs whose compression cannot be decoded)
  WARN       references exist only in backup/historical files
  CLEAN      no references anywhere scanned

Exit codes: 0 = CLEAN or WARN, 1 = BLOCKED, 2 = INCOMPLETE or usage error.
Read-only: this tool never writes to the swept root.
"""
from __future__ import annotations

import argparse
import bz2
import gzip
import json
import lzma
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

BACKUP_MARKERS = (".bak", ".old", ".save", "~", "backup", "migration-bak",
                  ".orig", ".dpkg-old", ".ucf-old")

TEXT_SURFACES = [
    ("fstab", "etc/fstab"),
    ("fstab", "etc/fstab.*"),                      # backups / variants
    ("crypttab", "etc/crypttab"),
    ("grub-default", "etc/default/grub"),
    ("grub-config", "boot/grub/grub.cfg"),
    ("grub-config", "boot/grub2/grub.cfg"),
    ("kernel-cmdline", "etc/kernel/cmdline"),
    ("dracut-config", "etc/dracut.conf"),
    ("dracut-config", "etc/dracut.conf.d/*.conf"),
    ("systemd-mount", "etc/systemd/system/*.mount"),
    ("systemd-mount", "usr/lib/systemd/system/*.mount"),
    ("systemd-unit", "etc/systemd/system/*.automount"),
]

INITRAMFS_GLOBS = ["boot/initrd.img-*", "boot/initramfs-*.img",
                   "boot/initrd-*", "boot/initramfs*"]


def is_backup(path: str) -> bool:
    name = os.path.basename(path).lower()
    return any(m in name for m in BACKUP_MARKERS)


@dataclass
class Hit:
    surface: str
    path: str
    identifier: str
    live: bool
    detail: str = ""


# --- device harvesting (--from-device, v2) ------------------------------
SKIP_DEVICE_TYPES = {"loop", "ram", "squashfs"}

# harvest field (lower-case) -> identifier kind; iteration order is the
# harvest order within one device node.
HARVEST_FIELDS = (("uuid", "uuid"), ("partuuid", "uuid"),
                  ("label", "id"), ("partlabel", "id"),
                  ("serial", "id"), ("wwn", "id"))


class HarvestError(Exception):
    """A --from-device source could not be harvested as requested."""


@dataclass
class HarvestedIdentifier:
    value: str
    kind: str               # "uuid" or "id"
    source_device: str
    field: str              # uuid | partuuid | label | partlabel | serial | wwn


def _harvest_add(out: list, seen: set, value, kind: str,
                 source_device: str, field_name: str) -> None:
    if value is None:
        return
    value = str(value).strip()
    if not value:
        return
    key = norm(value)
    if key in seen:
        return
    seen.add(key)
    out.append(HarvestedIdentifier(value, kind, source_device, field_name))


def _device_name(name: str) -> str:
    """Normalise a --device argument: 'sda', '/dev/sda' -> 'sda'."""
    name = str(name).strip()
    return os.path.basename(name) if name.startswith("/") else name


def _walk_lsblk(node: dict):
    """Yield a blockdevices node and its children, depth-first.

    Nodes of a skipped type (loop/ram/squashfs) are pruned together
    with their whole subtree.
    """
    dtype = str(node.get("type") or "").strip().lower()
    if dtype in SKIP_DEVICE_TYPES:
        return
    yield node
    for child in node.get("children") or []:
        if isinstance(child, dict):
            yield from _walk_lsblk(child)


def _find_lsblk_node(nodes: list, wanted: str) -> dict | None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if _device_name(str(node.get("name") or "")) == wanted:
            return node
        found = _find_lsblk_node(node.get("children") or [], wanted)
        if found is not None:
            return found
    return None


def harvest_lsblk(data: dict, device: str | None = None) -> list:
    """Harvest identifiers from parsed `lsblk -J` JSON."""
    roots = data.get("blockdevices")
    if not isinstance(roots, list):
        raise HarvestError("lsblk JSON has no 'blockdevices' list")
    if device:
        wanted = _device_name(device)
        target = _find_lsblk_node(roots, wanted)
        if target is None:
            raise HarvestError(f"unknown device: {device}")
        roots = [target]
    out: list = []
    seen: set = set()
    for root in roots:
        if not isinstance(root, dict):
            continue
        for node in _walk_lsblk(root):
            source = _device_name(str(node.get("name") or ""))
            for field_name, kind in HARVEST_FIELDS:
                _harvest_add(out, seen, node.get(field_name), kind,
                             source, field_name)
    return out


def harvest_blkid(text: str, device: str | None = None) -> list:
    """Harvest identifiers from `blkid -o export` text.

    Blocks are separated by blank lines; each starts with DEVNAME= and
    carries UUID/PARTUUID/LABEL/PARTLABEL key=value lines.
    """
    wanted = _device_name(device) if device else None
    out: list = []
    seen: set = set()
    matched = wanted is None
    for block in re.split(r"\n\s*\n", text):
        fields: dict = {}
        order: list = []
        for line in block.splitlines():
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key not in fields:
                order.append(key)
            fields[key] = val.strip()
        if not fields:
            continue
        devname = fields.get("DEVNAME", "")
        source = _device_name(devname) if devname else ""
        if wanted is not None:
            if source != wanted and devname != device:
                continue
            matched = True
        for field_name, kind in HARVEST_FIELDS:
            if field_name.upper() in fields:
                _harvest_add(out, seen, fields[field_name.upper()], kind,
                             source, field_name)
    if wanted is not None and not matched:
        raise HarvestError(f"unknown device: {device}")
    return out


def harvest_identifiers(text: str, device: str | None = None) -> list:
    """Auto-detect a device inventory dump and harvest identifiers.

    A leading '{' means lsblk JSON; anything else is treated as
    `blkid -o export` text. Raises HarvestError for malformed JSON or
    an unknown --device name.
    """
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except ValueError as exc:
            raise HarvestError(f"malformed lsblk JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise HarvestError("lsblk JSON is not an object")
        return harvest_lsblk(data, device)
    return harvest_blkid(text, device)


# --- live device harvesting (--live-device, v3) -------------------------
LSBLK_COLUMNS = "NAME,UUID,PARTUUID,LABEL,PARTLABEL,SERIAL,WWN,TYPE"


def normalize_live_device(device: str) -> str:
    """Normalise a --live-device argument to a full /dev/ path.

    'sda' -> '/dev/sda'; '/dev/sda' is returned unchanged.
    """
    device = str(device).strip()
    if device.startswith("/"):
        return device
    return "/dev/" + device


def run_lsblk(device_path: str):
    """Run lsblk (read-only) for one device; the injectable seam.

    Returns (returncode, stdout, stderr). Tests monkeypatch this
    module-level function to simulate lsblk without a real device.
    argv list only — never shell=True.
    """
    proc = subprocess.run(
        ["lsblk", "-J", "-o", LSBLK_COLUMNS, device_path],
        capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def harvest_live_device(device: str, runner=None) -> list:
    """Harvest identifiers by running lsblk live on `device`.

    Raises HarvestError with a distinct reason for every failure:
    lsblk missing, lsblk non-zero exit, invalid JSON output, device
    absent from the lsblk output. A successful run may still return
    an empty list — the caller treats zero harvest as INCOMPLETE.
    """
    if runner is None:
        runner = run_lsblk
    device_path = normalize_live_device(device)
    try:
        returncode, stdout, stderr = runner(device_path)
    except FileNotFoundError as exc:
        raise HarvestError(
            "lsblk binary not found: install util-linux or use "
            f"--from-device with a pre-captured dump ({exc})") from exc
    if returncode != 0:
        detail = (stderr or "").strip()
        raise HarvestError(
            f"lsblk exited {returncode} for {device_path}"
            + (f": {detail}" if detail else ""))
    try:
        data = json.loads(stdout)
    except (ValueError, TypeError) as exc:
        raise HarvestError(
            f"lsblk output for {device_path} was not valid JSON: "
            f"{exc}") from exc
    if not isinstance(data, dict) or \
            not isinstance(data.get("blockdevices"), list):
        raise HarvestError(
            f"lsblk output for {device_path} has no 'blockdevices' list")
    wanted = _device_name(device_path)
    if _find_lsblk_node(data["blockdevices"], wanted) is None:
        raise HarvestError(
            f"device {device_path} not present in lsblk output")
    return harvest_lsblk(data, device=wanted)


@dataclass
class Sweep:
    hits: list = field(default_factory=list)
    unverified: list = field(default_factory=list)
    scanned: list = field(default_factory=list)


def norm(s: str) -> str:
    return s.lower()


def find_ids(text: str, identifiers: list[str]) -> list[str]:
    low = norm(text)
    return [i for i in identifiers if norm(i) in low]


def scan_text_file(sweep: Sweep, surface: str, path: str, root: str,
                   identifiers: list[str]) -> None:
    rel = os.path.relpath(path, root)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError as exc:
        sweep.unverified.append(f"{rel}: unreadable ({exc.strerror or exc})")
        return
    sweep.scanned.append(rel)
    live = not is_backup(path)
    for lineno, line in enumerate(content.splitlines(), 1):
        for ident in find_ids(line, identifiers):
            sweep.hits.append(Hit(surface, rel, ident, live,
                                  f"line {lineno}: {line.strip()[:160]}"))


# --- initramfs decoding -------------------------------------------------
GZIP_MAGIC = b"\x1f\x8b"
XZ_MAGIC = b"\xfd7zXZ\x00"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
BZIP2_MAGIC = b"BZh"


def _try_decompress(data: bytes, offset: int) -> bytes | None:
    chunk = data[offset:]
    # decompressobj forms tolerate trailing bytes after the stream
    # (concatenated images / padding), which *.decompress() rejects.
    def _obj(factory):
        d = factory()
        out = d.decompress(chunk)
        return out or None
    import zlib
    for factory in (lambda: zlib.decompressobj(31), lzma.LZMADecompressor,
                    bz2.BZ2Decompressor):
        try:
            out = _obj(factory)
            if out:
                return out
        except Exception:
            pass
    for fn in (gzip.decompress, lzma.decompress, bz2.decompress):
        try:
            return fn(chunk)
        except Exception:
            pass
    # zstd is not in the stdlib (py<3.14); use the CLI when present.
    exe = shutil.which("zstd") or shutil.which("unzstd")
    if exe:
        try:
            out = subprocess.run([exe, "-dc"], input=chunk,
                                 capture_output=True, timeout=120)
            if out.returncode == 0 and out.stdout:
                return out.stdout
        except Exception:
            pass
    return None


def initramfs_searchable_bytes(data: bytes) -> tuple[bytes, bool]:
    """Return (searchable_bytes, fully_decoded).

    Layout: an optional uncompressed early (microcode) cpio, then ONE
    compressed main cpio. Searchable bytes = the raw early-cpio prefix
    plus the decoded main frame — never the raw compressed blob
    (scanning compressed bytes both misses real content and produces
    fragment false-positives, verified on Tritium's live images).

    Candidate frame offsets are tried in increasing order; the first
    decode that yields a substantial payload is the main frame.
    fully_decoded is False when compression magics are present but no
    candidate decoded — the caller must treat the image as unverified,
    never as clean.
    """
    candidates: list[int] = []
    for magic in (GZIP_MAGIC, XZ_MAGIC, ZSTD_MAGIC, BZIP2_MAGIC):
        start = 0
        for _ in range(8):                    # first few per format only
            idx = data.find(magic, start)
            if idx < 0:
                break
            candidates.append(idx)
            start = idx + 1
    if not candidates:
        return data, True                     # plain (uncompressed) cpio
    best: tuple[int, bytes] | None = None
    for idx in sorted(set(candidates)):
        out = _try_decompress(data, idx)
        if out and (best is None or len(out) > len(best[1])):
            best = (idx, out)
    if best is not None:
        return data[:best[0]] + best[1], True
    return data[:min(candidates)], False


def scan_initramfs(sweep: Sweep, path: str, root: str,
                   identifiers: list[str]) -> None:
    rel = os.path.relpath(path, root)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        sweep.unverified.append(f"{rel}: unreadable ({exc.strerror or exc})")
        return
    searchable, complete = initramfs_searchable_bytes(data)
    if not complete:
        sweep.unverified.append(
            f"{rel}: compression present but could not be decoded "
            f"(no gzip/xz/bz2/zstd decoder succeeded) — contents unverified")
        return
    sweep.scanned.append(rel)
    text = searchable.decode("utf-8", errors="ignore")
    live = not is_backup(path)
    for ident in find_ids(text, identifiers):
        # Context: the cpio member name or hook path around the match.
        idx = norm(text).find(norm(ident))
        ctx = text[max(0, idx - 120):idx + len(ident) + 40]
        ctx = " ".join(ctx.split())
        sweep.hits.append(Hit("initramfs", rel, ident, live,
                              f"in image contents near: …{ctx[-170:]}"))


def run(root: str, identifiers: list[str],
        efibootmgr_file: str | None = None) -> Sweep:
    sweep = Sweep()
    seen: set[str] = set()
    import glob as globmod
    for surface, pattern in TEXT_SURFACES:
        for path in sorted(globmod.glob(os.path.join(root, pattern))):
            if path in seen or not os.path.isfile(path):
                continue
            seen.add(path)
            scan_text_file(sweep, surface, path, root, identifiers)
    for pattern in INITRAMFS_GLOBS:
        for path in sorted(globmod.glob(os.path.join(root, pattern))):
            if path in seen or not os.path.isfile(path):
                continue
            seen.add(path)
            scan_initramfs(sweep, path, root, identifiers)
    if efibootmgr_file:
        if os.path.isfile(efibootmgr_file):
            fake = Sweep()
            scan_text_file(fake, "efibootmgr", efibootmgr_file,
                           os.path.dirname(os.path.abspath(efibootmgr_file)),
                           identifiers)
            for h in fake.hits:
                h.path = f"efibootmgr:{os.path.basename(efibootmgr_file)}"
                sweep.hits.append(h)
            sweep.scanned.extend(fake.scanned)
            sweep.unverified.extend(fake.unverified)
        else:
            sweep.unverified.append(
                f"efibootmgr dump not found: {efibootmgr_file}")
    return sweep


def verdict(sweep: Sweep) -> str:
    if any(h.live for h in sweep.hits):
        return "BLOCKED"
    if sweep.unverified:
        return "INCOMPLETE"
    if sweep.hits:
        return "WARN"
    return "CLEAN"


EXIT = {"CLEAN": 0, "WARN": 0, "BLOCKED": 1, "INCOMPLETE": 2}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Sweep boot/system surfaces for references to a "
                    "drive's identifiers before removing or wiping it.")
    ap.add_argument("--root", default="/",
                    help="filesystem root to sweep (default /)")
    ap.add_argument("--uuid", action="append", default=[],
                    help="filesystem UUID or PARTUUID (repeatable)")
    ap.add_argument("--id", action="append", default=[], dest="extra_ids",
                    help="label, serial, or by-id fragment (repeatable)")
    ap.add_argument("--efibootmgr", metavar="FILE",
                    help="file containing `efibootmgr -v` output to scan")
    source = ap.add_mutually_exclusive_group()
    source.add_argument("--from-device", metavar="FILE", dest="from_device",
                    help="harvest identifiers from an `lsblk -J` JSON or "
                         "`blkid -o export` dump ('-' reads stdin)")
    source.add_argument("--live-device", metavar="DEVICE",
                        dest="live_device",
                        help="run lsblk live (read-only) on this device "
                             "(/dev/sda or bare sda) and harvest its "
                             "identifiers")
    ap.add_argument("--device", metavar="NAME",
                    help="with --from-device: harvest only this device's "
                         "subtree (e.g. sda)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    explicit = list(args.uuid) + list(args.extra_ids)
    harvested: list = []
    identifiers_source = "explicit"
    live_device_path = None
    live_error = None
    if args.live_device:
        if args.device:
            print("error: --device cannot be combined with "
                  "--live-device (the live device is the subtree root)",
                  file=sys.stderr)
            return 2
        live_device_path = normalize_live_device(args.live_device)
        identifiers_source = "explicit+live-device" if explicit \
            else "live-device"
        try:
            harvested = harvest_live_device(args.live_device)
        except HarvestError as exc:
            live_error = str(exc)
            harvested = []
        if live_error is not None or not harvested:
            # Every live-probe failure — and a zero harvest — is
            # INCOMPLETE (exit 2), never a verdict from an empty or
            # untrusted identifier set.
            reason = live_error or (
                f"--live-device {live_device_path} yielded zero "
                "identifiers; no sweep was run and nothing is cleared")
            if args.json:
                print(json.dumps({
                    "root": args.root, "identifiers": explicit,
                    "verdict": "INCOMPLETE",
                    "harvested": [],
                    "identifiers_source": identifiers_source,
                    "identifier_source": {
                        "kind": "live-device",
                        "device": live_device_path, "harvested": 0},
                    "hits": [], "unverified": [reason], "scanned": [],
                }, indent=2))
            else:
                print(f"boot-ref-sweep: root={args.root} "
                      f"identifiers={', '.join(explicit)}")
                print(f"  live-device: {live_device_path} "
                      f"(harvested 0 identifier(s))")
                print("  harvested: (none)")
                print(f"  UNVERIFIED: {reason}")
                print("VERDICT: INCOMPLETE")
                print("Removal is NOT cleared: some surfaces could not "
                      "be verified.")
            return EXIT["INCOMPLETE"]
    elif args.from_device:
        identifiers_source = "explicit+device" if explicit else "device"
        try:
            if args.from_device == "-":
                device_text = sys.stdin.read()
            else:
                with open(args.from_device, "r", encoding="utf-8",
                          errors="replace") as fh:
                    device_text = fh.read()
        except OSError as exc:
            print(f"error: cannot read --from-device file "
                  f"{args.from_device}: {exc.strerror or exc}",
                  file=sys.stderr)
            return 2
        try:
            harvested = harvest_identifiers(device_text, args.device)
        except HarvestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if not harvested:
            # Zero harvested identifiers: never issue a verdict from an
            # empty identifier set (that would read CLEAN for any root).
            # Report INCOMPLETE and clear nothing.
            reason = ("--from-device yielded zero identifiers; "
                      "no sweep was run and nothing is cleared")
            if args.json:
                print(json.dumps({
                    "root": args.root, "identifiers": explicit,
                    "verdict": "INCOMPLETE",
                    "harvested": [],
                    "identifiers_source": identifiers_source,
                    "hits": [], "unverified": [reason], "scanned": [],
                }, indent=2))
            else:
                print(f"boot-ref-sweep: root={args.root} "
                      f"identifiers={', '.join(explicit)}")
                print("  harvested: (none)")
                print(f"  UNVERIFIED: {reason}")
                print("VERDICT: INCOMPLETE")
                print("Removal is NOT cleared: some surfaces could not "
                      "be verified.")
            return EXIT["INCOMPLETE"]
    elif args.device:
        print("error: --device requires --from-device", file=sys.stderr)
        return 2

    # Merge: explicit identifiers come first and win on duplicates;
    # harvested values already present (case-insensitively) are dropped.
    identifiers = list(explicit)
    seen = {norm(i) for i in identifiers}
    for h in harvested:
        if norm(h.value) not in seen:
            seen.add(norm(h.value))
            identifiers.append(h.value)
    if not identifiers:
        print("error: at least one --uuid or --id is required",
              file=sys.stderr)
        return 2
    if not os.path.isdir(args.root):
        print(f"error: root is not a directory: {args.root}", file=sys.stderr)
        return 2

    sweep = run(args.root, identifiers, args.efibootmgr)
    v = verdict(sweep)
    if args.json:
        payload = {
            "root": args.root, "identifiers": identifiers, "verdict": v,
            "hits": [vars(h) for h in sweep.hits],
            "unverified": sweep.unverified,
            "scanned": sweep.scanned,
        }
        if args.from_device:
            payload["harvested"] = [vars(h) for h in harvested]
            payload["identifiers_source"] = identifiers_source
        if live_device_path is not None:
            payload["harvested"] = [vars(h) for h in harvested]
            payload["identifiers_source"] = identifiers_source
            payload["identifier_source"] = {
                "kind": "live-device", "device": live_device_path,
                "harvested": len(harvested)}
        print(json.dumps(payload, indent=2))
    else:
        print(f"boot-ref-sweep: root={args.root} "
              f"identifiers={', '.join(identifiers)}")
        if live_device_path is not None:
            print(f"  live-device: {live_device_path} "
                  f"(harvested {len(harvested)} identifier(s))")
        if args.from_device or live_device_path is not None:
            print(f"  harvested ({identifiers_source}): "
                  + ", ".join(f"{h.value} [{h.kind}:{h.field} "
                              f"from {h.source_device}]"
                              for h in harvested))
        for h in sweep.hits:
            print(f"  {'LIVE ' if h.live else 'BACKUP'} [{h.surface}] "
                  f"{h.path} :: {h.identifier} — {h.detail}")
        for u in sweep.unverified:
            print(f"  UNVERIFIED: {u}")
        print(f"  scanned {len(sweep.scanned)} surface(s), "
              f"{len(sweep.hits)} hit(s)")
        print(f"VERDICT: {v}")
        if v == "BLOCKED":
            print("Do NOT remove/wipe the drive until the live "
                  "references above are fixed and the sweep is re-run.")
        elif v == "INCOMPLETE":
            print("Removal is NOT cleared: some surfaces could not be "
                  "verified.")
        elif v == "WARN":
            print("No live references. Backup files still mention the "
                  "drive — harmless for boot, keep in mind for restores.")
    return EXIT[v]


if __name__ == "__main__":
    raise SystemExit(main())
