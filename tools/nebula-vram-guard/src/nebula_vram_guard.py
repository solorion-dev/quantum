#!/usr/bin/env python3
"""nebula-vram-guard: pre-flight VRAM refusal for Nebula / ComfyUI jobs.

Read-only, stdlib-only, no network calls (operator-snapshot style, like
settle-check and codex-lint-drift). Given a job description as a local
JSON file, it estimates the job's VRAM requirement and answers one
question: does this job fit the GPU budget, or must it be REFUSED
before submit?

Verdicts:
  ALLOW     exit 0  required <= budget
  REFUSE    exit 1  required > budget
  INCOMPLETE exit 2  the job could not be judged (missing/unparseable
                    job file, zero models, a model with no size and no
                    known-size-table hit, non-positive dimensions)

Estimate:
  models_mib    = sum of model sizes (explicit size_mib, or the
                  built-in known-size table by filename pattern)
  latent_mib    = (width/8)*(height/8)*4 channels*4 bytes*batch / MiB
  activation_mib = max(256, latent_mib * 8)   (conservative overhead)
  estimate_mib  = models_mib + activation_mib + extra_mib
  required_mib  = estimate_mib + reserve_mib (default 1024)
  budget_mib    = free_mib if given else gpu_mib (default 8192)

This is a conservative pre-flight estimate, not a profiler.
"""
import argparse
import json
import math
import sys

# Built-in known-size table: (filename substring pattern, size MiB).
# ESTIMATES for common checkpoint size classes, labelled as such in the
# README. First match wins; matching is case-insensitive on the name.
KNOWN_SIZES = [
    ("flux1-dev-fp8", 11903),
    ("flux1-schnell-fp8", 11903),
    ("flux-fp8", 11903),
    ("flux1-dev", 23802),
    ("flux1-schnell", 23802),
    ("flux", 23802),
    ("wan2.1-t2v-14b", 28000),
    ("wan2.1", 16000),
    ("wan", 16000),
    ("sdxl", 6938),
    ("sd_xl", 6938),
    ("sd15", 2135),
    ("sd1.5", 2135),
    ("v1-5-pruned", 2135),
]

DEFAULT_GPU_MIB = 8192
DEFAULT_RESERVE_MIB = 1024
MIN_ACTIVATION_MIB = 256
ACTIVATION_FACTOR = 8


def known_size(name):
    low = name.lower()
    for pattern, size in KNOWN_SIZES:
        if pattern in low:
            return size
    return None


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def evaluate(job, gpu_mib, reserve_mib, free_mib):
    """Return a report dict; verdict INCOMPLETE carries errors."""
    report = {
        "verdict": None,
        "models": [],
        "models_mib": None,
        "activation_mib": None,
        "extra_mib": None,
        "estimate_mib": None,
        "reserve_mib": reserve_mib,
        "budget_mib": free_mib if free_mib is not None else gpu_mib,
        "budget_source": "free" if free_mib is not None else "gpu",
        "required_mib": None,
        "errors": [],
    }
    errors = report["errors"]
    if not isinstance(job, dict):
        errors.append("job file must contain a JSON object")
        report["verdict"] = "INCOMPLETE"
        return report
    models = job.get("models")
    if not isinstance(models, list) or len(models) == 0:
        errors.append("job must list at least one model")
        report["verdict"] = "INCOMPLETE"
        return report
    width, height = job.get("width"), job.get("height")
    if not is_number(width) or width <= 0:
        errors.append("width must be a positive number")
    if not is_number(height) or height <= 0:
        errors.append("height must be a positive number")
    batch = job.get("batch", 1)
    if not is_number(batch) or batch <= 0:
        errors.append("batch must be a positive number")
    extra = job.get("extra_mib", 0)
    if not is_number(extra) or extra < 0:
        errors.append("extra_mib must be a non-negative number")
    total = 0.0
    for i, m in enumerate(models):
        if not isinstance(m, dict) or not isinstance(m.get("name"), str) or not m["name"]:
            errors.append(f"models[{i}] must have a non-empty string name")
            continue
        entry = {"name": m["name"], "size_mib": None, "size_source": None}
        if "size_mib" in m and m["size_mib"] is not None:
            if not is_number(m["size_mib"]) or m["size_mib"] <= 0:
                errors.append(f"models[{i}] size_mib must be a positive number")
            else:
                entry["size_mib"] = float(m["size_mib"])
                entry["size_source"] = "explicit"
        else:
            hit = known_size(m["name"])
            if hit is None:
                errors.append(
                    f"models[{i}] '{m['name']}': no size_mib and no known-size-table match"
                )
            else:
                entry["size_mib"] = float(hit)
                entry["size_source"] = "known-table (estimate)"
        if entry["size_mib"] is not None:
            total += entry["size_mib"]
        report["models"].append(entry)
    if errors:
        report["verdict"] = "INCOMPLETE"
        return report
    latent_bytes = (width / 8) * (height / 8) * 4 * 4 * batch
    latent_mib = latent_bytes / (1024 * 1024)
    activation = max(MIN_ACTIVATION_MIB, latent_mib * ACTIVATION_FACTOR)
    report["models_mib"] = round(total, 2)
    report["activation_mib"] = round(activation, 2)
    report["extra_mib"] = float(extra)
    estimate = total + activation + float(extra)
    report["estimate_mib"] = round(estimate, 2)
    report["required_mib"] = round(estimate + reserve_mib, 2)
    report["verdict"] = "ALLOW" if report["required_mib"] <= report["budget_mib"] else "REFUSE"
    return report


