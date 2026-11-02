import gzip
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src", "boot_ref_sweep.py")
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import boot_ref_sweep as brs  # noqa: E402

GHOST_BOOT = "037a1434-1111-2222-3333-444455556666"
GHOST_ESP = "E1C3-D1B2"
LIVE_BOOT = "ea1a3177-e41f-442f-8f4c-e0822f542551"


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        fh.write(text)
    return p


def newc(entries):
    """Build a minimal newc cpio archive from [(name, bytes), ...]."""
    out = bytearray()
    ino = 1
    for name, data in entries:
        nb = name.encode() + b"\x00"
        fields = [ino, 0o100644, 0, 0, 1, 0, len(data), 0, 0, 0, 0,
                  len(nb), 0]
        hdr = "070701" + "".join(f"{f:08x}" for f in fields)
        out.extend(hdr.encode())
        out.extend(nb)
        out.extend(b"\x00" * ((4 - (len(hdr) + len(nb)) % 4) % 4))
        out.extend(data)
        out.extend(b"\x00" * ((4 - len(data) % 4) % 4))
        ino += 1
    nb = b"TRAILER!!!\x00"
    fields = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(nb), 0]
    hdr = "070701" + "".join(f"{f:08x}" for f in fields)
    out.extend(hdr.encode())
    out.extend(nb)
    out.extend(b"\x00" * ((4 - (len(hdr) + len(nb)) % 4) % 4))
    out.extend(b"\x00" * 256)
    return bytes(out)


