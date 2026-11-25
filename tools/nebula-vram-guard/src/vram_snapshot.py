#!/usr/bin/env python3
"""vram_snapshot: live free-VRAM snapshot for nebula-vram-guard.

The guard itself is host-free by design (operator-snapshot style): it
judges a job against a --free-mib number somebody hands it. This
helper is the host-touching companion, kept clearly separate: it asks
the local GPU how much VRAM is actually free right now and emits a
snapshot object suitable to feed the guard's --free-mib.

Stdlib-only. Read-only: it runs read-only vendor queries
(nvidia-smi / rocm-smi) or reads a saved output file (--from-file);
it writes nothing and changes no GPU state.

Sources, in order:
  1. nvidia-smi --query-gpu=index,name,memory.free,memory.total
     --format=csv,noheader,nounits          (primary)
  2. rocm-smi --showmeminfo vram            (fallback, AMD)
  3. --from-file <path>                     (saved output of either)

The command runner is injectable (the ``runner`` parameter of
collect_snapshot()/main()): tests pass a fake runner, so no test ever
needs a real GPU -- the boot-ref-sweep v3 live-device
injectable-runner precedent.

Verdict discipline (same as its siblings): EVERY failure -- tool
missing, command fails, unparseable output, zero GPUs, unknown
--gpu index, missing/unreadable --from-file -- is INCOMPLETE,
exit 2, never a guessed number. Argparse usage errors also exit 2
but print a usage message and no verdict line.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

NVIDIA_CMD = ["nvidia-smi", "--query-gpu=index,name,memory.free,memory.total",
              "--format=csv,noheader,nounits"]
ROCM_CMD = ["rocm-smi", "--showmeminfo", "vram"]


class SnapshotIncomplete(Exception):
    """Raised with a list of human-readable errors; verdict INCOMPLETE."""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def default_runner(argv):
    """Run a read-only vendor command; return (returncode, stdout, stderr).

    FileNotFoundError (tool missing) propagates to the caller, which
    turns it into INCOMPLETE like every other failure.
    """
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    return proc.returncode, proc.stdout, proc.stderr


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ parsers

def parse_nvidia(text):
    """Parse nvidia-smi CSV (noheader, nounits) into a list of GPU dicts."""
    gpus = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 4:
            raise SnapshotIncomplete(
                [f"unparseable nvidia-smi line (expected 4 fields): {line!r}"])
        try:
            index = int(parts[0])
            free = int(float(parts[2]))
            total = int(float(parts[3]))
        except ValueError:
            raise SnapshotIncomplete(
                [f"unparseable nvidia-smi numbers in line: {line!r}"])
        gpus.append({"gpu_index": index, "name": parts[1],
                     "free_mib": free, "total_mib": total})
    if not gpus:
        raise SnapshotIncomplete(["nvidia-smi output contained zero GPUs"])
    return gpus


_ROCM_LINE = re.compile(
    r"GPU\[(\d+)\]\s*:\s*(VRAM Total Memory|VRAM Total Used Memory|"
    r"VRAM Free Memory)\s*\((B|MiB|MB|GB)\)\s*:\s*([0-9]+(?:\.[0-9]+)?)")


def _to_mib(value, unit):
    v = float(value)
    if unit == "B":
        return int(v / (1024 * 1024))
    if unit == "GB":
        return int(v * 1024)
    return int(v)  # MiB / MB treated as MiB (rocm-smi reports B or MiB)


def parse_rocm(text):
    """Parse `rocm-smi --showmeminfo vram` output into a list of GPU dicts.

    Free VRAM is total - used unless a free figure is reported
    directly. A GPU missing either figure is INCOMPLETE, not guessed.
    """
    per_gpu = {}
    for line in text.splitlines():
        m = _ROCM_LINE.search(line)
        if not m:
            continue
        idx = int(m.group(1))
        entry = per_gpu.setdefault(idx, {"gpu_index": idx,
                                         "name": f"AMD GPU {idx}"})
        mib = _to_mib(m.group(4), m.group(3))
        if m.group(2) == "VRAM Total Memory":
            entry["total_mib"] = mib
        elif m.group(2) == "VRAM Total Used Memory":
            entry["used_mib"] = mib
        elif m.group(2) == "VRAM Free Memory":
            entry["free_mib"] = mib
    if not per_gpu:
        raise SnapshotIncomplete(["rocm-smi output contained zero GPUs"])
    gpus = []
    for idx in sorted(per_gpu):
        e = per_gpu[idx]
        if "total_mib" not in e:
            raise SnapshotIncomplete([f"rocm-smi GPU {idx}: no total VRAM figure"])
        if "free_mib" not in e:
            if "used_mib" not in e:
                raise SnapshotIncomplete(
                    [f"rocm-smi GPU {idx}: no used/free VRAM figure"])
            e["free_mib"] = e["total_mib"] - e["used_mib"]
        gpus.append({"gpu_index": idx, "name": e["name"],
                     "free_mib": e["free_mib"], "total_mib": e["total_mib"]})
    return gpus


def parse_saved(text):
    """Detect the format of saved command output and parse it."""
    if "VRAM" in text and "GPU[" in text:
        return parse_rocm(text)
    # nvidia CSV is the only other supported saved shape.
    return parse_nvidia(text)


# ----------------------------------------------------------------- collect

def _select(gpus, gpu_index):
    for g in gpus:
        if g["gpu_index"] == gpu_index:
            return g
    raise SnapshotIncomplete(
        [f"GPU index {gpu_index} not found (saw: "
         + ", ".join(str(g["gpu_index"]) for g in gpus) + ")"])


def collect_snapshot(gpu_index=0, from_file=None, runner=None, now_iso=None):
    """Return a snapshot dict, or raise SnapshotIncomplete.

    runner: callable(argv) -> (returncode, stdout, stderr); defaults
    to default_runner. Injected by tests so no real GPU is needed.
    """
    runner = runner or default_runner
    observed = now_iso or _utc_now_iso()
    if from_file is not None:
        try:
            with open(from_file, "r", encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            raise SnapshotIncomplete([f"snapshot file not found: {from_file}"])
        except OSError as exc:
            raise SnapshotIncomplete([f"snapshot file unreadable: {exc}"])
        gpus = parse_saved(text)
        chosen = _select(gpus, gpu_index)
        return {"source": "file", **chosen, "observed_at": observed}

    errors = []
    # Primary: nvidia-smi.
    try:
        rc, out, err = runner(NVIDIA_CMD)
        if rc != 0:
            errors.append(f"nvidia-smi exited {rc}: {(err or out).strip()[:200]}")
        else:
            chosen = _select(parse_nvidia(out), gpu_index)
            return {"source": "nvidia-smi", **chosen, "observed_at": observed}
    except FileNotFoundError:
        errors.append("nvidia-smi not found")
    except SnapshotIncomplete as exc:
        errors.extend(exc.errors)
    except Exception as exc:  # timeout etc. -- still INCOMPLETE, never a guess
        errors.append(f"nvidia-smi failed: {exc}")

    # Fallback: rocm-smi.
    try:
        rc, out, err = runner(ROCM_CMD)
        if rc != 0:
            errors.append(f"rocm-smi exited {rc}: {(err or out).strip()[:200]}")
        else:
            chosen = _select(parse_rocm(out), gpu_index)
            return {"source": "rocm-smi", **chosen, "observed_at": observed}
    except FileNotFoundError:
        errors.append("rocm-smi not found")
    except SnapshotIncomplete as exc:
        errors.extend(exc.errors)
    except Exception as exc:
        errors.append(f"rocm-smi failed: {exc}")

    raise SnapshotIncomplete(errors or ["no GPU tool produced a snapshot"])


# --------------------------------------------------------------------- CLI

def _print_human(snap):
    print(f"source: {snap['source']}")
    print(f"gpu: {snap['gpu_index']} ({snap['name']})")
    print(f"free: {snap['free_mib']:,} MiB")
    print(f"total: {snap['total_mib']:,} MiB")
    print(f"observed_at: {snap['observed_at']}")


def _print_incomplete(errors, as_json):
    if as_json:
        print(json.dumps({"verdict": "INCOMPLETE", "source": None,
                          "gpu_index": None, "name": None, "free_mib": None,
                          "total_mib": None, "observed_at": _utc_now_iso(),
                          "errors": errors}, indent=2))
    else:
        print("verdict: INCOMPLETE")
        for e in errors:
            print(f"error: {e}")


def main(argv=None, runner=None):
    p = argparse.ArgumentParser(
        prog="vram_snapshot.py",
        description="Live free-VRAM snapshot for nebula-vram-guard (read-only).")
    p.add_argument("--gpu", type=int, default=0,
                   help="GPU index to report (default: 0)")
    p.add_argument("--from-file", default=None,
                   help="parse saved nvidia-smi/rocm-smi output from this file "
                        "instead of running a live command")
    p.add_argument("--json", action="store_true", help="emit the snapshot as JSON")
    p.add_argument("--check", action="store_true",
                   help="also run the guard on --job with free_mib from this "
                        "snapshot; exit code is the guard's")
    p.add_argument("--job", default=None, help="job JSON for --check")
    p.add_argument("--gpu-mib", type=float, default=8192,
                   help="guard budget fallback for --check (unused when a "
                        "snapshot succeeds; the snapshot's free_mib wins)")
    p.add_argument("--reserve-mib", type=float, default=1024)
    args = p.parse_args(argv)
    if args.gpu < 0:
        p.error("--gpu must be non-negative")
    if args.check and not args.job:
        p.error("--check requires --job")

    try:
        snap = collect_snapshot(gpu_index=args.gpu, from_file=args.from_file,
                                runner=runner)
    except SnapshotIncomplete as exc:
        if args.check:
            # The guard cannot be judged without a free figure.
            _print_incomplete(exc.errors, args.json)
            return 2
        _print_incomplete(exc.errors, args.json)
        return 2

    if not args.check:
        if args.json:
            print(json.dumps(snap, indent=2))
        else:
            _print_human(snap)
        return 0

    # --check: run the guard in-process with the snapshot's free_mib,
    # mirroring workflow_adapter --check.
    import nebula_vram_guard
    try:
        with open(args.job, "r", encoding="utf-8") as fh:
            job = json.load(fh)
    except FileNotFoundError:
        _print_incomplete([f"job file not found: {args.job}"], args.json)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        _print_incomplete([f"job file unreadable or unparseable: {exc}"], args.json)
        return 2
    report = nebula_vram_guard.evaluate(job, args.gpu_mib, args.reserve_mib,
                                        float(snap["free_mib"]))
    if args.json:
        print(json.dumps({"snapshot": snap, "verdict": report["verdict"],
                          "guard": report}, indent=2))
    else:
        _print_human(snap)
        print(f"verdict: {report['verdict']}")
        if report.get("required_mib") is not None:
            print(f"required: {report['required_mib']:,.0f} MiB")
            print(f"budget (free): {report['budget_mib']:,.0f} MiB")
        for e in report["errors"]:
            print(f"error: {e}")
    return {"ALLOW": 0, "REFUSE": 1, "INCOMPLETE": 2}[report["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
