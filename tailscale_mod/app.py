"""Tailscale for Odysseus: the machines on your tailnet.

Odysseus calls this add-on for the `network.peers` capability (its Settings >
Devices machines, model discovery on your other machines, host names DNS does
not know, Ping). It also has a Machines tab, a Home card and two read-only
agent tools.

Everything is read only: it runs `tailscale status`, `tailscale ping` and
`tailscale serve status`, and never changes the tailnet, Serve or Funnel.

Run it without Odysseus:   python -m odysseus_mod.devcore
"""
from __future__ import annotations

import html as _html

from odysseus_mod import ModApp, html

from tailscale_mod import tailnet

app = ModApp(mod_id="tailscale")
CAP = "/mod/cap/network.peers"


def _peers_payload(refresh: bool = False):
    ps = tailnet.peers(refresh=refresh)
    return {"ok": bool(ps), "peers": ps, "error": "" if ps else (tailnet.last_error() or "No machines found.")}


# ── The capability Odysseus calls ────────────────────────────────────────

@app.get(CAP + "/peers")
def cap_peers(req):
    return _peers_payload(req.query.get("refresh") == "1")


@app.get(CAP + "/resolve")
def cap_resolve_get(req):
    return {"ip": tailnet.resolve(req.query.get("host", ""))}


@app.post(CAP + "/resolve")
def cap_resolve(req):
    body = req.json() if isinstance(req.json(), dict) else {}
    return {"ip": tailnet.resolve(str(body.get("host") or ""))}


@app.post(CAP + "/ping")
def cap_ping(req):
    body = req.json() if isinstance(req.json(), dict) else {}
    return tailnet.ping(str(body.get("target") or ""))


@app.get(CAP + "/serve")
def cap_serve(req):
    return tailnet.serve_status()


