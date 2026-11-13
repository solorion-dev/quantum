# Cooper local twin (pre-reconciliation)

Seeded from Codex `quantum-os-workstation`; this is the divergent local copy (`local-quantum-os-workstation`) preserved verbatim for reference. The canonical SKILL.md wins where they conflict.

# Quantum OS workstations

**Read `/home/scott/quantum-os/README.md` first.** It holds the measured numbers and is the
source of truth; this skill is the procedure.

Quantum OS is a *layer* — Ubuntu LTS plus a defined package set and defaults — with two build
targets: the container image agents use today, and an ISO for bare metal later. Do not let the
two drift; `image/Dockerfile` is authoritative for what the layer contains.

## Creating a workstation

```sh
docker run -d --name ws-<agent> \
  --memory=1536m --memory-swap=1536m \
  -e AGENT_NAME=<agent> -e TOOLS_TOKEN="$(cat <tokenfile>)" \
  -e TS_AUTHKEY="$(cat /home/scott/tritium-workstations/ts-authkey.txt)" \
  -e TS_TAG=tag:agent-sandbox \
  -v /mnt/fast/quantum-os/<agent>:/home/agent \
  quantum-os/workstation:latest
```

- **Name it `ws-<agent>`.** The RAM broker resolves containers by that exact pattern; a
  differently-named container cannot be granted memory.
- **Always set a memory ceiling.** Workstations ran with `Memory=0` — no limit — until
  2026-09-17. One agent could have OOM'd the host.
- **Home directory on `/mnt/fast`**, not `/`. Root has ~22 G free; `/mnt/fast` has ~397 G.
- `QOS_PROFILE=human` adds XFCE and noVNC on `:6080`. Default `agent` is headless.

## Baselines

| profile | ceiling | measured |
|---|---|---|
| `agent` | 1.5 GiB | idle 27.8 MiB · Chrome, 3 tabs 317 MiB |
| `human` | 4.0 GiB | desktop + browser |

A ceiling is **not** a reservation — an unused limit costs nothing, so be generous.

## Asking for more memory (STEWARD)

```sh
curl -s -X POST http://172.17.0.1:8947/request \
  -H "Authorization: Bearer $(cat /home/scott/quantum-os/broker/token.txt)" \
  -H 'Content-Type: application/json' \
  -d '{"agent":"axiom","gib":6,"minutes":45,"reason":"Blender turntable render"}'
```

State the real duration; the grant expires on its own and the ceiling drops back. `GET /status`
shows host memory, policy and live grants. `POST /release {"agent":"..."}` hands it back early.

**The arithmetic decides, the NPU only advises.** Hard gates: 12 GiB per grant, 240 min max,
never leave the host under 8 GiB free, never more than 50% of free memory in one grant. Never
rewrite the broker so a model's opinion can override a gate — a hallucination would hand out
40 GiB on a box carrying ~34 GiB of resident models.

## Troubleshooting, in the order things actually go wrong

- **Container exits instantly, traceback ends `OSError: [Errno 99] Cannot assign requested
  address`.** `server.py` tried to bind `172.17.0.1` — the *host* bridge gateway — inside the
  container netns. The entrypoint pins `BIND_HOST` to the container's own address; if you
  bypassed the entrypoint, pass `BIND_HOST` yourself.
- **Browser will not install or run.** Ubuntu's `chromium` is a snap and snapd does not run in a
  container. Chrome comes from Google's real apt repo — keep it that way.
- **Not on the tailnet.** `TS_AUTHKEY` missing or expired. The entrypoint soft-fails to
  bridge-only and says so in its log; `docker logs ws-<agent> | grep '\[qos\]'`. Keys must be
  **ephemeral, pre-authorised and tagged**, or every restart leaves a dead node behind.
- **Grant approved but nothing changed.** `docker update` succeeds on a *stopped* container.
  Check `docker inspect ws-<agent> --format '{{.State.Running}}'` before believing a grant.
- **Invisible to `tritium-svc`.** It is not in `services.json`. The catalogue is the single
  source of truth; a container nobody catalogued is a container nobody monitors.

## Rules that outrank convenience

- Never bind a service to `0.0.0.0` on this box. Bind the docker bridge gateway or the
  container's own address.
- Never put `ts-authkey.txt`, `broker/token.txt` or any credential in Drive or the Codex.
- Tag sandboxes; never tag Scott's personal devices — they lose `autogroup:self` and key expiry.
  Consequence: tagged nodes cannot SSH to untagged ones, and `tritium-linux` is untagged.
- Measure before claiming. Every number in `quantum-os/README.md` has a date and a command.
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
