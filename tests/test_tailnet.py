"""Reading the tailnet (tailscale_mod/tailnet.py) with the fake CLI in
tests/fake: peers, resolve, ping, Serve status. The real `tailscale` is never
run, and only read-only commands are ever asked for."""
import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
FAKE = os.path.join(ROOT, "tests", "fake", "tailscale")

from tailscale_mod import tailnet  # noqa: E402

READ_ONLY = ({"status", "--json"}, {"serve", "status", "--json"})


@pytest.fixture
def fake(monkeypatch, tmp_path):
    log = tmp_path / "calls.log"
    monkeypatch.setenv("TAILSCALE_BIN", FAKE)
    monkeypatch.setenv("FAKE_TAILSCALE_LOG", str(log))
    tailnet._cache.update(at=0.0, data=None, error="")
    yield log
    for line in log.read_text().splitlines() if log.exists() else []:
        args = json.loads(line)
        assert set(args) in READ_ONLY or args[0] == "ping", f"a non read-only command was run: {args}"


def _iso(days_ago, now):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(now - days_ago * 86400, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def test_parse_peers_marks_self_shared_and_age():
    now = time.time()
    data = {"Self": {"HostName": "srv", "DNSName": "srv.tailA.ts.net.", "TailscaleIPs": ["100.64.0.1"], "OS": "linux"},
            "Peer": {"a": {"HostName": "PC", "DNSName": "pc.tailA.ts.net.", "TailscaleIPs": ["100.64.0.2"],
                           "OS": "windows", "Online": True, "LastSeen": _iso(0, now)},
                     "b": {"HostName": "old", "DNSName": "old.tailA.ts.net.", "TailscaleIPs": ["100.64.0.3"],
                           "OS": "linux", "Online": False, "LastSeen": _iso(40, now)},
                     "c": {"HostName": "x", "DNSName": "x.tailB.ts.net.", "TailscaleIPs": "100.64.0.4", "OS": "linux"},
                     "bad": "row"}}
    ps = {p["host"]: p for p in tailnet.parse_peers(data, now=now)}
    assert ps["srv"]["is_self"] and ps["srv"]["online"] and ps["srv"]["age_days"] == 0.0
    assert ps["pc"]["name"] == "PC" and ps["pc"]["os"] == "windows" and not ps["pc"]["shared"]
    assert ps["old"]["age_days"] > 30 and not ps["old"]["online"]
    assert ps["x"]["shared"] and ps["x"]["ips"] == []          # a string is not a list of addresses
    assert tailnet.parse_peers(None) == [] and tailnet.parse_peers({"Peer": []}) == []


def test_a_recent_handshake_counts_as_online():
    now = time.time()
    from datetime import datetime, timezone
    hs = datetime.fromtimestamp(now - 30, tz=timezone.utc).isoformat(timespec="microseconds")
    hs = hs.replace("+00:00", "") + "123Z"                    # nanosecond digits, as tailscale prints
    data = {"Self": {"DNSName": "srv.t.ts.net."},
            "Peer": {"b": {"HostName": "lap", "DNSName": "lap.t.ts.net.", "Online": False, "LastHandshake": hs}}}
    lap = [p for p in tailnet.parse_peers(data, now=now) if p["host"] == "lap"][0]
    assert lap["online"]
    data["Peer"]["b"]["LastHandshake"] = "0001-01-01T00:00:00Z"
    assert not [p for p in tailnet.parse_peers(data, now=now) if p["host"] == "lap"][0]["online"]


def test_peers_resolve_and_ping_with_the_fake_cli(fake):
    ps = {p["host"]: p for p in tailnet.peers()}
    assert set(ps) == {"home-server", "gaming-pc", "laptop", "phone", "friends-box"}
    assert ps["friends-box"]["shared"] and ps["home-server"]["is_self"]
    assert tailnet.resolve("gaming-pc") == "100.64.0.2"
    assert tailnet.resolve("home-server.tail0example.ts.net") == "100.64.0.1"   # IPv4 first
    assert tailnet.resolve("nope") is None
    assert tailnet.ping("100.64.0.2")["ok"] is True
    assert tailnet.ping("100.64.0.3")["ok"] is False


def test_ping_refuses_anything_that_is_not_a_machine(fake):
    for bad in ("", "--up", "-c", "a b", "x;rm -rf /", "$(id)"):
        r = tailnet.ping(bad)
        assert r["ok"] is False and "not a machine" in r["detail"]
    assert not fake.exists() or fake.read_text() == ""


def test_serve_status_is_read_and_funnel_marked(fake):
    s = tailnet.serve_status()
    assert s["ok"]
    by = {m["url"]: m for m in s["mounts"]}
    assert by["https://home-server.tail0example.ts.net:443/"]["target"] == "http://127.0.0.1:7000"
    assert not by["https://home-server.tail0example.ts.net:443/"]["funnel"]
    assert by["https://home-server.tail0example.ts.net:8443/api/telephony"]["funnel"]


def test_no_tailscale_installed(monkeypatch):
    monkeypatch.setenv("TAILSCALE_BIN", "/nonexistent/tailscale")
    tailnet._cache.update(at=0.0, data=None, error="")
    assert tailnet.peers(refresh=True) == []
    assert "not installed" in tailnet.last_error()
    assert tailnet.serve_status()["ok"] is False
