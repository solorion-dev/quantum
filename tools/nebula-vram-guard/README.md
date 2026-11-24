# nebula-vram-guard

Pre-flight VRAM refusal for Nebula / ComfyUI jobs. Read-only,
stdlib-only Python 3.10+, no network calls (operator-snapshot style,
like settle-check and codex-lint-drift).

## Why

On 2026-11-22 a Nebula job asked an 8 GB RTX card to stage roughly
15.4 GB; the ComfyUI API froze and the stall took fleet attention to
untangle. Production Nebula has monitoring only — nothing refused the
oversized job before submit. This tool is that pre-flight guard: run
it on a job description before submitting, and an oversized job is
REFUSED with the numbers, instead of freezing the API.

## Job JSON

```json
{
  "models": [{"name": "model-file.safetensors", "size_mib": 6938}],
  "width": 1024,
  "height": 1024,
  "batch": 1,
  "extra_mib": 0
}
```

- `models` (required, non-empty): each entry needs a `name`.
  `size_mib` may be omitted **only** when the name matches the
  built-in known-size table below; an unknown name without a size is
  INCOMPLETE, never guessed silently.
- `width`, `height` (required, positive): output dimensions in px.
- `batch` (optional, default 1).
- `extra_mib` (optional, default 0): known extra allocations (LoRA
  stacks, control nets, upscalers) the operator wants counted.

## Known-size table (estimates)

Filename-pattern classes, in MiB. These are **estimates** of common
checkpoint size classes, not measurements of any specific file — pass
an explicit `size_mib` whenever the real size is known.

| Pattern | MiB | Class |
| --- | ---: | --- |
| sd15 / sd1.5 / v1-5-pruned | 2135 | SD 1.5 fp16 |
| sdxl / sd_xl | 6938 | SDXL fp16 |
| flux (fp16) | 23802 | FLUX.1 fp16 |
| flux fp8 | 11903 | FLUX.1 fp8 |
| wan2.1 | 16000 | Wan 2.1 video (class estimate) |
| wan2.1-t2v-14b | 28000 | Wan 2.1 14B (class estimate) |

## Estimate formula

```
latent_bytes   = (width/8) * (height/8) * 4 channels * 4 bytes * batch
activation_mib = max(256, latent_mib * 8)
estimate_mib   = sum(model sizes) + activation_mib + extra_mib
required_mib   = estimate_mib + reserve_mib   (default reserve 1024)
budget_mib     = free_mib if given, else gpu_mib (default 8192)
```

The activation term is deliberately conservative: the raw latent is
small, but a real sampler holds UNet activations, VAE decode buffers,
and intermediate tensors well beyond the latent itself, so the latent
is scaled by 8 with a 256 MiB floor. This is a conservative
pre-flight estimate, **not a profiler** — it exists to refuse jobs
that obviously cannot fit, not to predict exact peak usage.

## Verdicts & exit codes

| Code | Verdict | Meaning |
| --- | --- | --- |
| 0 | ALLOW | required <= budget |
| 1 | REFUSE | required > budget |
| 2 | INCOMPLETE | job file missing/unparseable, zero models, unknown model size, non-positive dimensions |

Exit 2 is overloaded like its siblings: an argparse usage error also
exits 2 but prints a usage message and **no verdict line**, which is
how you tell it from an INCOMPLETE verdict.

## Run it

```bash
python3 src/nebula_vram_guard.py --job examples/job-allow.json
# verdict: ALLOW ... required: 3,415 MiB, budget (gpu): 8,192 MiB -> exit 0

python3 src/nebula_vram_guard.py --job examples/job-refuse.json
# the 2026-11-22 shape: required 15,400 MiB vs 8,192 MiB -> REFUSE, exit 1

python3 src/nebula_vram_guard.py --job job.json --free-mib 5200   # budget = free VRAM
python3 src/nebula_vram_guard.py --job job.json --json           # structured report
python3 -m pytest tests/ -q                                       # self-test
```

`--json` emits the full breakdown: per-model sizes and their source
(explicit vs known-table estimate), activation, extra, estimate,
reserve, budget and its source, required, verdict, and errors.

The tool is read-only: it opens the job file and writes nothing (a
test pins the input's bytes and mtime as unchanged after a run).

## Workflow adapter (`src/workflow_adapter.py`)

The guard judges a job JSON — but the thing actually submitted to
ComfyUI is a workflow JSON. `workflow_adapter.py` translates a raw
ComfyUI workflow into guard job JSON, so the pre-flight runs on the
actual submitted workflow instead of a hand-written summary. It is
read-only, stdlib-only, and makes no network calls (it writes only
to the `--out` file you name, never to the workflow).

Both workflow shapes are supported:

- **API format** — top-level object mapping node-id →
  `{class_type, inputs}`.
- **UI format** — `{nodes: [{id, type, widgets_values, inputs}],
  links}`. Values come from the nodes' named widget inputs where
  present, falling back to the documented `widgets_values` order
  per node type.

What is extracted:

- **Models** (name only — never a size; the guard's known-size
  table or its INCOMPLETE discipline decides): `CheckpointLoaderSimple`
  / `CheckpointLoader` (`ckpt_name`), `UNETLoader` (`unet_name`),
  `LoraLoader` / `LoraLoaderModelOnly` (`lora_name`), `CLIPLoader`
  (`clip_name`), `DualCLIPLoader` (`clip_name1` + `clip_name2`),
  `VAELoader` (`vae_name`), `ControlNetLoader` (`control_net_name`).
  Identical filenames are deduped — a checkpoint loaded once counts
  once — and discovery order is preserved.
- **Dimensions** from `EmptyLatentImage` / `EmptySD3LatentImage` /
  `EmptyLatent` (`width`, `height`, `batch_size`). In API format,
  when dimensions are not directly obvious, the adapter follows a
  `KSampler` / `KSamplerAdvanced` `latent_image` link to its source
  latent node (resolving one hop through a primitive node's `value`
  when a dimension is itself a link). If several distinct latent
  sizes exist, the first in node order is used and a warning names
  the others.

The output is exactly the guard's job schema plus an `_adapter`
object (`workflow_format`, `warnings`, `model_sources` mapping each
model name to the loader class that referenced it). The guard's
`evaluate()` reads only the schema keys and ignores unknown
top-level keys, so the adapted job can be piped straight to it.

**INCOMPLETE discipline:** an unparseable file, a workflow in
neither format, zero models found, or zero latent dimensions found
is INCOMPLETE — the adapter flags `incomplete: true`, still emits
what it found, and never guesses a value it could not extract.

```bash
python3 src/workflow_adapter.py --workflow workflow.json --out job.json
python3 src/nebula_vram_guard.py --job job.json        # then guard it

python3 src/workflow_adapter.py --workflow workflow.json --check
# adapt + guard in one step; exit code is the guard's (0/1/2)
python3 src/workflow_adapter.py --workflow workflow.json --check --json
python3 src/workflow_adapter.py --workflow workflow.json --check --free-mib 5200
```

Worked examples (against the default 8,192 MiB budget):

```bash
python3 src/workflow_adapter.py --workflow examples/workflow-api-sd15.json --check
# CheckpointLoaderSimple v1-5-pruned + EmptyLatentImage 512x512 batch 1
# -> ALLOW, required 3,415 MiB vs budget 8,192 MiB, exit 0

python3 src/workflow_adapter.py --workflow examples/workflow-api-wan-refuse.json --check
# UNETLoader wan2.1-t2v-14b + 1280x720 latent
# -> REFUSE, required 29,280 MiB vs budget 8,192 MiB, exit 1
```
