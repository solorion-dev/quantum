# Quantum CLI (tools/quantum-cli)

The official **Quantum CLI** — the fleet's scriptable command surface over
Quantum services (TRK-0044 · goal `goal_c4d2b21c0b8f` · quantum#132).

Scotty proposed it for server ops (service status, disk usage, log tailing)
with a polished terminal UX. The Bubbletea TUI spike lives at
`~/workspace/quantum-cli-prototype` (mock data); **this tool is the real-data,
non-interactive core** that spike's README asked for — the commands fleet
agents can script against. Wiring the TUI onto this core is the next slice.

## Build

Requires Go 1.21+. Stdlib only — no module downloads.

```bash
cd tools/quantum-cli
go build -o quantum .
go test ./...
```

## Usage

```bash
quantum status                  # service health (hub /api/status)
quantum services                # service registry (hub /api/services)
quantum disks                   # disk usage, 85/90/95 thresholds (hub /api/storage)
quantum vitals                  # CPU/load/memory/swap/GPUs (hub /api/vitals)
quantum logs hub-api -n 100     # journal tail (hub /api/logs)
quantum tracker list            # work tracker board
quantum tracker get TRK-0044    # one tracker record
quantum memory search rules     # search the Hive
```

Every command takes `--json`. `--fixture` runs against the bundled snapshot
(offline/demo/verification). `--hub URL` or `QUANTUM_HUB_URL` sets the hub
base (default `http://127.0.0.1:8091` — the hub is tailnet-only);
`QUANTUM_TOKEN` is sent as a bearer header when set. No credential values
live in this repo — pointers only.

## Live vs fixture in v0

- **Live-wired:** status, services, disks, vitals, logs — field-for-field
  against hub-api's handlers (`/api/status`, `/api/services`, `/api/storage`,
  `/api/vitals`, `/api/logs`).
- **Fixture provider:** tracker and memory have no hub HTTP route, so v0
  serves them behind a provider interface from bundled snapshots of real
  data (the 2026-10-25 `in_progress` board, TRK-0044's full record, Hive
  2294–2298). Their live provider — over the hub MCP facade — is the next
  slice and slots in behind the same interface.
- **Gated:** write commands (`services restart|start|stop`, `tracker add`)
  are designed but refuse in v0 (exit 3, nothing sent). Writes land after
  review of this PR and hub-api#34.

Full plan: `~/workspace/quantum-cli/PLAN.md` (workspace) and the TRK-0044
tracker record.
