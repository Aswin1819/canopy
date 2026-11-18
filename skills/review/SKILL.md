---
name: review
description: Open a plan, scope breakdown, spec, architecture or research summary as a collapsible tree in the user's browser, where they rule Keep / Cut / Change / Ask on each node; their decisions (with stable node ids) come back into this session. With --gate it is an approval gate (Approve / Request changes) to run before executing a plan. Use when the user asks for a "mind map", "tree view", "tree review", to "review the plan as a tree", to "approve the plan" visually, or to comment on the structure of something hierarchical.
argument-hint: "[file.json | outline.md] [--gate]"
---

# Tree review / approval gate

A local review loop. The server (Python 3.8+ stdlib, bundled d3, no network) serves the tree on `127.0.0.1` behind a per-session token, waits for the person to act, prints the result on stdout and exits.

## Review or gate?
- **Review** (default): you want feedback on a structure. The person sends Keep / Cut / Change / Ask decisions and notes. Status `submitted`.
- **`--gate`**: you need sign-off before doing the work (writing code, sending, publishing). The page shows **Approve** and **Request changes**. Approve unlocks only after every top-level branch has been opened, selected or ruled on (Expand all counts; a decision on the root covers all). Do not start the work until you get `approved`.
- Add `--json` when you will act on many decisions (recommended); Markdown is the default.

## 1. Write the tree
Prefer JSON, in the project or scratchpad, e.g. `plan.map.json`. Give each node a short `id` you can map back to your plan; if omitted, ids are made from the name path (`backend/export-endpoint`).
```json
{"title": "CSV export", "subtitle": "Scope review before coding",
 "root": {"id": "root", "name": "CSV export", "children": [
   {"id": "be", "name": "Backend", "note": "detail shown in the panel", "children": [
     {"id": "be.endpoint", "name": "Export endpoint", "note": "GET /api/reports/:id/export"},
     {"id": "be.ratelimit", "name": "Rate limit", "todo": true},
     {"id": "be.perm", "name": "Permission check", "done": true}]},
   {"id": "launch", "name": "Announce to beta users", "h": true}]}}
```
- Group by component or scope, not by step order. Names 2-6 words, detail in `note`. 3-4 levels, 3-7 children per node, up to ~150 nodes.
- `h` (or `"kind": "human"`) = human step, `done` / `todo` (or `"status"`) = state.
- A Markdown outline also works: `# Title`, then `- Name :: note [human] [done] [todo] [id:x]`, any consistent indent. Several top-level bullets become children of the title. Example: `${CLAUDE_PLUGIN_ROOT}/examples/plan-example.md`.

## 2. Launch in the background
Bash tool with `run_in_background: true` and `timeout: 7200000`:
```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/launch.sh" <file> --data-dir "${CLAUDE_PLUGIN_DATA}" --json [--gate] [--export-plan PLAN.md]
```
(PowerShell: `& "${CLAUDE_PLUGIN_ROOT}/scripts/launch.cmd" <file> --data-dir "${CLAUDE_PLUGIN_DATA}" --json`.) The launcher picks `python3`, `python` or `py -3`. Read the first line of the task output once to get the URL (`Mind map review ready: http://127.0.0.1:PORT/s/TOKEN/`), give it to the person and say: click a label to select, `+` to open, K / X / C / A to decide, add text for Change and Ask, then Review & send (or Approve / Request changes). Each plan file keeps the same URL on every round (same port and token), so for a second round edit the same file and re-run the same command; the tab left open on the last round offers "Open the next round" by itself.

## 3. Wait, then act on the result
Don't poll or kill the task; you are notified when it exits. JSON shape:
`{status, decisions:[{id, path, name, decision, text}], general, stats}`, decisions in tree order. A decision on a branch applies to everything under it that has no decision of its own (a child's own decision wins). `stats.items_covered`/`stats.items` count end items (nodes with no children) covered that way.

| status | exit | what to do |
|---|---|---|
| `approved` | 0 | Go ahead. Decisions are guidance: apply Change/Cut, answer Ask, as part of the work. |
| `changes_requested` | 0 | Don't start. Revise: apply each `change`, remove each `cut`, answer each `ask` in chat, update the same tree file, offer to re-open it (same command, same URL). |
| `submitted` | 0 | Act on each decision the same way; acknowledge `keep` and `note` briefly. |
| `closed` | 0 | The person closed without sending. Ask in chat what they want; don't assume approval. |
| `closed_tab` | 4 | Tab closed or lost. Drafts are kept: re-run the same command if they want to continue. |
| `timeout` | 3 | 110 min passed. Drafts are kept: re-run the same command. |
| (bad input) | 2 | Fix the file using the error on stderr (it names the node, e.g. `root.children[2]: missing 'name'`) and re-run. |

Duplicate ids are fixed automatically (`id~2`) with a warning on stderr; give same-named siblings explicit ids.

`--export-plan PLAN.md` writes the approved/submitted tree as a Markdown checklist with Cut items removed and Change/Ask notes inline.

## Notes
- Drafts are saved on the server under `${CLAUDE_PLUGIN_DATA}/drafts/` (fallback `~/.canopy/drafts`), keyed by file path + title, restored on reload and on re-run, kept on Close, cleared after a send.
- SSH/remote: add `--port 7777` and forward it (`ssh -L 7777:127.0.0.1:7777`); `CANOPY_BROWSER=none` stops auto-open.
