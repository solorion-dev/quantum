# Tailscale ACLs and Tags — Reference

Tailnet policy file (huJSON — JSON with comments). Default-deny.

## Current Syntax: Grants

```jsonc
{
  "tagOwners": {
    "tag:server": ["autogroup:admin"],
    "tag:exit-node": ["autogroup:admin"]
  },
  "grants": [
    {
      "src": ["autogroup:member"],
      "dst": ["tag:server"],
      "ip": ["tcp:8090", "tcp:8092", "tcp:443"]
    },
    {
      "src": ["scotty@tailnet"],
      "dst": ["tag:server"],
      "ip": ["tcp:22", "tcp:8123"]
    }
  ],
  "ssh": [
    {
      "action": "check",
      "src": ["scotty@tailnet"],
      "dst": ["tag:server"],
      "users": ["scott", "root"]
    }
  ],
  "nodeAttrs": [
    {"target": ["tag:server"], "attr": ["funnel"]}
  ],
  "autoApprovers": {
    "routes": {"0.0.0.0/0": ["tag:exit-node"]},
    "exitNode": ["tag:exit-node"]
  },
  "tests": [
    {"src": "scotty@tailnet", "dst": "tag:server", "accept": ["tcp:22"]}
  ]
}
```

## Key Concepts

- **Tags** identify machines (e.g., `tag:server` on Tritium)
- **tagOwners** controls who can apply tags
- **grants** use src/dst/ip (current syntax; legacy `acls` still works)
- **List ports explicitly** — broad grant for services, narrow for admin
- **tests** validate the policy on save
- Policy pushes to nodes within ~1 minute

## Example: Tritium Home Server

```jsonc
{
  "tagOwners": {
    "tag:server": ["autogroup:admin"]
  },
  "grants": [
    // All members can reach service ports
    {
      "src": ["autogroup:member"],
      "dst": ["tag:server"],
      "ip": ["tcp:8090", "tcp:8092", "tcp:8094", "tcp:8099", "tcp:8100", "tcp:8080", "tcp:443"]
    },
    // Only Scotty can SSH or reach admin ports
    {
      "src": ["scotty@tailnet"],
      "dst": ["tag:server"],
      "ip": ["tcp:22", "tcp:8123"]
    }
  ]
}
```

## Docs
https://tailscale.com/kb/1192/acl-syntax
