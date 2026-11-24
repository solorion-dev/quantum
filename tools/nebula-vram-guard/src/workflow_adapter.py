#!/usr/bin/env python3
"""workflow_adapter: translate a raw ComfyUI workflow JSON into a
nebula-vram-guard job JSON.

Read-only, stdlib-only, no network calls. The guard's pre-flight used
to run on a hand-written summary of a workflow; this adapter runs it
on the actual submitted workflow instead.

Two workflow shapes are supported:

  API format  top-level object mapping node-id ->
              {"class_type": ..., "inputs": {...}}
  UI format   {"nodes": [{"id": ..., "type": ...,
              "widgets_values": [...], "inputs": [...]}], "links": [...]}

Extraction is conservative: a value that cannot be confidently
extracted is a warning / INCOMPLETE, never a guess. Model entries
carry a name only -- the guard's known-size table (or its INCOMPLETE
discipline for unknown names) decides sizes. This adapter never
invents a size.

Incomplete (adapter report flag ``incomplete: true``; exit 2 in
--check mode, and exit 2 in adapter-only mode when nothing usable
could be extracted): unparseable file, neither format recognised,
zero models found, or zero latent dimensions found.

The emitted job JSON is exactly the guard's schema
{models, width, height, batch, extra_mib} plus an ``_adapter``
object {workflow_format, warnings, model_sources}. The guard's
evaluate() reads only the schema keys and ignores unknown top-level
keys (verified against nebula_vram_guard.evaluate), so the job can
be piped straight to the guard.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# class_type -> list of (input name, model kind). Order within a node
# follows the node's own input order in the workflow.
MODEL_FIELDS = {
    "CheckpointLoaderSimple": [("ckpt_name", "checkpoint")],
    "CheckpointLoader": [("ckpt_name", "checkpoint")],
    "UNETLoader": [("unet_name", "unet")],
    "LoraLoader": [("lora_name", "lora")],
    "LoraLoaderModelOnly": [("lora_name", "lora")],
    "CLIPLoader": [("clip_name", "clip")],
    "DualCLIPLoader": [("clip_name1", "clip"), ("clip_name2", "clip")],
    "VAELoader": [("vae_name", "vae")],
    "ControlNetLoader": [("control_net_name", "controlnet")],
}

LATENT_CLASSES = {"EmptyLatentImage", "EmptySD3LatentImage", "EmptyLatent"}
SAMPLER_CLASSES = {"KSampler", "KSamplerAdvanced"}

# Documented widgets_values positions for UI-format nodes, used only
# when the node's named widget inputs do not resolve the value.
# CheckpointLoader's widgets are [config, ckpt_name]; UNETLoader's
# are [unet_name, weight_dtype]; LoraLoader's are
# [lora_name, strength_model, strength_clip] (model/clip are links);
# CLIPLoader's are [clip_name, type, ...]; DualCLIPLoader's are
# [clip_name1, clip_name2, type, ...]; the latent nodes' are
# [width, height, batch_size].
UI_WIDGET_INDEX = {
    "CheckpointLoaderSimple": {"ckpt_name": 0},
    "CheckpointLoader": {"ckpt_name": 1},
    "UNETLoader": {"unet_name": 0},
    "LoraLoader": {"lora_name": 0},
    "LoraLoaderModelOnly": {"lora_name": 0},
    "CLIPLoader": {"clip_name": 0},
    "DualCLIPLoader": {"clip_name1": 0, "clip_name2": 1},
    "VAELoader": {"vae_name": 0},
    "ControlNetLoader": {"control_net_name": 0},
}
UI_LATENT_WIDGETS = ("width", "height", "batch_size")  # positions 0, 1, 2


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _add_model(models, sources, warnings, name, class_type):
    if not isinstance(name, str) or not name:
        warnings.append(f"{class_type}: model name missing or not a string; skipped")
        return
    if name in sources:
        return  # dedupe: a model loaded twice counts once
    sources[name] = class_type
    models.append({"name": name})


def _latent_dims(width, height, batch):
    if _is_number(width) and _is_number(height) and width > 0 and height > 0:
        b = batch if _is_number(batch) and batch > 0 else 1
        return (int(width), int(height), int(b))
    return None


def _register_latent(latents, dims, label):
    if dims is not None and dims not in latents:
        latents.append(dims)


# ---------------------------------------------------------------- API format

def _extract_api(data):
    models, sources, warnings, latents = [], {}, [], []
    nodes = data  # node-id -> {class_type, inputs}
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs") or {}
        if class_type in MODEL_FIELDS:
            for field, _kind in MODEL_FIELDS[class_type]:
                _add_model(models, sources, warnings, inputs.get(field), class_type)
        elif class_type in LATENT_CLASSES:
            dims = _latent_dims(inputs.get("width"), inputs.get("height"),
                                inputs.get("batch_size", 1))
            if dims:
                _register_latent(latents, dims, class_type)
            else:
                warnings.append(f"{class_type} node {node_id}: dimensions not extractable")
    # Follow sampler latent_image links when no direct latent was found
    # with obvious dimensions. Along this path only, a dimension that is
    # itself a link to a primitive node (inputs {"value": N}) is
    # resolved -- that is the one hop whose value is unambiguous.
    if not latents:
        for node_id, node in nodes.items():
            if not isinstance(node, dict) or node.get("class_type") not in SAMPLER_CLASSES:
                continue
            link = (node.get("inputs") or {}).get("latent_image")
            if isinstance(link, list) and len(link) == 2:
                target = nodes.get(str(link[0]))
                if isinstance(target, dict) and target.get("class_type") in LATENT_CLASSES:
                    t_inputs = target.get("inputs") or {}
                    dims = _latent_dims(_resolve_number(nodes, t_inputs.get("width")),
                                        _resolve_number(nodes, t_inputs.get("height")),
                                        _resolve_number(nodes, t_inputs.get("batch_size", 1)))
                    if dims:
                        _register_latent(latents, dims, target["class_type"])
    return models, sources, warnings, latents


def _resolve_number(nodes, value):
    """A literal number, or one hop through a primitive node's value."""
    if _is_number(value):
        return value
    if isinstance(value, list) and len(value) == 2:
        target = nodes.get(str(value[0]))
        if isinstance(target, dict):
            v = (target.get("inputs") or {}).get("value")
            if _is_number(v):
                return v
    return None


