# boot-ref-sweep

Pre-removal dangling-reference checker. **Before a drive is wiped,
pulled, or decommissioned, run this.** "It is not the current system
drive" does not prove nothing still waits for it.

Born from the Oct 24–25, 2026 Tritium outage (TRK-0464): the AirDisk
was verified "not the current OS drive" and wiped; two ghost UUIDs
(`037a1434…` = old `/boot`, `E1C3-D1B2` = old `/boot/efi`) were still
baked as dracut `devexists` wait-hooks inside both Oct 10 initramfs
images, and Tritium failed to boot for 9.5 hours. The live `/etc/fstab`
and GRUB were both innocent — the references lived *inside the images*.

## What it sweeps

| Surface | Why |
|---|---|
| `/etc/fstab` (+ backups, classified separately) | mounts that will hang or fail boot |
| `/etc/crypttab` | LUKS unlock waits |
| `/etc/default/grub`, `/boot/grub/grub.cfg` | root/search UUIDs |
| `/etc/kernel/cmdline`, `/etc/dracut.conf(.d)` | baked-in boot config sources |
| systemd `*.mount` / `*.automount` units | mount waits outside fstab |
| **initramfs image contents** (`/boot/initrd*`, `/boot/initramfs*`) | decompresses gzip/xz/bz2/zstd (zstd via CLI when present) and scans filenames + contents — hooks, embedded fstab/cmdline |
| `efibootmgr -v` dump (`--efibootmgr FILE`) | firmware boot entries pointing at the drive's ESP |

Identifiers (`--uuid`, repeatable; `--id` for labels / serials /
by-id fragments) match case-insensitively — vfat UUIDs print
upper-case, configs carry either.

## Harvesting identifiers from a device (`--from-device`, v2)

Typing a drive's identifiers by hand is the error-prone step: miss
one PARTUUID and the sweep clears a drive it should have blocked.
Instead, capture the device's own inventory and let the tool harvest
every identifier from it:

```sh
lsblk -J -o NAME,UUID,PARTUUID,LABEL,PARTLABEL,SERIAL,WWN,TYPE \
  > /tmp/lsblk.json
python3 src/boot_ref_sweep.py --root / --from-device /tmp/lsblk.json

# blkid export dumps work too (format is auto-detected):
blkid -o export > /tmp/blkid.txt
python3 src/boot_ref_sweep.py --root / --from-device /tmp/blkid.txt

# or pipe either one in on stdin:
lsblk -J -o NAME,UUID,PARTUUID,LABEL,PARTLABEL,SERIAL,WWN,TYPE \
  | python3 src/boot_ref_sweep.py --root / --from-device -
```

Harvest rules:

- lsblk JSON is walked recursively, including nested `children`
  (partitions, LUKS/crypt mappings, LVM). Nodes of type `loop`,
  `ram`, or `squashfs` are skipped with their whole subtree.
- `UUID` / `PARTUUID` harvest as uuid-class; `LABEL` / `PARTLABEL` /
  `SERIAL` / `WWN` harvest as id-class. Null, empty, and
  whitespace-only values are skipped; duplicates are dropped
  case-insensitively, preserving first-seen order.
- `--device NAME` restricts the harvest to that device's subtree
  (e.g. `--device sda`, or a partition such as `--device sda2`).
  An unknown `--device` name is an error: exit 2, no verdict.
- Harvested identifiers merge with any explicit `--uuid` / `--id`
  values; on a duplicate the explicit spelling wins.
- **Zero-harvest rule:** if `--from-device` yields **zero**
  identifiers, the verdict is `INCOMPLETE` (exit 2) and no sweep is
  run. An empty identifier set would otherwise "find nothing" on any
  root and falsely report CLEAN — that must never clear a drive.

Harvested identifiers are reported in both output modes: a
`harvested (…)` line in human output, and in `--json` a `"harvested"`
list of `{value, kind, source_device, field}` objects plus an
`"identifiers_source"` field (`"device"`, `"explicit"`, or
`"explicit+device"`). When `--from-device` is absent, output is
exactly as in v1.

## Harvesting live from a device (`--live-device`, v3)

v3 removes the pre-capture step: the tool runs `lsblk` itself —
read-only, it never writes, mounts, or probes with anything else —
and feeds the JSON through the exact same harvest path as
`--from-device`:

```sh
# the pre-wipe invocation: name the drive, sweep the live root
python3 src/boot_ref_sweep.py --root / --live-device /dev/sda

# a bare device name works too (normalised to /dev/sda):
python3 src/boot_ref_sweep.py --root / --live-device sda --json
```

- The command run is
  `lsblk -J -o NAME,UUID,PARTUUID,LABEL,PARTLABEL,SERIAL,WWN,TYPE <device>`
  (children are included, as `lsblk -J` does by default), executed as
  an argv list with no shell. The subtree rooted at the named device
  is harvested; the loop/ram/squashfs pruning and merge rules are
  identical to `--from-device`, and explicit `--uuid` / `--id` values
  still win on duplicates.
- `--live-device` and `--from-device` are mutually exclusive
  (usage error, exit 2).