def write_initrd(root, name, entries, compress=True):
    p = os.path.join(root, "boot", name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    raw = newc(entries)
    with open(p, "wb") as fh:
        fh.write(gzip.compress(raw) if compress else raw)
    return p


def cli(root, *ids, extra=()):
    cmd = [sys.executable, SRC, "--root", root]
    for i in ids:
        cmd += ["--uuid", i]
    cmd += list(extra)
    return subprocess.run(cmd, capture_output=True, text=True)


class SweepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = self.tmp

    def test_clean_tree(self):
        write(self.root, "etc/fstab",
              f"UUID={LIVE_BOOT} /boot ext4 defaults 0 2\n")
        write_initrd(self.root, "initrd.img-6.8",
                     [("conf/cmdline", b"root=UUID=aaaa\n")])
        r = cli(self.root, GHOST_BOOT, GHOST_ESP)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("VERDICT: CLEAN", r.stdout)

    def test_live_fstab_hit_blocks(self):
        write(self.root, "etc/fstab",
              f"UUID={GHOST_BOOT} /boot ext4 defaults 0 2\n")
        r = cli(self.root, GHOST_BOOT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("VERDICT: BLOCKED", r.stdout)
        self.assertIn("Do NOT remove/wipe", r.stdout)

    def test_backup_only_is_warn_not_blocked(self):
        # The real Oct 25 finding: ghosts lived only in fstab backups.
        write(self.root, "etc/fstab",
              f"UUID={LIVE_BOOT} /boot ext4 defaults 0 2\n")
        write(self.root, "etc/fstab.migration-bak",
              f"UUID={GHOST_BOOT} /boot ext4 defaults 0 2\n")
        r = cli(self.root, GHOST_BOOT)
        self.assertEqual(r.returncode, 0)
        self.assertIn("VERDICT: WARN", r.stdout)

    def test_grub_cfg_hit_blocks(self):
        write(self.root, "boot/grub/grub.cfg",
              f"search --fs-uuid --set=root {GHOST_BOOT}\n")
        r = cli(self.root, GHOST_BOOT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("grub-config", r.stdout)

    def test_default_grub_and_cmdline(self):
        write(self.root, "etc/default/grub",
              f'GRUB_CMDLINE_LINUX="root=UUID={GHOST_BOOT}"\n')
        r = cli(self.root, GHOST_BOOT)
        self.assertEqual(r.returncode, 1)

    def test_crypttab_hit(self):
        write(self.root, "etc/crypttab",
              f"crypt1 UUID={GHOST_BOOT} none luks\n")
        r = cli(self.root, GHOST_BOOT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("crypttab", r.stdout)

    def test_systemd_mount_hit(self):
        write(self.root, "etc/systemd/system/mnt-old.mount",
              f"[Mount]\nWhat=/dev/disk/by-uuid/{GHOST_BOOT}\nWhere=/mnt/old\n")
        r = cli(self.root, GHOST_BOOT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("systemd-mount", r.stdout)

    def test_case_insensitive_vfat_uuid(self):
        write(self.root, "etc/fstab", f"UUID={GHOST_ESP.lower()} /boot/efi vfat defaults 0 2\n")
        r = cli(self.root, GHOST_ESP)
        self.assertEqual(r.returncode, 1)

    def test_extra_id_label_and_serial(self):
        write(self.root, "etc/fstab", "LABEL=OLDBOOT /boot ext4 defaults 0 2\n")
        p = subprocess.run([sys.executable, SRC, "--root", self.root,
                            "--id", "OLDBOOT"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)

    def test_initramfs_hook_filename_hit_blocks(self):
        # The actual outage mechanism: a devexists hook baked into the image.
        hook = (f"var/lib/dracut/hooks/initqueue/finished/"
                f"devexists-\\x2fdev\\x2fdisk\\x2fby-uuid\\x2f{GHOST_BOOT}.sh")
        write_initrd(self.root, "initrd.img-7.0.0-38-generic",
                     [(hook, b"#!/bin/sh\n")])
        r = cli(self.root, GHOST_BOOT)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("initramfs", r.stdout)

    def test_initramfs_embedded_fstab_content_hit(self):
        write_initrd(self.root, "initrd.img-6.8",
                     [("etc/fstab", f"UUID={GHOST_ESP} /boot/efi vfat\n".encode())])
        r = cli(self.root, GHOST_ESP)
        self.assertEqual(r.returncode, 1)

    def test_initramfs_uncompressed_cpio_hit(self):
        write_initrd(self.root, "initrd.img-6.8",
                     [("hooks/x", f"wait {GHOST_BOOT}".encode())],
                     compress=False)
        r = cli(self.root, GHOST_BOOT)
        self.assertEqual(r.returncode, 1)

    def test_initramfs_early_cpio_plus_gzip_main(self):
        # early microcode cpio (raw) concatenated with gzipped main image
        early = newc([("kernel/microcode", b"\x00" * 32)])
        main = gzip.compress(newc([("etc/cmdline",
                                    f"root=UUID={GHOST_BOOT}".encode())]))
        p = os.path.join(self.root, "boot", "initrd.img-6.8")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(early + main)
        r = cli(self.root, GHOST_BOOT)
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_undecodable_initramfs_is_incomplete_not_clean(self):
        # gzip magic followed by garbage: decoder fails -> INCOMPLETE (2),
        # never silently CLEAN.
        p = os.path.join(self.root, "boot", "initrd.img-6.8")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(b"\x1f\x8b" + b"not-a-real-gzip-stream" * 8)
        r = cli(self.root, GHOST_BOOT)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("INCOMPLETE", r.stdout)

    def test_json_output(self):
        write(self.root, "etc/fstab", f"UUID={GHOST_BOOT} /boot ext4 defaults 0 2\n")
        p = cli(self.root, GHOST_BOOT, extra=("--json",))
        data = json.loads(p.stdout)
        self.assertEqual(data["verdict"], "BLOCKED")
        self.assertEqual(len(data["hits"]), 1)
        self.assertTrue(data["hits"][0]["live"])

    def test_efibootmgr_dump_hit(self):
        dump = os.path.join(self.tmp, "efi.txt")
        with open(dump, "w") as fh:
            fh.write(f"Boot0002* OldDisk HD(1,GPT,{GHOST_BOOT},0x800,0x1000)/File(\\EFI\\ubuntu\\shimx64.efi)\n")
        p = cli(self.root, GHOST_BOOT, extra=("--efibootmgr", dump))
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("efibootmgr", p.stdout)

    def test_no_identifier_is_usage_error(self):
        p = subprocess.run([sys.executable, SRC, "--root", self.root],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    def test_missing_root_is_error(self):
        p = cli(os.path.join(self.tmp, "nope"), GHOST_BOOT)
        self.assertEqual(p.returncode, 2)

    def test_dracut_conf_hit(self):
        write(self.root, "etc/dracut.conf.d/99-old.conf",
              f'# was built for {GHOST_BOOT}\n')
        r = cli(self.root, GHOST_BOOT)
        self.assertEqual(r.returncode, 1)

    def test_multiple_identifiers_report_each(self):
        write(self.root, "etc/fstab",
              f"UUID={GHOST_BOOT} /boot ext4 defaults 0 2\n"
              f"UUID={GHOST_ESP} /boot/efi vfat defaults 0 2\n")
        data = json.loads(cli(self.root, GHOST_BOOT, GHOST_ESP,
                              extra=("--json",)).stdout)
        found = {h["identifier"] for h in data["hits"]}
        self.assertEqual(found, {GHOST_BOOT, GHOST_ESP})


if __name__ == "__main__":
    unittest.main()

class DecoderSegmentTests(unittest.TestCase):
    def test_trailing_raw_bytes_after_frame_not_searched(self):
        # An identifier sitting in raw bytes AFTER the compressed frame
        # (not inside any cpio member) must not be reported: raw
        # compressed-blob scanning produced fragment false-positives
        # on Tritium's live images on 2026-10-25.
        main = gzip.compress(newc([("etc/cmdline", b"root=UUID=aaaa\n")]))
        data = newc([("kernel/microcode", b"\x00" * 64)]) + main + \
            f"trailing-{GHOST_BOOT}".encode()
        searchable, complete = brs.initramfs_searchable_bytes(data)
        self.assertTrue(complete)
        self.assertNotIn(GHOST_BOOT.encode(), searchable)

    def test_early_cpio_prefix_is_searched(self):
        early = newc([("hooks/early", f"wait {GHOST_BOOT}".encode())])
        main = gzip.compress(newc([("etc/cmdline", b"root=UUID=aaaa\n")]))
        searchable, complete = brs.initramfs_searchable_bytes(early + main)
        self.assertTrue(complete)
        self.assertIn(GHOST_BOOT.encode(), searchable)


# --- v2: --from-device harvesting ----------------------------------------

OTHER_UUID = "99999999-8888-7777-6666-555544443333"
SERIAL = "WD-WX21A0001234"
WWN = "0x50014ee2b5a12345"


def lsblk_sample():
    return {"blockdevices": [
        {"name": "sda", "type": "disk", "serial": SERIAL, "wwn": WWN,
         "uuid": None, "partuuid": None, "label": None, "partlabel": None,
         "children": [
             {"name": "sda1", "type": "part", "uuid": GHOST_ESP,
              "partuuid": "aaaa0001-01", "label": None,
              "partlabel": "EFI System"},
             {"name": "sda2", "type": "part", "uuid": GHOST_BOOT,
              "partuuid": "aaaa0001-02", "label": "OLDBOOT",
              "partlabel": "boot",
              "children": [
                  {"name": "dm-0", "type": "crypt", "uuid": OTHER_UUID,
                   "label": "cryptboot"},
              ]},
         ]},
        {"name": "sdb", "type": "disk", "serial": "OTHER-SERIAL",
         "children": [
             {"name": "sdb1", "type": "part",
              "uuid": "bbbb1111-2222-3333-4444-555566667777"},
         ]},
        {"name": "loop0", "type": "loop", "uuid": "LOOPUUID-SKIP",
         "children": [
             {"name": "loop0p1", "type": "part", "uuid": "LOOPCHILD-SKIP"},
         ]},
    ]}


BLKID_SAMPLE = """\
DEVNAME=/dev/sda1
UUID=E1C3-D1B2
PARTUUID=aaaa0001-01
TYPE=vfat
PARTLABEL=EFI System

DEVNAME=/dev/sda2
UUID=037a1434-1111-2222-3333-444455556666
PARTUUID=aaaa0001-02
LABEL=OLDBOOT
TYPE=ext4
"""


def device_file(tmp, payload, name="device.json"):
    p = os.path.join(tmp, name)
    with open(p, "w") as fh:
        fh.write(payload if isinstance(payload, str) else json.dumps(payload))
    return p


def cli_device(root, device_path, extra=()):
    cmd = [sys.executable, SRC, "--root", root,
           "--from-device", device_path] + list(extra)
    return subprocess.run(cmd, capture_output=True, text=True)


class HarvestUnitTests(unittest.TestCase):
    def test_lsblk_nested_children_harvest(self):
        got = brs.harvest_identifiers(json.dumps(lsblk_sample()))
        by_value = {h.value: h for h in got}
        # the crypt child nested under sda2 is harvested too
        self.assertIn(OTHER_UUID, by_value)
        self.assertEqual(by_value[OTHER_UUID].source_device, "dm-0")
        self.assertEqual(by_value[GHOST_BOOT].kind, "uuid")
        self.assertEqual(by_value[GHOST_BOOT].field, "uuid")
        self.assertEqual(by_value[GHOST_BOOT].source_device, "sda2")
        self.assertEqual(by_value["aaaa0001-02"].kind, "uuid")
        self.assertEqual(by_value["aaaa0001-02"].field, "partuuid")
        self.assertEqual(by_value["OLDBOOT"].kind, "id")
        self.assertEqual(by_value["OLDBOOT"].field, "label")
        self.assertEqual(by_value[SERIAL].kind, "id")
        self.assertEqual(by_value[SERIAL].field, "serial")
        self.assertEqual(by_value[SERIAL].source_device, "sda")
        self.assertEqual(by_value[WWN].field, "wwn")
        # first-seen order: the disk's own serial precedes partition UUIDs
        self.assertEqual(got[0].value, SERIAL)

    def test_lsblk_dedupe_case_insensitive_first_seen_wins(self):
        data = {"blockdevices": [
            {"name": "sda", "type": "disk", "children": [
                {"name": "sda1", "type": "part", "uuid": GHOST_ESP},
                {"name": "sda2", "type": "part",
                 "uuid": GHOST_ESP.lower(), "label": "Data"},
                {"name": "sda3", "type": "part", "label": "DATA"},
            ]}]}
        got = brs.harvest_identifiers(json.dumps(data))
        values = [h.value for h in got]
        self.assertEqual(values.count(GHOST_ESP), 1)
        self.assertNotIn(GHOST_ESP.lower(), values)
        self.assertEqual([v for v in values if v.lower() == "data"], ["Data"])

    def test_lsblk_skips_loop_ram_squashfs(self):
        got = brs.harvest_identifiers(json.dumps(lsblk_sample()))
        values = [h.value for h in got]
        self.assertNotIn("LOOPUUID-SKIP", values)
        self.assertNotIn("LOOPCHILD-SKIP", values)
        data = {"blockdevices": [
            {"name": "ram0", "type": "ram", "uuid": "RAM-SKIP"},
            {"name": "sr0", "type": "squashfs", "uuid": "SQUASH-SKIP"},
            {"name": "sda", "type": "disk", "uuid": OTHER_UUID},
        ]}
        values = [h.value for h in brs.harvest_identifiers(json.dumps(data))]
        self.assertEqual(values, [OTHER_UUID])

    def test_lsblk_skips_null_empty_whitespace(self):
        data = {"blockdevices": [
            {"name": "sda", "type": "disk", "uuid": None, "label": "",
             "serial": "   ", "children": [
                 {"name": "sda1", "type": "part", "uuid": OTHER_UUID},
             ]}]}
        got = brs.harvest_identifiers(json.dumps(data))
        self.assertEqual([h.value for h in got], [OTHER_UUID])

    def test_blkid_export_parse(self):
        got = brs.harvest_identifiers(BLKID_SAMPLE)
        by_value = {h.value: h for h in got}
        self.assertEqual(by_value[GHOST_ESP].source_device, "sda1")
        self.assertEqual(by_value[GHOST_ESP].kind, "uuid")
        self.assertEqual(by_value["aaaa0001-01"].field, "partuuid")
        self.assertEqual(by_value["EFI System"].field, "partlabel")
        self.assertEqual(by_value["EFI System"].kind, "id")
        self.assertEqual(by_value[GHOST_BOOT].source_device, "sda2")
        self.assertEqual(by_value["OLDBOOT"].field, "label")
        # TYPE= is not an identifier and is never harvested
        self.assertNotIn("vfat", by_value)
        self.assertNotIn("ext4", by_value)

    def test_device_filter_restricts_to_subtree(self):
        got = brs.harvest_identifiers(json.dumps(lsblk_sample()),
                                      device="sdb")
        values = [h.value for h in got]
        self.assertIn("bbbb1111-2222-3333-4444-555566667777", values)
        self.assertIn("OTHER-SERIAL", values)
        self.assertNotIn(GHOST_BOOT, values)
        self.assertNotIn(SERIAL, values)
        # a partition name selects that partition (and its children)
        got = brs.harvest_identifiers(json.dumps(lsblk_sample()),
                                      device="sda2")
        values = [h.value for h in got]
        self.assertIn(GHOST_BOOT, values)
        self.assertIn(OTHER_UUID, values)  # nested crypt child
        self.assertNotIn(GHOST_ESP, values)

    def test_device_filter_blkid(self):
        got = brs.harvest_identifiers(BLKID_SAMPLE, device="sda2")
        values = [h.value for h in got]
        self.assertIn(GHOST_BOOT, values)
        self.assertNotIn(GHOST_ESP, values)

    def test_unknown_device_raises(self):
        with self.assertRaises(brs.HarvestError):
            brs.harvest_identifiers(json.dumps(lsblk_sample()),
                                    device="nvme9n1")
        with self.assertRaises(brs.HarvestError):
            brs.harvest_identifiers(BLKID_SAMPLE, device="sdz1")


class FromDeviceCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = self.tmp

    def test_unknown_device_cli_exit2_no_verdict(self):
        dev = device_file(self.tmp, lsblk_sample())
        p = subprocess.run([sys.executable, SRC, "--root", self.root,
                            "--from-device", dev, "--device", "nvme9n1"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("unknown device", p.stderr)
        self.assertNotIn("VERDICT:", p.stdout)

    def test_zero_harvest_is_incomplete_never_clean(self):
        empty = {"blockdevices": [
            {"name": "sda", "type": "disk", "uuid": None, "label": "  ",
             "children": [{"name": "sda1", "type": "part"}]}]}
        dev = device_file(self.tmp, empty)
        write(self.root, "etc/fstab",
              f"UUID={LIVE_BOOT} /boot ext4 defaults 0 2\n")
        p = cli_device(self.root, dev)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("VERDICT: INCOMPLETE", p.stdout)
        self.assertNotIn("VERDICT: CLEAN", p.stdout)
        data = json.loads(cli_device(self.root, dev,
                                     extra=("--json",)).stdout)
        self.assertEqual(data["verdict"], "INCOMPLETE")
        self.assertEqual(data["harvested"], [])

    def test_merge_explicit_wins_on_dedupe(self):
        dev = device_file(self.tmp, lsblk_sample())
        # explicit flag carries the same UUID in a different case
        p = subprocess.run([sys.executable, SRC, "--root", self.root,
                            "--from-device", dev,
                            "--uuid", GHOST_ESP.lower(), "--json"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        data = json.loads(p.stdout)
        lowered = [i.lower() for i in data["identifiers"]]
        self.assertEqual(lowered.count(GHOST_ESP.lower()), 1)
        # the explicit (lower-case) spelling is the one kept
        self.assertIn(GHOST_ESP.lower(), data["identifiers"])
        self.assertNotIn(GHOST_ESP, data["identifiers"])
        # harvested identifiers are still reported, with provenance
        harvested = {h["value"]: h for h in data["harvested"]}
        self.assertEqual(harvested[GHOST_BOOT]["source_device"], "sda2")
        self.assertEqual(harvested[GHOST_BOOT]["field"], "uuid")
        self.assertEqual(harvested[SERIAL]["kind"], "id")
        self.assertEqual(data["identifiers_source"], "explicit+device")

    def test_end_to_end_harvested_id_finds_fstab_reference(self):
        dev = device_file(self.tmp, lsblk_sample())
        write(self.root, "etc/fstab",
              f"UUID={GHOST_BOOT} /boot ext4 defaults 0 2\n")
        p = cli_device(self.root, dev)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("VERDICT: BLOCKED", p.stdout)
        self.assertIn("harvested", p.stdout)
        self.assertIn(GHOST_BOOT, p.stdout)
        data = json.loads(cli_device(self.root, dev,
                                     extra=("--json",)).stdout)
        self.assertEqual(data["verdict"], "BLOCKED")
        self.assertTrue(any(h["identifier"] == GHOST_BOOT
                            for h in data["hits"]))

    def test_end_to_end_blkid_device_file(self):
        dev = device_file(self.tmp, BLKID_SAMPLE, name="blkid.txt")
        write(self.root, "etc/fstab",
              "LABEL=OLDBOOT /boot ext4 defaults 0 2\n")
        p = cli_device(self.root, dev)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("VERDICT: BLOCKED", p.stdout)

    def test_from_device_stdin(self):
        write(self.root, "etc/fstab",
              f"UUID={GHOST_ESP} /boot/efi vfat defaults 0 2\n")
        p = subprocess.run([sys.executable, SRC, "--root", self.root,
                            "--from-device", "-"],
                           input=json.dumps(lsblk_sample()),
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("VERDICT: BLOCKED", p.stdout)

    def test_device_without_from_device_is_error(self):
        p = subprocess.run([sys.executable, SRC, "--root", self.root,
                            "--uuid", GHOST_BOOT, "--device", "sda"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("--from-device", p.stderr)

    def test_missing_from_device_file_is_error(self):
        p = cli_device(self.root, os.path.join(self.tmp, "nope.json"))
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("VERDICT:", p.stdout)