# ── The Machines tab ─────────────────────────────────────────────────────

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Machines</title>
<style>
body{font:14px system-ui,sans-serif;margin:0;padding:18px 20px;background:#111;color:#ddd}
h1{font-size:17px;margin:0 0 4px}h2{font-size:14px;margin:22px 0 8px;color:#bbb}
.dim{color:#888;font-size:13px}table{border-collapse:collapse;width:100%;margin-top:10px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #262626;font-size:13px;vertical-align:top}
th{color:#888;font-weight:500}button{font:inherit;font-size:12px;padding:3px 10px;border-radius:6px;
border:1px solid #444;background:#1d1d1d;color:#eee;cursor:pointer}button:hover{border-color:#666}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:#555}
.on{background:#3fb950}.chip{font-size:11px;border:1px solid #3a3a3a;border-radius:9px;padding:0 6px;margin-left:6px;color:#aaa}
.err{color:#f0883e}code{font-size:12px;color:#bbb}
</style></head><body>
<h1>Machines</h1>
<div class="dim">Your tailnet, as this server's Tailscale sees it. Read only: nothing here changes Tailscale.
<button id="refresh" style="margin-left:8px">Refresh</button></div>
<div id="msg" class="err" style="margin-top:8px"></div>
<table><thead><tr><th>Machine</th><th>OS</th><th>Address</th><th>Last seen</th><th></th></tr></thead>
<tbody id="rows"><tr><td colspan="5" class="dim">Loading...</td></tr></tbody></table>
<h2>Tailscale Serve and Funnel</h2>
<div class="dim">What this server publishes. Funnel means reachable from the internet.</div>
<table><thead><tr><th>Address</th><th>Goes to</th><th></th></tr></thead><tbody id="serve"></tbody></table>
<script>
// Relative URLs only: the page is served under /mods/tailscale/~token/ by the core.
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function ago(p) {
  if (p.is_self) return 'this server';
  if (p.online) return 'online now';
  if (p.age_days == null) return 'never';
  const d = p.age_days;
  return d < 1 ? Math.round(d * 24) + ' h ago' : Math.round(d) + ' days ago';
}
async function load(refresh) {
  const r = await fetch('api/peers' + (refresh ? '?refresh=1' : ''));
  const d = await r.json();
  document.getElementById('msg').textContent = d.ok ? '' : (d.error || 'No machines found.');
  const rows = (d.peers || []).sort((a, b) => (b.is_self - a.is_self) || (a.shared - b.shared) || (b.online - a.online) || a.name.localeCompare(b.name));
  document.getElementById('rows').innerHTML = rows.map((p) => `<tr>
    <td><span class="dot ${p.online ? 'on' : ''}"></span><strong>${esc(p.name)}</strong>${p.is_self ? '<span class="chip">this server</span>' : ''}${p.shared ? '<span class="chip">shared with you</span>' : ''}<div class="dim">${esc(p.dns)}</div></td>
    <td>${esc(p.os || '?')}</td><td><code>${esc((p.ips || []).join(', '))}</code></td><td>${esc(ago(p))}</td>
    <td>${p.is_self ? '' : `<button data-ping="${esc((p.ips || [])[0] || p.host)}">Ping</button> <span class="dim" data-out></span>`}</td></tr>`).join('')
    || '<tr><td colspan="5" class="dim">No machines.</td></tr>';
  const s = await (await fetch('api/serve')).json();
  document.getElementById('serve').innerHTML = (s.mounts || []).map((m) => `<tr><td><code>${esc(m.url)}</code></td>
    <td><code>${esc(m.target)}</code></td><td>${m.funnel ? '<span class="chip">Funnel: public</span>' : '<span class="chip">tailnet only</span>'}</td></tr>`).join('')
    || `<tr><td colspan="3" class="dim">${esc(s.ok ? 'Nothing is served.' : s.error)}</td></tr>`;
}
document.getElementById('refresh').onclick = () => load(true);
document.getElementById('rows').addEventListener('click', async (ev) => {
  const b = ev.target.closest('[data-ping]');
  if (!b) return;
  const out = b.parentNode.querySelector('[data-out]');
  out.textContent = 'pinging...';
  const r = await (await fetch('api/ping', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                            body: JSON.stringify({target: b.dataset.ping})})).json();
  out.textContent = r.ok ? 'answers' : 'no answer';
  out.title = r.detail || '';
});
load(false);
</script></body></html>"""


@app.get("/")
def home(req):
    return html(PAGE)


@app.get("/api/peers")
def api_peers(req):
    return _peers_payload(req.query.get("refresh") == "1")


@app.get("/api/serve")
def api_serve(req):
    return tailnet.serve_status()


@app.post("/api/ping")
def api_ping(req):
    body = req.json() if isinstance(req.json(), dict) else {}
    return tailnet.ping(str(body.get("target") or ""))


@app.get("/cards/summary")
def card(req):
    ps = [p for p in tailnet.peers() if not p["shared"]]
    on = sum(1 for p in ps if p["online"])
    body = (f"<b style='font-size:20px'>{on}</b> of {len(ps)} machines online" if ps
            else f"<span style='color:#f0883e'>{_html.escape(tailnet.last_error() or 'No machines found.')}</span>")
    return html("<!doctype html><meta charset=utf-8><body style='font:13px system-ui;color:#ddd;margin:10px'>"
                + body + "</body>")


# ── Agent tools (read only) ──────────────────────────────────────────────

@app.tool("tailnet_machines", "The machines on the user's tailnet: name, OS, address, online or when last seen.",
          keywords=["tailscale", "tailnet", "machines online", "which machines"], read_only=True)
def tool_machines(req, args):
    ps = tailnet.peers(refresh=True)
    if not ps:
        return {"output": tailnet.last_error() or "No machines found on the tailnet."}
    lines = []
    for p in ps:
        state = "this server" if p["is_self"] else ("online" if p["online"] else "offline")
        lines.append(f"- {p['name']} ({p['os'] or '?'}, {', '.join(p['ips'][:1])}): {state}"
                     + (" [shared from another tailnet]" if p["shared"] else ""))
    return {"output": "\n".join(lines), "data": {"peers": ps}}


@app.tool("tailnet_ping", "Check whether one machine on the tailnet answers (tailscale ping).",
          {"machine": {"type": "string", "description": "Machine name or tailnet address"}}, ["machine"],
          keywords=["tailscale", "tailnet", "ping"], read_only=True)
def tool_ping(req, args):
    target = str(args.get("machine") or "")
    p = tailnet.find(tailnet.peers(), target)
    r = tailnet.ping((p["ips"] or [p["host"]])[0] if p else target)
    return {"output": f"{target} {'answers' if r['ok'] else 'does not answer'}: {r['detail']}", "data": r}


def main():
    app.run()
