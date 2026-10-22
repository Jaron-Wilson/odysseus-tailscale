"""The tailnet, read from the `tailscale` command on this server.

Only read-only commands are ever run, with fixed arguments and no shell:

    tailscale status --json         the machines (this server and its peers)
    tailscale ping -c 1 <ip|name>   whether one machine answers
    tailscale serve status --json   what Tailscale Serve and Funnel publish

Nothing here changes the tailnet, Serve or Funnel. `TAILSCALE_BIN` picks the
command (tests point it at a fake that prints canned JSON).
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

PEERS_TTL = 10.0
_cache: Dict[str, Any] = {"at": 0.0, "data": None, "error": ""}
_lock = threading.Lock()

# A tailnet IP, or a MagicDNS / host name. Nothing that could be an option.
_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")


def binary() -> str:
    return os.environ.get("TAILSCALE_BIN") or "tailscale"


def run(args: List[str], timeout: float = 10.0) -> Dict[str, Any]:
    """Run `tailscale <args>`: {rc, out, err}. rc -1 when it could not run."""
    try:
        p = subprocess.run([binary()] + args, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "out": p.stdout, "err": (p.stderr or "").strip()[:300]}
    except FileNotFoundError:
        return {"rc": -1, "out": "", "err": "The tailscale command is not installed on this server."}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "out": "", "err": f"tailscale {args[0]} timed out after {timeout:.0f}s"}
    except OSError as e:
        return {"rc": -1, "out": "", "err": str(e)[:300]}


def status_json() -> Optional[dict]:
    """`tailscale status --json`, or None (the reason is in last_error())."""
    r = run(["status", "--json"])
    if r["rc"] != 0:
        _cache["error"] = r["err"] or f"tailscale status exited with {r['rc']}"
        return None
    try:
        data = json.loads(r["out"])
    except ValueError:
        _cache["error"] = "tailscale status did not print JSON"
        return None
    if not isinstance(data, dict):
        _cache["error"] = "tailscale status printed something unexpected"
        return None
    _cache["error"] = ""
    return data


def last_error() -> str:
    return _cache["error"]


def _short(dns: str) -> str:
    return (dns or "").rstrip(".").split(".")[0].lower()


def _suffix(dns: str) -> str:
    return ".".join((dns or "").rstrip(".").split(".")[1:]).lower()


def _ts(value: str) -> Optional[float]:
    if not value or value.startswith("0001"):
        return None
    try:
        # Tailscale prints nanoseconds; Python reads up to microseconds.
        return datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def parse_peers(data: Optional[dict], now: Optional[float] = None) -> List[Dict[str, Any]]:
    """This server and its peers, in the shape Odysseus's `network.peers`
    capability uses: host, name, dns, ips, os, online, last_seen, age_days,
    is_self, shared.

    Peers shared in from another tailnet are marked `shared`: they are
    someone else's machines, not the user's.
    """
    if not isinstance(data, dict):
        return []
    now = now or time.time()
    me = data.get("Self") if isinstance(data.get("Self"), dict) else {}
    my_suffix = _suffix(me.get("DNSName", ""))
    out = []

    def rec(p: dict, is_self: bool) -> Dict[str, Any]:
        dns = (p.get("DNSName") or "").rstrip(".")
        last = p.get("LastSeen") or ""
        seen = _ts(last)
        age_days = max(0.0, (now - seen) / 86400) if seen else None
        # Tailscale's Online flag comes from its control server and can blink
        # off for a machine that is plainly reachable. A direct handshake in
        # the last few minutes counts as online too.
        online = bool(p.get("Online"))
        hs = _ts(p.get("LastHandshake") or "")
        if not online and hs:
            online = now - hs < 180
        ips = p.get("TailscaleIPs") if isinstance(p.get("TailscaleIPs"), list) else []
        return {
            "host": _short(dns) or (p.get("HostName") or "").lower(),
            "name": p.get("HostName") or _short(dns),
            "dns": dns,
            "ips": [i for i in ips if isinstance(i, str)],
            "os": (p.get("OS") or "").lower(),
            "online": True if is_self else online,
            "last_seen": "" if is_self else last,
            "age_days": 0.0 if is_self else age_days,
            "is_self": is_self,
            "shared": bool(my_suffix) and _suffix(dns) != my_suffix,
        }

    if me:
        out.append(rec(me, True))
    peers = data.get("Peer") if isinstance(data.get("Peer"), dict) else {}
    for p in peers.values():
        if isinstance(p, dict):
            out.append(rec(p, False))
    return [p for p in out if p["host"]]


def peers(refresh: bool = False) -> List[Dict[str, Any]]:
    with _lock:
        if refresh or time.time() - _cache["at"] > PEERS_TTL:
            _cache["data"] = status_json()
            _cache["at"] = time.time()
        return parse_peers(_cache["data"])


def find(all_peers: List[Dict[str, Any]], host_or_ip: str) -> Optional[Dict[str, Any]]:
    h = (host_or_ip or "").strip().lower().rstrip(".")
    if not h:
        return None
    for p in all_peers:
        if h in [i.lower() for i in p["ips"]] or h == p["dns"].lower() or h == p["host"] or h == p["name"].lower():
            return p
    short = h.split(".")[0]
    return next((p for p in all_peers if p["host"] == short), None)


def resolve(host: str) -> Optional[str]:
    """A tailnet IPv4 (else IPv6) for a machine name, or None."""
    p = find(peers(), host)
    if not p:
        return None
    v4 = [i for i in p["ips"] if "." in i]
    return (v4 or p["ips"] or [None])[0]


def valid_target(target: str) -> bool:
    t = (target or "").strip()
    if not t or t.startswith("-"):
        return False
    try:
        ipaddress.ip_address(t)
        return True
    except ValueError:
        return bool(_TARGET_RE.match(t))


def ping(target: str) -> Dict[str, Any]:
    """One `tailscale ping`: {ok, detail}."""
    if not valid_target(target):
        return {"ok": False, "detail": "not a machine name or tailnet address"}
    r = run(["ping", "-c", "1", "--timeout", "5s", target.strip()], timeout=12)
    out = (r["out"] or "").strip()
    return {"ok": r["rc"] == 0 and "pong" in out.lower(), "detail": (out or r["err"])[:300]}


def serve_status() -> Dict[str, Any]:
    """What Tailscale Serve and Funnel publish (read only): {ok, mounts, error}.

    Each mount is {url, path, target, funnel}."""
    r = run(["serve", "status", "--json"])
    if r["rc"] != 0:
        return {"ok": False, "mounts": [], "error": r["err"] or "tailscale serve status failed"}
    try:
        data = json.loads(r["out"] or "{}") or {}
    except ValueError:
        return {"ok": False, "mounts": [], "error": "tailscale serve status did not print JSON"}
    return {"ok": True, "mounts": parse_serve(data), "error": ""}


def parse_serve(data: Any) -> List[Dict[str, Any]]:
    """Mounts from `tailscale serve status --json` (its ServeConfig)."""
    if not isinstance(data, dict):
        return []
    funnel = data.get("AllowFunnel") if isinstance(data.get("AllowFunnel"), dict) else {}
    out = []
    web = data.get("Web") if isinstance(data.get("Web"), dict) else {}
    for hostport, cfg in web.items():
        handlers = (cfg or {}).get("Handlers") if isinstance(cfg, dict) else None
        for path, h in (handlers or {}).items():
            if not isinstance(h, dict):
                continue
            target = h.get("Proxy") or h.get("Path") or ("text" if h.get("Text") else "")
            out.append({"url": f"https://{hostport}{path}", "path": path, "target": str(target)[:200],
                        "funnel": bool(funnel.get(hostport))})
    tcp = data.get("TCP") if isinstance(data.get("TCP"), dict) else {}
    for port, cfg in tcp.items():
        if isinstance(cfg, dict) and cfg.get("TCPForward"):
            out.append({"url": f"tcp:{port}", "path": "", "target": str(cfg["TCPForward"])[:200],
                        "funnel": any(k.endswith(f":{port}") for k, v in funnel.items() if v)})
    return sorted(out, key=lambda m: m["url"])
