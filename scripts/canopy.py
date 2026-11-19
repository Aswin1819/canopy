"""Tree-shaped review / approval gate.

Shows a tree (a plan, scope breakdown, architecture, research summary) as a collapsible
mind map in the browser. The reviewer rules on nodes (Keep / Cut / Change / Ask, plus an
optional note) and sends the result back to the calling agent on stdout.

Usage:
  canopy.py <tree.json | outline.md> [--gate] [--json] [--export-plan PLAN.md]
                    [--port 0] [--no-open] [--timeout-min 110] [--data-dir DIR]
                    [--heartbeat-sec 20] [--heartbeat-grace-sec 90]

Exit codes:
  0  the reviewer acted: submitted, approved, changes_requested or closed (read the status)
  2  bad input or startup failure (unreadable file, invalid tree, port in use, missing asset)
  3  timeout: nobody acted within --timeout-min (drafts kept; re-run the same command)
  4  closed_tab: the page stopped sending heartbeats (tab closed; drafts kept)

Python 3.8+, standard library only. Makes no network requests: the page, d3 and fonts are
all served from this process on 127.0.0.1.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---- The one place the tool's name lives (plugin.json / marketplace.json / SKILL.md
# ---- necessarily repeat it; README "Renaming" lists them).
TOOL_NAME = "canopy"
DISPLAY_NAME = "Canopy"
ENV_PREFIX = "CANOPY_"            # CANOPY_PORT, CANOPY_BROWSER, CANOPY_DATA_DIR
FALLBACK_DATA_DIR = Path.home() / ("." + TOOL_NAME)

VERSION = "1.3.0"
MAX_BODY = 1024 * 1024
MAX_TEXT = 20000
MAX_OPEN = 5000
ROUND_PORT_BASE, ROUND_PORT_SPAN = 7700, 300   # default port per plan file: 7700-7999, random if taken
DECISIONS = ("keep", "cut", "change", "ask")
TOKEN_HEADER = "X-Canopy-Token"

HERE = Path(__file__).resolve().parent


def _asset(name):
    for d in (HERE.parent / "assets", HERE / "assets", HERE):
        if (d / name).is_file():
            return d / name
    return HERE.parent / "assets" / name


for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def warn(msg):
    print(f"{TOOL_NAME}: warning: {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- input
FLAG_RE = re.compile(r"\[(human|done|todo)\]|\[id[:=]\s*([^\]\s]+)\s*\]", re.I)
BULLET_RE = re.compile(r"^([ \t]*)(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")


def parse_outline(text):
    """Markdown outline -> doc. `# Title` line, then bullets (- * + or 1.) indented by any
    consistent amount. `Name :: note [human] [done] [todo] [id:foo]`. If there is more than
    one top-level bullet, the title becomes a synthetic root."""
    title, subtitle, items = None, None, []
    for raw in text.splitlines():
        if not items and title is None and re.match(r"^#\s+\S", raw):
            title = raw.lstrip("#").strip()
            continue
        m = BULLET_RE.match(raw)
        if m:
            items.append((len(m.group(1).expandtabs(4)), m.group(2)))
        elif title is not None and not items and raw.strip() and not raw.lstrip().startswith("#") and subtitle is None:
            subtitle = raw.strip()
    if not items:
        raise ValueError("no '- item' lines found in outline")

    def node(txt):
        d = {"name": "", "children": []}
        for fm in FLAG_RE.finditer(txt):
            if fm.group(2):
                d["id"] = fm.group(2)
            else:
                d[{"human": "h"}.get(fm.group(1).lower(), fm.group(1).lower())] = True
        txt = FLAG_RE.sub("", txt).strip()
        # Split on " :: " only, so names like std::vector survive.
        m = re.match(r"^(.*?)\s+::(?:\s+(.*))?$", txt)
        name, note = (m.group(1), m.group(2) or "") if m else (txt, "")
        d["name"] = name.strip()
        if note.strip():
            d["note"] = note.strip()
        return d

    # Build with an indent stack; depth is relative, so 2- or 4-space indents both work.
    min_indent = min(i for i, _ in items)
    tops, stack = [], []  # stack of (indent, node)
    for indent, txt in items:
        n = node(txt)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            if indent != min_indent and tops:
                # Dedent to a level that is still deeper than the top level: attach to last top.
                tops[-1]["children"].append(n)
            else:
                tops.append(n)
        else:
            stack[-1][1]["children"].append(n)
        stack.append((indent, n))
    if len(tops) == 1:
        root = tops[0]
        doc = {"title": title or root["name"], "root": root}
    else:
        name = title or "Plan"
        doc = {"title": name, "root": {"name": name, "children": tops}}
    if subtitle:
        doc["subtitle"] = subtitle
    return doc


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return (s[:40].rstrip("-")) or "node"


def normalise(doc):
    """Validate the tree, coerce aliases, assign stable ids. Returns (doc, warnings)."""
    if not isinstance(doc, dict):
        raise ValueError("top level must be a JSON object")
    if "root" not in doc:  # bare tree
        doc = {"title": doc.get("name", "Plan"), "root": doc}
    warnings, seen_ids = [], {}

    def walk(n, where, parent_id, depth):
        if not isinstance(n, dict):
            raise ValueError(f"{where}: must be an object with a 'name'")
        name = n.get("name")
        if isinstance(name, (int, float)) and not isinstance(name, bool):
            name = str(name)
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{where}: missing 'name'")
        out = {"name": name.strip()}
        if n.get("note") is not None:
            out["note"] = str(n["note"])
        status = str(n.get("status", "")).lower()
        if n.get("h") or n.get("human") or n.get("kind") == "human":
            out["h"] = True
        if n.get("done") or status == "done":
            out["done"] = True
        if n.get("todo") or status == "todo":
            out["todo"] = True
        explicit = n.get("id")
        if explicit is not None and str(explicit).strip():
            nid = str(explicit).strip()
        else:
            nid = "root" if depth == 0 else (slug(name) if parent_id == "root" else f"{parent_id}/{slug(name)}")
        if nid in seen_ids:
            base, k = nid, 2
            while f"{base}~{k}" in seen_ids:
                k += 1
            nid = f"{base}~{k}"
            warnings.append(f"duplicate id '{base}' at {where} (also at {seen_ids[base]}); using '{nid}'"
                            + ("" if explicit else " — give same-named siblings explicit ids"))
        seen_ids[nid] = where
        out["id"] = nid
        kids = n.get("children")
        if kids is None:
            kids = []
        if not isinstance(kids, list):
            raise ValueError(f"{where}.children: must be a list")
        out["children"] = [walk(c, f"{where}.children[{i}]", nid, depth + 1) for i, c in enumerate(kids)]
        return out

    root = walk(doc["root"], "root", None, 0)
    title = str(doc.get("title") or root["name"])
    sub = doc.get("subtitle")
    out = {"title": title, "subtitle": str(sub) if sub else "", "root": root}
    # Nodes Claude removed on purpose, with the reason: {"id": "why"}; shown in the next round's removed list.
    dropped = doc.get("dropped")
    if isinstance(dropped, dict):
        out["dropped"] = {str(k)[:300]: str(v)[:MAX_TEXT] for k, v in list(dropped.items())[:500] if isinstance(v, str)}
    return out, warnings


def load(path):
    text = Path(path).read_text(encoding="utf-8-sig")  # BOM-tolerant (PowerShell writes one)
    if Path(path).suffix.lower() == ".json":
        raw = json.loads(text)
    else:
        stripped = text.lstrip()
        raw = json.loads(stripped) if stripped.startswith("{") else parse_outline(text)
    return normalise(raw)


def walk_nodes(root):
    """Preorder (tree order) iterator of (node, path_names, top_level_id)."""
    stack = [(root, [root["name"]], None)]
    while stack:
        n, path, top = stack.pop()
        yield n, path, top
        for c in reversed(n["children"]):
            stack.append((c, path + [c["name"]], top or c["id"]))


# --------------------------------------------------------------------------- output
STATUS_LABEL = {
    "approved": "APPROVED",
    "changes_requested": "CHANGES REQUESTED",
    "submitted": "SUBMITTED",
    "closed": "CLOSED (reviewer closed without sending; draft kept)",
    "closed_tab": "CLOSED_TAB (browser tab closed or lost; draft kept)",
    "timeout": "TIMEOUT (no decision in time; draft kept, re-run the same command)",
}
DEC_LABEL = {"change": "CHANGE", "cut": "CUT", "ask": "ASK", "note": "NOTE", "keep": "KEEP"}
DEC_ORDER = ("change", "cut", "ask", "note", "keep")


def build_result(doc, status, payload=None, gate=False):
    payload = payload or {}
    raw = payload.get("decisions") or {}
    if isinstance(raw, list):  # also accept [{id, decision, text}]
        raw = {str(x.get("id")): {"d": x.get("decision"), "t": x.get("text")} for x in raw if isinstance(x, dict)}
    if not isinstance(raw, dict):
        raw = {}
    decisions, stats = [], {k: 0 for k in DEC_ORDER}
    known = set()
    total = 0
    top_ids = [c["id"] for c in doc["root"]["children"]]
    send = status in ("submitted", "approved", "changes_requested")
    for n, path, _top in walk_nodes(doc["root"]):
        total += 1
        known.add(n["id"])
        if not send:
            continue
        v = raw.get(n["id"])
        if not isinstance(v, dict):
            continue
        d = str(v.get("d") or v.get("decision") or "").lower()
        t = str(v.get("t") or v.get("text") or "").strip()[:MAX_TEXT]
        if d not in DECISIONS:
            d = "note" if t else ""
        if not d:
            continue
        stats[d] += 1
        decisions.append({"id": n["id"], "path": path, "name": n["name"], "decision": d, "text": t})
    dropped = [k for k in raw if k not in known] if send else []
    general = str(payload.get("general") or "").strip()[:MAX_TEXT] if send else ""
    reviewed = len(decisions)
    # Items = nodes with no children. One is covered when it has a decision or note of its own, or when a branch
    # above it has Keep/Cut/Change/Ask (that decision applies to everything under it without its own).
    own = {d["id"] for d in decisions}
    ruled = {d["id"] for d in decisions if d["decision"] != "note"}
    items = covered = on_branches = 0
    stack = [(doc["root"], False)]
    while stack:
        n, up = stack.pop()
        if not n["children"]:
            items += 1
            covered += up or n["id"] in own
        else:
            on_branches += n["id"] in ruled
            stack.extend((c, up or n["id"] in ruled) for c in n["children"])
    return {
        "version": 1,
        "tool": TOOL_NAME,
        "status": status,
        "gate": gate,
        "title": doc["title"],
        "source": doc.get("_source", ""),
        "decisions": decisions,
        "general": general,
        "stats": dict(stats, reviewed=reviewed, nodes=total, items=items, items_covered=covered, on_branches=on_branches,
                      top_level=len(top_ids), dropped_unknown_ids=len(dropped)),
    }


def _indent(text):
    lines = text.splitlines() or [""]
    return lines[0] + "".join("\n    " + ln for ln in lines[1:])


def format_markdown(res):
    out = [f"# {DISPLAY_NAME}: {res['title']}", "", f"Status: {STATUS_LABEL.get(res['status'], res['status'])}"]
    s = res["stats"]
    if res["status"] in ("submitted", "approved", "changes_requested"):
        counts = ", ".join(f"{s[k]} {DEC_LABEL[k].lower()}" for k in DEC_ORDER if s[k])
        out.append(f"Reviewed: {s['items_covered']}/{s['items']} items with {s['reviewed']} "
                   f"decision{'' if s['reviewed'] == 1 else 's'}"
                   + (f" ({counts})" if counts else ""))
        if s.get("on_branches"):
            out.append("A decision on a branch applies to everything under it that has no decision of its own.")
        if res["status"] == "approved" and (s["change"] or s["cut"] or s["ask"]):
            out.append("Approved with notes: treat the items below as guidance, not as a request to stop.")
        out.append("")
        for k in DEC_ORDER:
            items = [d for d in res["decisions"] if d["decision"] == k]
            if not items:
                continue
            out.append(f"## {DEC_LABEL[k]} ({len(items)})")
            for d in items:
                line = f"- `{d['id']}` {' › '.join(d['path'])}"
                if d["text"]:
                    line += " — " + _indent(d["text"])
                out.append(line)
            out.append("")
        if res["general"]:
            out += ["## General", res["general"], ""]
        if not res["decisions"] and not res["general"]:
            out += ["(No decisions or notes were made.)", ""]
        if res.get("exported_plan"):
            out += [f"Plan checklist written to: {res['exported_plan']}", ""]
    return "\n".join(out).rstrip() + "\n"


def export_plan(doc, res, path):
    by_id = {d["id"]: d for d in res["decisions"]}
    lines = [f"# {doc['title']}", ""]
    if doc.get("subtitle"):
        lines += [doc["subtitle"], ""]
    lines += [f"_Reviewed with {TOOL_NAME}: {res['status']}. Cut items removed._", ""]

    def rec(n, depth):
        d = by_id.get(n["id"])
        if d and d["decision"] == "cut":
            return
        pad = "  " * depth
        box = "[x]" if n.get("done") else "[ ]"
        tail = f" — {n['note']}" if n.get("note") else ""
        human = " (human step)" if n.get("h") else ""
        lines.append(f"{pad}- {box} {n['name']}{human}{tail}")
        if d and d["text"] and d["decision"] in ("change", "ask", "note", "keep"):
            lines.append(f"{pad}  > {DEC_LABEL[d['decision']].title()}: {' '.join(d['text'].split())}")
        for c in n["children"]:
            rec(c, depth + 1)

    rec(doc["root"], 0)
    if res.get("general"):
        lines += ["", "## General notes", res["general"]]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- drafts
def data_dir(arg):
    for cand in (arg, os.environ.get(ENV_PREFIX + "DATA_DIR"), os.environ.get("CLAUDE_PLUGIN_DATA")):
        if cand and "${" not in cand and cand.strip():
            return Path(cand.strip())
    return FALLBACK_DATA_DIR


def draft_path(ddir, source, title):
    h = hashlib.sha256((str(Path(source).resolve()) + "\n" + title).encode("utf-8")).hexdigest()[:20]
    return Path(ddir) / "drafts" / f"{h}.json"


def round_path(ddir, source):
    """Per plan file (not per title, which may change between rounds): the port and token it is served on."""
    h = hashlib.sha256(str(Path(source).resolve()).encode("utf-8")).hexdigest()[:20]
    return Path(ddir) / "rounds" / f"{h}.json", h


def snapshot(doc):
    """What a round looked like: {id: [name, note, parent id]} for every node."""
    out = {}

    def rec(n, parent):
        out[n["id"]] = [n["name"], n.get("note", ""), parent]
        for c in n["children"]:
            rec(c, n["id"])
    rec(doc["root"], None)
    return out


def round_diff(doc, last):
    """Compare this round's tree with the last sent round of the same plan file, matching nodes by id.
    Returns None for a first round, else:
      n        round number
      new      ids not in the last round
      changed  {id: {name, note}}: old text of nodes whose name or note changed (their decision needs a recheck)
      moved    {id: old parent id}: same node under a different parent
      removed  [{id, name, said, reason}]: gone this round; reason from the tree's "dropped" map
      said     {id: {d, t}}: last round's decisions for nodes still here
      carried  {id: {d, t, from}}: decisions that apply again without a new look: the node's own when its text is
               unchanged (wherever it moved), else a removed branch's Keep/Cut/Change/Ask passed down to its old
               descendants that are still here, unchanged, and had no decision of their own"""
    if not isinstance(last, dict) or not isinstance(last.get("nodes"), dict):
        return None
    before, now = last["nodes"], snapshot(doc)
    text = lambda v: [v[0], v[1]] if isinstance(v, list) and len(v) >= 2 else None
    said = {k: v for k, v in (last.get("decisions") or {}).items() if isinstance(v, dict)}
    changed, moved, carried = {}, {}, {}
    for i, v in now.items():
        old = before.get(i)
        if old is None:
            continue
        if text(old) != text(v):
            changed[i] = {"name": text(old)[0] if text(old) else "", "note": text(old)[1] if text(old) else ""}
        elif i in said:
            carried[i] = dict(said[i], **{"from": i})
        if isinstance(old, list) and len(old) >= 3 and old[2] != v[2] and i != doc["root"]["id"]:
            moved[i] = old[2]
    kids = {}
    for i, v in before.items():
        if isinstance(v, list) and len(v) >= 3 and v[2] is not None:
            kids.setdefault(v[2], []).append(i)
    removed = [i for i in before if i not in now]
    for r in removed:  # a removed branch's decision reaches its old descendants, nearest decision first
        sv = said.get(r)
        if not sv or str(sv.get("d") or "") not in DECISIONS:
            continue
        stack = list(kids.get(r, []))
        while stack:
            c = stack.pop()
            if c in said:          # a decision of its own (kept or rechecked) wins, and covers its own subtree
                continue
            if c in now and c not in changed and c not in carried:
                carried[c] = {"d": sv["d"], "t": "", "from": r}
            stack.extend(kids.get(c, []))
    reasons = doc.get("dropped") or {}
    return {
        "n": int(last.get("n") or 1) + 1,
        "new": [i for i in now if i not in before and i != doc["root"]["id"]],
        "changed": changed,
        "moved": moved,
        "removed": [{"id": i, "name": text(before[i])[0] if text(before[i]) else str(i), "said": said.get(i),
                     "reason": reasons.get(i, "")} for i in removed][:500],
        "said": {i: v for i, v in said.items() if i in now},
        "carried": carried,
    }


def read_draft(p):
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def write_draft(p, d):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


# --------------------------------------------------------------------------- server
def gate_missing(doc, payload):
    """Top-level branch ids without a decision: a branch counts once it, or something in it, has Keep / Cut /
    Change / Ask (a note alone does not, and opening it does not). A decision on the root covers every branch."""
    dec = payload.get("decisions") or {}
    rv = dec.get(doc["root"]["id"]) if isinstance(dec, dict) else None
    if isinstance(rv, dict) and str(rv.get("d") or "").lower() in DECISIONS:
        return []
    decided_tops = set()
    for n, _p, top in walk_nodes(doc["root"]):
        v = dec.get(n["id"]) if isinstance(dec, dict) else None
        if top and isinstance(v, dict) and str(v.get("d") or "").lower() in DECISIONS:
            decided_tops.add(top)
    return [c["id"] for c in doc["root"]["children"] if c["id"] not in decided_tops]


class Session:
    def __init__(self, doc, source, args):
        self.doc, self.source, self.args = doc, source, args
        self.ddir = data_dir(args.data_dir)
        self.draft_file = draft_path(self.ddir, source, doc["title"])
        # Same plan file, same address: every review round reuses the token (and, in main, the port), so a tab
        # left open on the last round can find the next one.
        self.round_file, rh = round_path(self.ddir, source)
        prev = read_draft(self.round_file) or {}
        tok = prev.get("token")
        self.token = tok if isinstance(tok, str) and re.fullmatch(r"[A-Za-z0-9_-]{24,64}", tok) else secrets.token_urlsafe(24)
        p = prev.get("port")
        self.port_hint = p if isinstance(p, int) and 1024 <= p <= 65535 else ROUND_PORT_BASE + int(rh, 16) % ROUND_PORT_SPAN
        self.round_prev = prev
        self.diff = round_diff(doc, prev.get("last"))
        self.inst = secrets.token_hex(6)   # this process: a finished tab tells the next round by a different one
        self.rev = hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
        self.done = threading.Event()
        self.status, self.payload = None, None
        self.last_hb = None
        self.lock = threading.Lock()
        self.port = None
        tpl = _asset("template.html").read_text(encoding="utf-8")
        d3 = _asset("d3.v7.min.js").read_text(encoding="utf-8")
        if "</script" in d3.lower():
            raise RuntimeError("d3 bundle contains </script")
        self.template, self.d3 = tpl, d3

    def page(self):
        nonce = secrets.token_urlsafe(16)
        draft = read_draft(self.draft_file)
        cfg = {"token": self.token, "gate": bool(self.args.gate), "hb": int(self.args.heartbeat_sec * 1000),
               "draft": draft, "draftKey": self.draft_file.stem, "tool": TOOL_NAME, "display": DISPLAY_NAME,
               "header": TOKEN_HEADER, "version": VERSION, "rev": self.rev, "inst": self.inst,
               "round": self.diff}
        doc = {k: v for k, v in self.doc.items() if not k.startswith("_")}

        def island(o):
            return (json.dumps(o, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
                    .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))

        html = self.template.replace("__NONCE__", nonce)
        html = html.replace("/*__D3__*/", self.d3)
        html = html.replace("/*__CONFIG__*/null", island(cfg)).replace("/*__DATA__*/null", island(doc))
        csp = (f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
               "connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        return html, csp

    def finish(self, status, payload=None):
        with self.lock:
            if self.done.is_set():
                return False
            self.status, self.payload = status, payload
            self.done.set()
            return True


def make_handler(sess):
    class H(BaseHTTPRequestHandler):
        server_version = TOOL_NAME
        sys_version = ""

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json", extra=None):
            b = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)

        def _err(self, code, msg, **more):
            self._send(code, json.dumps(dict(error=msg, **more)))

        def _host_ok(self):
            host = (self.headers.get("Host") or "").lower()
            return host in (f"127.0.0.1:{sess.port}", f"localhost:{sess.port}")

        def do_GET(self):
            if not self._host_ok():
                return self._err(403, "bad host")
            p = self.path.split("?", 1)[0]
            if p in (f"/s/{sess.token}/", f"/s/{sess.token}"):
                html, csp = sess.page()
                return self._send(200, html, "text/html", {"Content-Security-Policy": csp,
                                                           "X-Frame-Options": "DENY"})
            if p == f"/s/{sess.token}/round":
                # A finished tab polls this to find the next round of the same plan; it does not count as a heartbeat.
                return self._send(200, json.dumps({"rev": sess.rev, "inst": sess.inst}))
            return self._err(404, "not found")

        def do_POST(self):
            # S1: Host, Origin, token, content type and size all checked before reading.
            if not self._host_ok():
                return self._err(403, "bad host")
            origin = self.headers.get("Origin")
            if origin is not None and origin.lower() not in (f"http://127.0.0.1:{sess.port}",
                                                             f"http://localhost:{sess.port}"):
                return self._err(403, "bad origin")
            tok = self.headers.get(TOKEN_HEADER) or ""
            if not hmac.compare_digest(tok.encode(), sess.token.encode()):
                return self._err(403, "bad token")
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return self._err(415, "application/json only")
            try:
                n = int(self.headers.get("Content-Length") or "-1")
            except ValueError:
                n = -1
            if n < 0:
                return self._err(411, "content-length required")
            if n > MAX_BODY:
                # Drain a bounded amount so the client sees the 413 instead of a reset.
                left = min(n, 4 * MAX_BODY)
                while left > 0:
                    chunk = self.rfile.read(min(65536, left))
                    if not chunk:
                        break
                    left -= len(chunk)
                self.close_connection = True
                return self._err(413, "body too large")
            try:
                payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                if not isinstance(payload, dict):
                    raise ValueError
            except Exception:
                return self._err(400, "bad json")

            path = self.path.split("?", 1)[0]
            if path == "/api/heartbeat":
                sess.last_hb = time.monotonic()
                return self._send(200, json.dumps({"ok": True, "rev": sess.rev}))
            if path == "/api/draft":
                sess.last_hb = time.monotonic()
                try:
                    ids = lambda v: [i for i in v if isinstance(i, str)][:MAX_OPEN] if isinstance(v, list) else []
                    cur, ts = payload.get("cur"), payload.get("ts")
                    write_draft(sess.draft_file, {"v": 1, "decisions": payload.get("decisions") or {},
                                                  "general": str(payload.get("general") or "")[:MAX_TEXT],
                                                  "seen": ids(payload.get("seen")), "open": ids(payload.get("open")),
                                                  "cur": cur[:500] if isinstance(cur, str) else None,
                                                  "ts": ts if isinstance(ts, (int, float)) else 0,
                                                  "saved": time.time()})
                except Exception as e:
                    return self._err(500, f"could not save draft: {e}")
                return self._send(200, '{"ok":true}')
            if path == "/api/close":
                if not sess.finish("closed"):
                    return self._err(409, "this review has already finished", status=sess.status)
                return self._send(200, '{"ok":true}')
            if path == "/api/submit":
                action = payload.get("action") or "submit"
                allowed = ("approve", "request_changes") if sess.args.gate else ("submit",)
                if action not in allowed:
                    return self._err(400, f"action must be one of {list(allowed)}")
                if action == "approve":
                    missing = gate_missing(sess.doc, payload)
                    if missing:
                        return self._err(409, "review every top-level branch first", missing=missing)
                status = {"approve": "approved", "request_changes": "changes_requested"}.get(action, "submitted")
                if not sess.finish(status, payload):
                    return self._err(409, "this review has already finished", status=sess.status)
                return self._send(200, '{"ok":true}')
            return self._err(404, "not found")

    return H


def open_browser(url):
    if os.environ.get(ENV_PREFIX + "BROWSER", "").lower() in ("none", "0", "false"):
        return False
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    if sys.platform.startswith("linux"):
        try:
            if "microsoft" in Path("/proc/version").read_text().lower():
                subprocess.Popen(["cmd.exe", "/c", "start", "", url], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return True
        except Exception:
            pass
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return False
    try:
        return webbrowser.open(url)
    except Exception:
        return False


EXIT = {"submitted": 0, "approved": 0, "changes_requested": 0, "closed": 0, "timeout": 3, "closed_tab": 4}


def main(argv=None):
    ap = argparse.ArgumentParser(prog=TOOL_NAME, description=DISPLAY_NAME + ": tree-shaped review gate")
    ap.add_argument("source", help="tree .json or Markdown outline .md")
    ap.add_argument("--gate", action="store_true", help="show Approve / Request changes")
    ap.add_argument("--json", action="store_true", help="print one JSON object instead of Markdown")
    ap.add_argument("--export-plan", metavar="PLAN.md", help="on approve/submit, write the tree as a checklist minus Cut items")
    ap.add_argument("--port", type=int, default=int(os.environ.get(ENV_PREFIX + "PORT") or 0))
    ap.add_argument("--no-open", action="store_true", help="don't open a browser (also CANOPY_BROWSER=none)")
    ap.add_argument("--timeout-min", type=float, default=110.0)
    ap.add_argument("--data-dir", default=None, help="drafts root (default ${CLAUDE_PLUGIN_DATA}, else ~/.%s)" % TOOL_NAME)
    ap.add_argument("--heartbeat-sec", type=float, default=float(os.environ.get(ENV_PREFIX + "HEARTBEAT_SEC") or 20))
    ap.add_argument("--heartbeat-grace-sec", type=float, default=float(os.environ.get(ENV_PREFIX + "HEARTBEAT_GRACE_SEC") or 90))
    ap.add_argument("--version", action="version", version=f"{TOOL_NAME} {VERSION}")
    a = ap.parse_args(argv)

    try:
        doc, warnings = load(a.source)
        doc["_source"] = str(Path(a.source).resolve())
    except Exception as e:
        print(f"{TOOL_NAME}: cannot read {a.source}: {e}", file=sys.stderr)
        return 2
    for w in warnings:
        warn(w)
    try:
        sess = Session(doc, a.source, a)
        srv = None
        if not a.port:  # this plan's usual port first, so the URL stays the same between rounds
            try:
                srv = ThreadingHTTPServer(("127.0.0.1", sess.port_hint), make_handler(sess))
            except OSError:
                srv = None
        if srv is None:
            srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(sess))
    except OSError as e:
        print(f"{TOOL_NAME}: cannot start server on 127.0.0.1:{a.port}: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"{TOOL_NAME}: startup failed: {e}", file=sys.stderr)
        return 2
    srv.daemon_threads = True
    sess.port = srv.server_address[1]
    try:
        write_draft(sess.round_file, dict(sess.round_prev, token=sess.token, port=sess.port, source=str(Path(a.source).resolve())))
    except OSError as e:
        warn(f"could not remember this plan's address: {e}")
    url = f"http://127.0.0.1:{sess.port}/s/{sess.token}/"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"{DISPLAY_NAME} ready: {url}", file=sys.stderr, flush=True)
    print(f"{TOOL_NAME}: drafts at {sess.draft_file}", file=sys.stderr, flush=True)
    if not a.no_open:
        open_browser(url)

    deadline = time.monotonic() + a.timeout_min * 60
    last_tick = time.monotonic()
    while not sess.done.wait(0.2):
        now = time.monotonic()
        if now - last_tick > max(5.0, a.heartbeat_grace_sec / 2):
            # The process itself was suspended (laptop sleep): don't blame the tab.
            if sess.last_hb is not None:
                sess.last_hb = now
        last_tick = now
        if sess.last_hb is not None and now - sess.last_hb > a.heartbeat_grace_sec:
            sess.finish("closed_tab")
        elif now > deadline:
            sess.finish("timeout")
    time.sleep(0.2)  # let the HTTP response flush
    srv.shutdown()

    res = build_result(doc, sess.status, sess.payload, gate=a.gate)
    if sess.status in ("submitted", "approved", "changes_requested"):
        # Remember this round, so the next one can show what changed and what was said about it.
        try:
            raw = (sess.payload or {}).get("decisions") or {}
            said = {k: {"d": str(v.get("d") or ""), "t": str(v.get("t") or "")[:MAX_TEXT]}
                    for k, v in raw.items() if isinstance(v, dict) and (v.get("d") or str(v.get("t") or "").strip())} if isinstance(raw, dict) else {}
            rp = read_draft(sess.round_file) or {}
            rp["last"] = {"n": (sess.diff or {}).get("n", 1), "status": sess.status, "nodes": snapshot(doc), "decisions": said}
            write_draft(sess.round_file, rp)
        except Exception as e:
            warn(f"could not remember this round: {e}")
        try:
            sess.draft_file.unlink()
        except OSError:
            pass
        if a.export_plan and sess.status in ("submitted", "approved"):
            try:
                export_plan(doc, res, a.export_plan)
                res["exported_plan"] = str(Path(a.export_plan).resolve())
            except Exception as e:
                warn(f"could not write plan checklist: {e}")
    if a.json:
        sys.stdout.write(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
    else:
        sys.stdout.write(format_markdown(res))
    sys.stdout.flush()
    return EXIT[sess.status]


if __name__ == "__main__":
    sys.exit(main())
