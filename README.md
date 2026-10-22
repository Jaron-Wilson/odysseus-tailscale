# Tailscale for Odysseus

An [Odysseus](https://github.com/Jaron-Wilson/odysseus) add-on that brings the machines on your
tailnet into Odysseus. It provides the core's `network.peers` capability, so with it installed:

- **Settings > Devices** lists your computers and phones by machine, with **Ping**.
- **Model discovery** also scans the model servers on your other online machines.
- Host names DNS does not know (a MagicDNS name on a server without MagicDNS) still resolve.
- A **Machines** tab (System group) shows every machine with its OS, address and last seen, and
  what **Tailscale Serve** and **Funnel** publish from this server.
- The agent gets two read-only tools: `tailnet_machines` and `tailnet_ping`.

Without the add-on, Odysseus keeps working: MCP servers and devices you add by hand still work,
discovery scans this server, Docker's host and the hosts in its environment, and Settings >
Devices offers "Install the Tailscale add-on".

**Read only.** It runs only `tailscale status --json`, `tailscale ping -c 1 <machine>` and
`tailscale serve status --json`, with fixed arguments and no shell. It never runs `tailscale up`,
`serve`, `funnel` or anything else that changes your tailnet. Set up Tailscale yourself.

## Install

1. Install Tailscale on the Odysseus server and sign in (`tailscale up`), as the same user
   Odysseus runs as or with `tailscale set --operator=$USER`, so `tailscale status` works
   without sudo.
2. In Odysseus: Settings > Mods > Browse, search **tailscale**, then Review and install (or
   paste `git@github.com:Jaron-Wilson/odysseus-tailscale.git`). It asks for no permissions.
3. Enable it. It starts with Odysseus (`start: boot`), since the core asks it for machines.

## Migrating from the built-in Tailscale support

Nothing to copy. There are no keys or tokens: the add-on reads the server's own `tailscale`
login. Your machine preferences (label, preferred for heavy work, GPU, SSH user), linked devices,
enrollments and MCP servers stay in Odysseus (`machines.json`, `devices.json` and the database),
because they are the core's own data and work with any `network.peers` provider.

To check the server's tailnet before installing (read only):

```
tailscale status --json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("Peer") or {}), "peers")'
```

## The capability

Odysseus calls `/mod/cap/network.peers/<action>` with a signed identity (see `docs/mods.md` in
Odysseus, "Capability providers"):

| Action | Answers |
|---|---|
| `GET peers` | `{ok, peers: [{host, name, dns, ips, os, online, last_seen, age_days, is_self, shared}], error}` |
| `GET resolve?host=` / `POST resolve {host}` | `{ip}` (IPv4 first), or `{ip: null}` |
| `POST ping {target}` | `{ok, detail}` from one `tailscale ping` |
| `GET serve` | `{ok, mounts: [{url, path, target, funnel}], error}` |

## Develop

```
python -m odysseus_mod.devcore            # run it under a stand-in core
TAILSCALE_BIN=tests/fake/tailscale python -m odysseus_mod.devcore   # with canned machines
python -m pytest -q                       # tests use tests/fake/tailscale, never the real CLI
```

Standard library only. `TAILSCALE_BIN` picks the command (default `tailscale` on `PATH`).