- **Failure semantics — every failure is `INCOMPLETE` (exit 2), never
  a verdict from an untrusted identifier set:** the `lsblk` binary is
  missing, `lsblk` exits non-zero, its stdout is not valid JSON, the
  device is absent from the `lsblk` output, or the harvest yields
  zero identifiers. Each failure reports its own distinct reason.
- In `--json` mode, live runs add
  `"identifier_source": {"kind": "live-device", "device": "/dev/sda", "harvested": N}`;
  human output prints one extra `live-device:` line naming the device
  and the harvested count. When `--live-device` is absent, output is
  byte-identical to v2.

## Verdicts & exit codes

- `CLEAN` (0) — no references anywhere scanned.
- `WARN` (0) — references only in backup/historical files (e.g.
  `fstab.bak-*`). Safe to remove; remember restores may resurrect them.
- `BLOCKED` (1) — a **live** surface references the drive. Do not
  remove/wipe until fixed and re-swept.
- `INCOMPLETE` (2) — a surface could not be verified (e.g. an
  initramfs whose compression no decoder could open), or a
  `--from-device` harvest yielded zero identifiers. Removal is
  **not** cleared; an unscanned image is never reported as clean.

## Drive-removal checklist

The short operator sequence this tool exists to serve — run it in
order, and treat anything other than `CLEAN`/`WARN` as a stop:

1. **Name the drive by hard identifiers, never by position.** With
   v3 you no longer capture them by hand:
   `python3 src/boot_ref_sweep.py --root / --live-device /dev/sdX`
   (a bare `sdX` works too). The sweep harvests the drive's own
   UUID/PARTUUID/LABEL/PARTLABEL/SERIAL/WWN from live `lsblk` output.
2. **Read the verdict before touching hardware:**
   - `BLOCKED` (exit 1) — a live surface still references the drive.
     Fix each listed reference, then re-run until it clears.
   - `INCOMPLETE` (exit 2) — something could not be verified (a
     failed `lsblk` probe, an undecodable or unreadable initramfs —
     re-run with sufficient privileges). Removal is **not** cleared;
     an unverified surface is never a pass.
   - `WARN` (exit 0) — only backup/historical files mention the
     drive. Safe to remove; remember a restore could resurrect them.
   - `CLEAN` (exit 0) — no references anywhere scanned. Proceed.
3. **Check firmware entries too** when the drive ever held an ESP:
   add `--efibootmgr /tmp/efibootmgr.txt` (a captured
   `efibootmgr -v` dump) to the same sweep.
4. **After removal,** reboot (or run the fleet bootcheck) and confirm
   the machine comes up clean before wiping or reusing the drive —
   the sweep clears references, the boot proves it.

## Usage

```sh
# identifiers come from lsblk -o NAME,UUID,PARTUUID,LABEL,SERIAL
# for the drive you are about to touch — hard identifiers, never names
python3 src/boot_ref_sweep.py --root / \
  --uuid 037a1434-0000-0000-0000-000000000000 --uuid E1C3-D1B2 \
  --id OLDLABEL --efibootmgr /tmp/efibootmgr.txt
python3 src/boot_ref_sweep.py --root /mnt/target-root --uuid … --json
```

Read-only. Stdlib only (Python 3.10+); `zstd` CLI used opportunistically
for zstd images.

## Tests

```sh
python3 -m pytest tests/ -q   # 50 tests: every surface, the gzip-hook
                              # outage shape, early-cpio+main images,
                              # undecodable image = INCOMPLETE, WARN vs
                              # BLOCKED classification, decoder segment
                              # rules (no raw compressed-blob scanning),
                              # plus v2 --from-device harvesting: nested
                              # lsblk children, case-insensitive dedupe,
                              # loop/ram/squashfs skip, blkid export,
                              # --device filter + unknown device,
                              # zero-harvest = INCOMPLETE, explicit-wins
                              # merge, stdin, and end-to-end BLOCKED
                              # from harvested identifiers alone; plus
                              # v3 --live-device: mocked-lsblk harvest
                              # incl. children, bare-name normalisation,
                              # missing/non-zero/invalid/absent/zero
                              # failures = INCOMPLETE, --from-device
                              # conflict, explicit-wins dedupe, live
                              # BLOCKED end-to-end, and v2 output
                              # unchanged without the flag
```

## Field check (Oct 25, 2026, Tritium after recovery)

Run against Tritium's real root for the full ghost UUIDs
(`037a1434-e951-4027-b2c8-9d8975bce954`, `E1C3-D1B2`): **verdict WARN,
exit 0, 53 surfaces scanned, 0 unverified.** Every hit is
backup-classified — five `fstab.bak-*` files and the two preserved
`.bak-ghostfix` initramfs images (which really do contain the ghost
hooks). Zero live hits: the live fstab and the rebuilt live initramfs
images are clean — exactly the post-repair state verified by hand
during the outage recovery, now checkable in ~12 seconds.

Two design lessons were caught by this field run and fixed before
shipping: (1) scanning raw compressed bytes produced fragment
false-positives on the live images — the decoder now searches only
the uncompressed early-cpio prefix plus the decoded main frame;
(2) `*.decompress()` rejects trailing bytes after a stream, so
decoding uses decompressobj forms. Always pass FULL UUIDs: short
fragments are legitimate for text surfaces but raise false-positive
risk anywhere near binary data.
