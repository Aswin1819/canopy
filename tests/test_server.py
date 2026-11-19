"""Tests for scripts/canopy.py (stdlib unittest). Run: python -m unittest discover -s tests -v"""
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "canopy.py"
sys.path.insert(0, str(ROOT / "scripts"))
import canopy as mr  # noqa: E402

TREE = {"title": "Test plan", "root": {"name": "Plan", "children": [
    {"name": "Backend", "id": "be", "children": [{"name": "API", "note": "REST"}, {"name": "DB"}]},
    {"name": "Frontend", "children": [{"name": "Button"}]},
    {"name": "Docs"}]}}


class Server:
    """Runs the real script in a subprocess and talks HTTP to it."""

    def __init__(self, tmp, *flags, tree=TREE, name="plan.json"):
        self.src = Path(tmp) / name
        if isinstance(tree, str):
            self.src.write_text(tree, encoding="utf-8")
        else:
            self.src.write_text(json.dumps(tree), encoding="utf-8")
        self.data = Path(tmp) / "data"
        env = dict(os.environ, CANOPY_BROWSER="none", PYTHONIOENCODING="utf-8")
        self.p = subprocess.Popen([sys.executable, str(SCRIPT), str(self.src), "--no-open", "--data-dir", str(self.data), *flags],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.stderr = []
        while True:
            line = self.p.stderr.readline().decode("utf-8")
            if not line:
                raise RuntimeError("server died: " + "".join(self.stderr) + self.p.stdout.read().decode())
            self.stderr.append(line)
            m = re.search(r"http://127\.0\.0\.1:(\d+)/s/([^/]+)/", line)
            if m:
                self.port, self.token = int(m.group(1)), m.group(2)
                break

    def req(self, method, path, body=None, headers=None, host=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        if data is not None:
            h.setdefault("Content-Type", "application/json")
        h.update(headers or {})
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        out = (r.status, r.read().decode("utf-8"), dict(r.getheaders()))
        c.close()
        return out

    def post(self, path, body, **kw):
        hd = {"X-Canopy-Token": self.token, "Origin": f"http://127.0.0.1:{self.port}"}
        hd.update(kw.pop("headers", {}))
        return self.req("POST", path, body, headers=hd, **kw)

    def finish(self, timeout=15):
        out, err = self.p.communicate(timeout=timeout)
        return self.p.returncode, out.decode("utf-8").replace(chr(13) + chr(10), chr(10)), "".join(self.stderr) + err.decode("utf-8")

    def kill(self):
        if self.p.poll() is None:
            self.p.kill()
            self.p.communicate()


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.tmpd = tempfile.TemporaryDirectory()
        self.tmp = self.tmpd.name
        self.servers = []

    def tearDown(self):
        for s in self.servers:
            s.kill()
        self.tmpd.cleanup()

    def start(self, *flags, **kw):
        s = Server(self.tmp, *flags, **kw)
        self.servers.append(s)
        return s


class TestSecurity(ServerCase):
    def test_csrf_rejected(self):
        s = self.start()
        url = "/api/submit"
        body = {"decisions": {"root": {"d": "change", "t": "rm -rf ~"}}}
        # no token
        st, _, _ = s.req("POST", url, body, headers={"Origin": f"http://127.0.0.1:{s.port}"})
        self.assertEqual(st, 403)
        # wrong token
        st, _, _ = s.req("POST", url, body, headers={"X-Canopy-Token": "nope"})
        self.assertEqual(st, 403)
        # valid token but foreign Origin
        st, _, _ = s.post(url, body, headers={"Origin": "https://evil.example"})
        self.assertEqual(st, 403)
        # DNS-rebinding style Host
        st, _, _ = s.post(url, body, host="evil.example")
        self.assertEqual(st, 403)
        st, _, _ = s.req("GET", f"/s/{s.token}/", host="evil.example")
        self.assertEqual(st, 403)
        # text/plain "simple request" (no preflight) is refused even with the token
        st, _, _ = s.post(url, None, raw=json.dumps(body).encode(), headers={"Content-Type": "text/plain"})
        self.assertEqual(st, 415)
        # body cap
        st, _, _ = s.post("/api/draft", None, raw=b"{" + b" " * (mr.MAX_BODY + 10) + b"}")
        self.assertEqual(st, 413)
        # still running: none of those ended the session
        self.assertIsNone(s.p.poll())
        st, _, _ = s.post("/api/close", {})
        self.assertEqual(st, 200)
        code, out, _ = s.finish()
        self.assertEqual(code, 0)
        self.assertIn("CLOSED", out)
        self.assertNotIn("rm -rf", out)

    def test_page_served_only_at_token_path_with_csp_and_escaping(self):
        evil = {"title": "T</script><script>alert(1)</script>", "root": {"name": "<img src=x onerror=alert(1)>", "children": []}}
        s = self.start(tree=evil)
        st, _, _ = s.req("GET", "/")
        self.assertEqual(st, 404)
        st, html, hd = s.req("GET", f"/s/{s.token}/")
        self.assertEqual(st, 200)
        self.assertIn("default-src 'none'", hd.get("Content-Security-Policy", ""))
        self.assertIn(s.token, html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("</script><script>alert", html)
        self.assertNotIn("cdnjs", html.split("/*__D3__*/")[0] if "/*__D3__*/" in html else "")
        self.assertNotIn("fonts.googleapis", html)
        self.assertIn("d3js.org v7.8.5", html)  # bundled, not fetched
        s.post("/api/close", {})
        s.finish()


class TestFlows(ServerCase):
    def test_submit_markdown(self):
        s = self.start()
        dec = {"be/api": {"d": "change", "t": "Use GraphQL\n## Forged heading"}, "be/db": {"d": "cut", "t": ""},
               "docs": {"d": "", "t": "just a note"}, "ghost": {"d": "keep", "t": ""}}
        st, _, _ = s.post("/api/submit", {"action": "submit", "decisions": dec, "general": "Looks fine"})
        self.assertEqual(st, 200)
        code, out, _ = s.finish()
        self.assertEqual(code, 0)
        self.assertIn("Status: SUBMITTED", out)
        self.assertIn("## CHANGE (1)", out)
        self.assertIn("- `be/api` Plan › Backend › API — Use GraphQL", out)
        self.assertIn("\n    ## Forged heading", out)  # indented, can't forge a section
        self.assertNotIn("\n## Forged", out)
        self.assertIn("## CUT (1)", out)
        self.assertIn("## NOTE (1)", out)
        self.assertIn("## General\nLooks fine", out)
        self.assertNotIn("ghost", out)

    def test_submit_json(self):
        s = self.start("--json")
        dec = {"be/api": {"d": "ask", "t": "Why REST?"}, "frontend/button": {"d": "keep", "t": ""}}
        s.post("/api/submit", {"action": "submit", "decisions": dec, "general": ""})
        code, out, _ = s.finish()
        self.assertEqual(code, 0)
        res = json.loads(out)
        self.assertEqual(res["status"], "submitted")
        self.assertEqual(res["decisions"], [
            {"id": "be/api", "path": ["Plan", "Backend", "API"], "name": "API", "decision": "ask", "text": "Why REST?"},
            {"id": "frontend/button", "path": ["Plan", "Frontend", "Button"], "name": "Button", "decision": "keep", "text": ""}])
        self.assertEqual(res["stats"]["ask"], 1)
        self.assertEqual(res["stats"]["nodes"], 7)
        self.assertIn("general", res)

    def test_gate_approve_flow(self):
        plan = Path(self.tmp) / "PLAN.md"
        s = self.start("--gate", "--json", "--export-plan", str(plan))
        # submit is not a gate action
        st, _, _ = s.post("/api/submit", {"action": "submit"})
        self.assertEqual(st, 400)
        # approve before every top-level branch was looked at -> 409 naming the missing ones
        st, body, _ = s.post("/api/submit", {"action": "approve", "seen": ["be"], "decisions": {}})
        self.assertEqual(st, 409)
        self.assertEqual(sorted(json.loads(body)["missing"]), ["docs", "frontend"])
        # a decision inside a branch counts as looking at it
        dec = {"be/db": {"d": "cut", "t": "not needed"}, "frontend/button": {"d": "change", "t": "blue"}}
        st, _, _ = s.post("/api/submit", {"action": "approve", "seen": ["docs"], "decisions": dec, "general": "go"})
        self.assertEqual(st, 200)
        code, out, _ = s.finish()
        self.assertEqual(code, 0)
        res = json.loads(out)
        self.assertEqual(res["status"], "approved")
        self.assertTrue(res["gate"])
        text = plan.read_text(encoding="utf-8")
        self.assertIn("- [ ] Plan", text)
        self.assertIn("  - [ ] Backend", text)
        self.assertNotIn("DB", text)                  # cut removed
        self.assertIn("> Change: blue", text)
        self.assertEqual(res["exported_plan"], str(plan.resolve()))

    def test_gate_request_changes(self):
        s = self.start("--gate")
        s.post("/api/submit", {"action": "request_changes", "decisions": {"docs": {"d": "change", "t": "add FAQ"}}})
        code, out, _ = s.finish()
        self.assertEqual(code, 0)
        self.assertIn("Status: CHANGES REQUESTED", out)
        self.assertIn("`docs`", out)

    def test_gate_root_decision_covers_all_and_second_finish_is_409(self):
        s = self.start("--gate", "--json")
        st, _, _ = s.post("/api/submit", {"action": "approve", "decisions": {"root": {"d": "keep", "t": ""}}})
        self.assertEqual(st, 200)
        st, body, _ = s.post("/api/submit", {"action": "request_changes", "decisions": {}})
        self.assertEqual(st, 409)
        self.assertEqual(json.loads(body)["status"], "approved")
        code, out, _ = s.finish()
        self.assertEqual(json.loads(out)["status"], "approved")

    def test_same_plan_same_address_between_rounds(self):
        s1 = self.start("--json")
        st, body, _ = s1.req("GET", f"/s/{s1.token}/round")
        self.assertEqual(st, 200)
        rev1 = json.loads(body)["rev"]
        st, body, _ = s1.post("/api/heartbeat", {})
        self.assertEqual(json.loads(body)["rev"], rev1)
        s1.post("/api/submit", {"action": "submit", "decisions": {}})
        s1.finish()
        # Round 2 of the same file (revised): same port and token, new revision.
        tree2 = json.loads(json.dumps(TREE))
        tree2["root"]["children"].append({"name": "Rollout"})
        s2 = self.start("--json", tree=tree2)
        self.assertEqual((s2.port, s2.token), (s1.port, s1.token))
        st, body, _ = s2.req("GET", f"/s/{s2.token}/round")
        self.assertNotEqual(json.loads(body)["rev"], rev1)
        self.assertEqual(s2.req("GET", "/s/wrong-token/round")[0], 404)

    def test_round_diff_between_rounds(self):
        s1 = self.start("--json")
        s1.post("/api/submit", {"action": "submit", "decisions": {"be/api": {"d": "change", "t": "GraphQL"},
                                                                   "docs": {"d": "cut", "t": ""}}})
        s1.finish()
        tree2 = json.loads(json.dumps(TREE))
        tree2["root"]["children"][0]["children"][0]["note"] = "GraphQL"   # be/api changed
        tree2["root"]["children"].pop()                                    # docs removed
        tree2["root"]["children"].append({"name": "Rollout"})              # new
        doc2, _ = mr.normalise(json.loads(json.dumps(tree2)))
        last = json.loads((Path(self.tmp) / "data" / "rounds").glob("*.json").__next__().read_text(encoding="utf-8"))["last"]
        d = mr.round_diff(doc2, last)
        self.assertEqual(d["n"], 2)
        self.assertEqual(d["changed"], {"be/api": {"name": "API", "note": "REST"}})
        self.assertEqual(d["new"], ["rollout"])
        self.assertEqual([r["id"] for r in d["removed"]], ["docs"])
        self.assertEqual(d["removed"][0]["said"]["d"], "cut")
        self.assertEqual(d["said"]["be/api"], {"d": "change", "t": "GraphQL"})
        self.assertIsNone(mr.round_diff(doc2, None))
        s2 = self.start("--json", tree=tree2)
        st, html, _ = s2.req("GET", f"/s/{s2.token}/")
        self.assertEqual(st, 200)
        self.assertIn('"changed"', html)
        self.assertIn('"rollout"', html)

    def test_close_keeps_draft(self):
        s = self.start("--json")
        st, _, _ = s.post("/api/draft", {"decisions": {"docs": {"d": "keep", "t": "x"}}, "general": "g", "seen": ["docs"],
                                         "open": ["docs", 7, "api"]})
        self.assertEqual(st, 200)
        drafts = list((s.data / "drafts").glob("*.json"))
        self.assertEqual(len(drafts), 1)
        self.assertEqual(json.loads(drafts[0].read_text(encoding="utf-8"))["open"], ["docs", "api"],
                         "open branches are kept (strings only) so the map reopens as it was")
        s.post("/api/close", {})
        code, out, _ = s.finish()
        self.assertEqual(code, 0)
        res = json.loads(out)
        self.assertEqual(res["status"], "closed")
        self.assertEqual(res["decisions"], [])
        self.assertTrue(drafts[0].exists(), "draft must survive Close")
        # and it is restored into the page on the next run
        s2 = self.start("--json")
        _, html, _ = s2.req("GET", f"/s/{s2.token}/")
        self.assertIn('"docs": {"d": "keep", "t": "x"}', html)
        s2.post("/api/submit", {"action": "submit", "decisions": {"docs": {"d": "keep", "t": ""}}})
        s2.finish()
        self.assertFalse(drafts[0].exists(), "draft is cleared after a real submit")

    def test_heartbeat_timeout_closed_tab(self):
        s = self.start("--json", "--heartbeat-grace-sec", "1")
        st, _, _ = s.post("/api/heartbeat", {})
        self.assertEqual(st, 200)
        t0 = time.time()
        code, out, _ = s.finish(timeout=15)
        self.assertEqual(code, 4)
        self.assertEqual(json.loads(out)["status"], "closed_tab")
        self.assertLess(time.time() - t0, 10)

    def test_no_heartbeat_means_no_closed_tab(self):
        s = self.start("--json", "--heartbeat-grace-sec", "0.5", "--timeout-min", "0.03")
        code, out, _ = s.finish(timeout=15)
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["status"], "timeout")

    def test_bad_input_exit_2(self):
        s_path = Path(self.tmp) / "bad.json"
        s_path.write_text('{"root": {"children": []}}', encoding="utf-8")
        p = subprocess.run([sys.executable, str(SCRIPT), str(s_path), "--no-open"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("root: missing 'name'", p.stderr)


class TestParsing(unittest.TestCase):
    def test_branch_decision_covers_items(self):
        doc, _ = mr.normalise(json.loads(json.dumps(TREE)))
        # Keep on the Backend branch covers API and DB; a note on Frontend does not cover Button; Docs has its own note.
        dec = {"be": {"d": "keep", "t": ""}, "frontend": {"d": "", "t": "later"}, "docs": {"d": "", "t": "fine"}}
        res = mr.build_result(doc, "submitted", {"decisions": dec})
        self.assertEqual((res["stats"]["items"], res["stats"]["items_covered"]), (4, 3))
        self.assertEqual(res["stats"]["on_branches"], 1)
        out = mr.format_markdown(res)
        self.assertIn("Reviewed: 3/4 items with 3 decisions", out)
        self.assertIn("applies to everything under it", out)
        # Without branch decisions the extra line stays out.
        res = mr.build_result(doc, "submitted", {"decisions": {"docs": {"d": "keep", "t": ""}}})
        self.assertNotIn("applies to everything under it", mr.format_markdown(res))

    def test_two_top_level_items_do_not_nest(self):
        doc = mr.parse_outline("# My plan\n- A\n- B\n  - B1\n")
        self.assertEqual(doc["root"]["name"], "My plan")
        self.assertEqual([c["name"] for c in doc["root"]["children"]], ["A", "B"])
        self.assertEqual(doc["root"]["children"][1]["children"][0]["name"], "B1")
        self.assertEqual(doc["root"]["children"][0]["children"], [])

    def test_single_root_and_nesting(self):
        doc = mr.parse_outline("# T\n- Root :: the root\n  - A [done]\n    - A1 [human] [todo]\n  - B\n")
        r = doc["root"]
        self.assertEqual((r["name"], r["note"]), ("Root", "the root"))
        self.assertEqual([c["name"] for c in r["children"]], ["A", "B"])
        a1 = r["children"][0]["children"][0]
        self.assertTrue(r["children"][0]["done"] and a1["h"] and a1["todo"])

    def test_four_space_indent_numbered_and_double_colon(self):
        doc = mr.parse_outline("# T\n1. Use std::vector :: container choice\n    * child [id:c1]\n2. Second\n")
        kids = doc["root"]["children"]
        self.assertEqual(kids[0]["name"], "Use std::vector")
        self.assertEqual(kids[0]["note"], "container choice")
        self.assertEqual(kids[0]["children"][0]["id"], "c1")
        self.assertEqual(kids[1]["name"], "Second")

    def test_no_bullets_raises(self):
        with self.assertRaises(ValueError):
            mr.parse_outline("# Title\njust text\n")

    def test_bom_json(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "bom.json"
            p.write_bytes(b"\xef\xbb\xbf" + json.dumps(TREE).encode("utf-8"))
            doc, warns = mr.load(p)
            self.assertEqual(doc["title"], "Test plan")
            self.assertEqual(warns, [])
            q = Path(t) / "bom.md"
            q.write_bytes(b"\xef\xbb\xbf# X\n- a\n- b\n")
            self.assertEqual(len(mr.load(q)[0]["root"]["children"]), 2)

    def test_ids_auto_and_duplicates(self):
        tree = {"root": {"name": "R", "children": [
            {"name": "Same"}, {"name": "Same"}, {"name": "X", "id": "dup"}, {"name": "Y", "id": "dup"},
            {"name": "Z", "children": [{"name": "Leaf!"}]}]}}
        doc, warns = mr.normalise(tree)
        ids = [c["id"] for c in doc["root"]["children"]]
        self.assertEqual(ids, ["same", "same~2", "dup", "dup~2", "z"])
        self.assertEqual(doc["root"]["children"][4]["children"][0]["id"], "z/leaf")
        self.assertEqual(doc["root"]["id"], "root")
        self.assertEqual(len(warns), 2)
        self.assertTrue(all("duplicate id" in w for w in warns))

    def test_validation_paths(self):
        with self.assertRaisesRegex(ValueError, r"root\.children\[1\]: missing 'name'"):
            mr.normalise({"root": {"name": "R", "children": [{"name": "ok"}, {"note": "x"}]}})
        with self.assertRaisesRegex(ValueError, r"children: must be a list"):
            mr.normalise({"root": {"name": "R", "children": "nope"}})

    def test_aliases(self):
        doc, _ = mr.normalise({"root": {"name": "R", "children": [{"name": "a", "status": "done"}, {"name": "b", "kind": "human"}]}})
        self.assertTrue(doc["root"]["children"][0]["done"])
        self.assertTrue(doc["root"]["children"][1]["h"])

    def test_examples_load(self):
        for ex in ("auth-feature-plan.json", "plan-example.md", "plugin-self.map.json"):
            doc, warns = mr.load(ROOT / "examples" / ex)
            self.assertTrue(doc["root"]["children"], ex)
            self.assertEqual(warns, [], ex)


if __name__ == "__main__":
    unittest.main()