# ----------------------------------------------------------------- UI format

def _ui_widget_values(node):
    """Map widget name -> value using the node's named inputs.

    In UI format, inputs carrying a ``widget`` entry consume
    widgets_values in order. Returns {} when that mapping is not
    available, so callers fall back to documented positions.
    """
    widgets = node.get("widgets_values")
    inputs = node.get("inputs")
    if not isinstance(widgets, list) or not isinstance(inputs, list):
        return {}
    out = {}
    idx = 0
    for inp in inputs:
        if isinstance(inp, dict) and isinstance(inp.get("widget"), dict):
            name = inp["widget"].get("name")
            if idx < len(widgets) and isinstance(name, str):
                out[name] = widgets[idx]
            idx += 1
    return out


def _ui_field(node, class_type, field):
    named = _ui_widget_values(node)
    if field in named:
        return named[field]
    widgets = node.get("widgets_values")
    pos = UI_WIDGET_INDEX.get(class_type, {}).get(field)
    if isinstance(widgets, list) and pos is not None and pos < len(widgets):
        return widgets[pos]
    return None


def _extract_ui(data):
    models, sources, warnings, latents = [], {}, [], []
    nodes = data.get("nodes") or []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        class_type = node.get("type")
        if class_type in MODEL_FIELDS:
            for field, _kind in MODEL_FIELDS[class_type]:
                _add_model(models, sources, warnings,
                           _ui_field(node, class_type, field), class_type)
        elif class_type in LATENT_CLASSES:
            named = _ui_widget_values(node)
            widgets = node.get("widgets_values") or []
            vals = {}
            for i, fname in enumerate(UI_LATENT_WIDGETS):
                if fname in named:
                    vals[fname] = named[fname]
                elif i < len(widgets):
                    vals[fname] = widgets[i]
            dims = _latent_dims(vals.get("width"), vals.get("height"),
                                vals.get("batch_size", 1))
            if dims:
                _register_latent(latents, dims, class_type)
            else:
                warnings.append(f"{class_type} node {node.get('id')}: dimensions not extractable")
    return models, sources, warnings, latents


# -------------------------------------------------------------------- driver

