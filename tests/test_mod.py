"""The add-on under the stand-in core (odysseus_mod.devcore), as Odysseus runs
it: the network.peers capability with a signed identity, the Machines page,
the card and the tools. The fake `tailscale` in tests/fake answers."""
import json
import os
import sys
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from odysseus_mod.devcore import DevCore  # noqa: E402


def get(url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.fixture(scope="module")
def core(tmp_path_factory):
    os.environ["TAILSCALE_BIN"] = os.path.join(ROOT, "tests", "fake", "tailscale")
    c = DevCore(ROOT, port=0, user="alice", state_dir=str(tmp_path_factory.mktemp("devcore")))
    c.serve()
    c.start_mod()
    yield c
    c.close()


def cap(core, action, method="GET", body=None):
    conn, r = core.mod_request(method, f"/mod/cap/network.peers/{action}",
                               body=json.dumps(body).encode() if body is not None else None,
                               user="odysseus-core", headers={"Content-Type": "application/json"})
    data = r.read()
    conn.close()
    return r.status, json.loads(data)


def test_manifest_provides_network_peers_and_has_a_tutorial():
    with open(os.path.join(ROOT, "odysseus-mod.json")) as f:
        m = json.load(f)
    assert m["id"] == "tailscale" and m["provides"] == ["network.peers"]
    assert m["runtime"]["start"] == "boot" and m["permissions"] == []
    assert 1 <= len(m["tutorial"]["steps"]) <= 8


def test_unsigned_requests_are_refused(core):
    assert get(f"http://127.0.0.1:{core.mod_port}/health")[0] == 200
    assert get(f"http://127.0.0.1:{core.mod_port}/mod/cap/network.peers/peers")[0] == 401


def test_capability_actions(core):
    code, d = cap(core, "peers")
    assert code == 200 and d["ok"]
    assert {p["host"] for p in d["peers"]} >= {"home-server", "gaming-pc"}
    assert all(set(p) >= {"host", "name", "dns", "ips", "os", "online", "is_self", "shared", "age_days"}
               for p in d["peers"])
    assert cap(core, "resolve", "POST", {"host": "gaming-pc"})[1] == {"ip": "100.64.0.2"}
    assert cap(core, "ping", "POST", {"target": "100.64.0.2"})[1]["ok"] is True
    assert cap(core, "ping", "POST", {"target": "--help"})[1]["ok"] is False
    code, s = cap(core, "serve")
    assert code == 200 and any(m["funnel"] for m in s["mounts"])


def test_pages_through_the_proxy(core):
    code, body = get(f"{core.url}/mods/tailscale/")
    assert code == 200 and b"Machines" in body and b"api/peers" in body
    code, body = get(f"{core.url}/mods/tailscale/api/peers")
    assert code == 200 and json.loads(body)["ok"]
    code, body = get(f"{core.url}/mods/tailscale/cards/summary")
    assert code == 200 and b"machines online" in body


def test_tools(core):
    conn, r = core.mod_request("GET", "/mod/tools", user="odysseus-core")
    names = [t["function"]["name"] for t in json.loads(r.read())["tools"]]
    conn.close()
    assert names == ["tailnet_machines", "tailnet_ping"]
    conn, r = core.mod_request("POST", "/mod/tools/tailnet_machines", body=b"{}", user="alice",
                               headers={"Content-Type": "application/json"})
    out = json.loads(r.read())["output"]
    conn.close()
    assert "GAMING-PC" in out and "shared from another tailnet" in out
