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

## Run without Odysseus

The Machines page works on its own, on any machine where `tailscale status` works for the user running it. With no `ODYSSEUS_URL` in its environment the mod runs standalone: it asks for a password
instead of trusting Odysseus's signed headers, keeps its settings and data in files under `MOD_DATA_DIR`,
and writes notifications to its log.

```bash
git clone https://github.com/Jaron-Wilson/odysseus-tailscale.git && cd odysseus-tailscale
# Python 3.10 or newer, standard library only; the tailscale CLI signed in on this machine
MOD_PASSWORD=pick-one python3 -m tailscale_mod      # then open http://127.0.0.1:8765/
```

| Variable | Default | Meaning |
|---|---|---|
| `MOD_PASSWORD` | made up and printed at start | The sign-in password (one local user) |
| `MOD_PORT` | `8765` | The port it listens on |
| `MOD_HOST` | `127.0.0.1` | The address it listens on. It speaks plain HTTP: to reach it from another machine, put HTTPS in front (for example `tailscale serve`) rather than listening on `0.0.0.0` |
| `MOD_DATA_DIR` | `./data` | Where its settings and data are kept |
| `TAILSCALE_BIN` | `tailscale` on `PATH` | The Tailscale command to run |

What works standalone:

- The Machines page (`tailscale status --json`), Ping and the Serve overview, all read only

What needs Odysseus:

- The `network.peers` capability that other mods and Odysseus's model discovery use
- The agent tools in Odysseus's chat

`tests/test_standalone.py` starts it this way, as its own process, and checks the sign-in, that
forged Odysseus headers are ignored, and the pages.

## Develop

```
python -m odysseus_mod.devcore            # run it under a stand-in core
TAILSCALE_BIN=tests/fake/tailscale python -m odysseus_mod.devcore   # with canned machines
python -m pytest -q                       # tests use tests/fake/tailscale, never the real CLI
```

Standard library only. `TAILSCALE_BIN` picks the command (default `tailscale` on `PATH`).