def fmt(v):
    return f"{v:,.0f}" if float(v) == int(v) else f"{v:,.2f}"


def print_human(r):
    print(f"verdict: {r['verdict']}")
    for m in r["models"]:
        if m["size_mib"] is not None:
            print(f"model: {m['name']} = {fmt(m['size_mib'])} MiB ({m['size_source']})")
    if r["estimate_mib"] is not None:
        print(f"models total: {fmt(r['models_mib'])} MiB")
        print(f"activation estimate: {fmt(r['activation_mib'])} MiB")
        print(f"extra: {fmt(r['extra_mib'])} MiB")
        print(f"estimate: {fmt(r['estimate_mib'])} MiB")
        print(f"reserve: {fmt(r['reserve_mib'])} MiB")
        print(f"required: {fmt(r['required_mib'])} MiB")
        print(f"budget ({r['budget_source']}): {fmt(r['budget_mib'])} MiB")
    for e in r["errors"]:
        print(f"error: {e}")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="nebula_vram_guard.py",
        description="Pre-flight VRAM guard for Nebula/ComfyUI jobs (read-only).",
    )
    p.add_argument("--job", required=True, help="path to the job JSON file")
    p.add_argument("--gpu-mib", type=float, default=DEFAULT_GPU_MIB)
    p.add_argument("--reserve-mib", type=float, default=DEFAULT_RESERVE_MIB)
    p.add_argument("--free-mib", type=float, default=None,
                   help="currently free VRAM in MiB; overrides --gpu-mib as the budget")
    p.add_argument("--json", action="store_true", help="emit a structured JSON report")
    args = p.parse_args(argv)
    if args.gpu_mib <= 0 or args.reserve_mib < 0 or (args.free_mib is not None and args.free_mib <= 0):
        p.error("--gpu-mib must be positive, --reserve-mib non-negative, --free-mib positive")
    try:
        with open(args.job, "r", encoding="utf-8") as fh:
            job = json.load(fh)
    except FileNotFoundError:
        report = {"verdict": "INCOMPLETE", "models": [], "models_mib": None,
                  "activation_mib": None, "extra_mib": None, "estimate_mib": None,
                  "reserve_mib": args.reserve_mib,
                  "budget_mib": args.free_mib if args.free_mib is not None else args.gpu_mib,
                  "budget_source": "free" if args.free_mib is not None else "gpu",
                  "required_mib": None,
                  "errors": [f"job file not found: {args.job}"]}
        print(json.dumps(report, indent=2)) if args.json else print_human(report)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        report = {"verdict": "INCOMPLETE", "models": [], "models_mib": None,
                  "activation_mib": None, "extra_mib": None, "estimate_mib": None,
                  "reserve_mib": args.reserve_mib,
                  "budget_mib": args.free_mib if args.free_mib is not None else args.gpu_mib,
                  "budget_source": "free" if args.free_mib is not None else "gpu",
                  "required_mib": None,
                  "errors": [f"job file unreadable or unparseable: {exc}"]}
        print(json.dumps(report, indent=2)) if args.json else print_human(report)
        return 2
    report = evaluate(job, args.gpu_mib, args.reserve_mib, args.free_mib)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)
    return {"ALLOW": 0, "REFUSE": 1, "INCOMPLETE": 2}[report["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