def adapt(data):
    """Translate parsed workflow JSON into (job, adapter_report)."""
    warnings = []
    if isinstance(data, dict) and isinstance(data.get("nodes"), list):
        fmt = "ui"
        models, sources, w, latents = _extract_ui(data)
        warnings.extend(w)
    elif isinstance(data, dict) and any(
            isinstance(v, dict) and "class_type" in v for v in data.values()):
        fmt = "api"
        models, sources, w, latents = _extract_api(data)
        warnings.extend(w)
    else:
        return None, {"workflow_format": None, "warnings": warnings,
                      "model_sources": {}, "incomplete": True,
                      "errors": ["workflow format not recognised "
                                 "(neither API nor UI format)"]}
    if len(latents) > 1:
        others = ", ".join(f"{w}x{h} batch {b}" for w, h, b in latents[1:])
        warnings.append(
            f"multiple distinct latent sizes found; using first "
            f"({latents[0][0]}x{latents[0][1]} batch {latents[0][2]}); others: {others}")
    errors = []
    if not models:
        errors.append("no model loader nodes found")
    if not latents:
        errors.append("no latent dimensions found")
    job = {"models": models, "extra_mib": 0}
    if latents:
        job["width"], job["height"], job["batch"] = latents[0]
    job["_adapter"] = {
        "workflow_format": fmt,
        "warnings": warnings,
        "model_sources": sources,
    }
    report = {"workflow_format": fmt, "warnings": warnings,
              "model_sources": sources,
              "incomplete": bool(errors), "errors": errors}
    return job, report


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="workflow_adapter.py",
        description="Translate a ComfyUI workflow JSON into a nebula-vram-guard job JSON (read-only).")
    p.add_argument("--workflow", required=True, help="path to the workflow JSON file")
    p.add_argument("--out", default=None, help="write the job JSON here (default: stdout)")
    p.add_argument("--check", action="store_true",
                   help="also run the guard on the adapted job; exit code is the guard's")
    p.add_argument("--gpu-mib", type=float, default=8192)
    p.add_argument("--reserve-mib", type=float, default=1024)
    p.add_argument("--free-mib", type=float, default=None)
    p.add_argument("--json", action="store_true", help="emit a machine-readable adapter report")
    args = p.parse_args(argv)

    job, report, load_error = None, None, None
    try:
        with open(args.workflow, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        load_error = f"workflow file not found: {args.workflow}"
    except (OSError, json.JSONDecodeError) as exc:
        load_error = f"workflow file unreadable or unparseable: {exc}"
    if load_error is not None:
        report = {"workflow_format": None, "warnings": [], "model_sources": {},
                  "incomplete": True, "errors": [load_error]}
    else:
        job, report = adapt(data)

    verdict = None
    guard_report = None
    if args.check:
        import nebula_vram_guard
        if job is None:
            verdict = "INCOMPLETE"
            guard_report = {"verdict": "INCOMPLETE", "errors": report["errors"],
                            "required_mib": None, "budget_mib": None}
        else:
            guard_report = nebula_vram_guard.evaluate(
                job, args.gpu_mib, args.reserve_mib, args.free_mib)
            verdict = guard_report["verdict"]

    if job is not None:
        text = json.dumps(job, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        elif not args.json:
            print(text)

    if args.json:
        out = {"incomplete": report["incomplete"], "errors": report["errors"],
               "workflow_format": report["workflow_format"],
               "warnings": report["warnings"],
               "model_sources": report["model_sources"], "job": job}
        if args.check:
            out["verdict"] = verdict
            out["guard"] = guard_report
        print(json.dumps(out, indent=2))
    elif args.check:
        print(f"adapter: format={report['workflow_format']} "
              f"models={len(job['models']) if job else 0} "
              f"incomplete={report['incomplete']}")
        for w in report["warnings"]:
            print(f"warning: {w}")
        for e in report["errors"]:
            print(f"error: {e}")
        if guard_report is not None:
            print(f"verdict: {guard_report['verdict']}")
            if guard_report.get("required_mib") is not None:
                print(f"required: {guard_report['required_mib']:,.0f} MiB")
                print(f"budget: {guard_report['budget_mib']:,.0f} MiB")

    if args.check:
        return {"ALLOW": 0, "REFUSE": 1, "INCOMPLETE": 2}[verdict]
    return 2 if report["incomplete"] else 0


if __name__ == "__main__":
    sys.exit(main())
