# Changelog

## 1.2.0 (2026-11-19)
One colour system with a dark theme, round-to-round review, and consistent wording. Shaped by a brand audit and a look at similar tools (Plannotator, PR review, mind-map tools).

### Review rounds
- On round 2 and later, every node Claude added or changed is marked (a dot on the map, a tag in the outline), and the panel shows the old text and what you said last round. Removed nodes are listed with your old decision. A header chip ("Round 2 · 3 changed · 1 new · 1 removed") filters to what changed, and a fresh round opens the way to every change.
- The server keeps the last sent round next to the plan's address (nodes and decisions) and sends the difference to the page.
- In a gate review with Cut, Change or Ask decisions, Approve becomes **Approve with notes**, and the end screen says Claude treats them as guidance.

### Colour and theme
- Every colour is a token: neutrals, decisions, status and eight branch hues, each with light and dark values. Nothing in the CSS or the script is hard-coded any more.
- Dark theme that follows the system, or press `T` (or the ◐ button) for light, dark or system; remembered per browser.
- Decision colours keep the same hex in both themes and pass contrast in both (white text ≥ 5:1, fill ≥ 3:1 on every surface). Cut, Ask and Note were below 3:1 on dark before.
- New branch palette (canopy teal, dusk indigo, iris violet, orchid, rose, moss, ochre, bark) that stays clear of the decision and focus colours; the two slate branches that looked like Note are gone.
- Inputs get a 3.5:1 edge; one type scale, radius set and shadow set; the icon's leaves now use branch colours instead of decision colours.
- `docs/brand.md`: the palette, contrast numbers, type and shape rules, and a glossary.

### Large trees
- `1`–`4` show that many levels. `W` turns on walk mode: Keep or Cut moves straight to the next item not covered yet.

### Wording
- "Covered n/N items", "Send review…", "Collapse all", "Saved · 14:02", "to do", "human step"; the gate rule is one sentence everywhere ("Approve unlocks once you have opened or decided on every top-level branch").
- The skill now tells Claude to look for the line the server really prints ("Canopy ready: …"), and a bare tree with no name is titled "Plan".
- README: corrected keyboard behaviour and the progress counter, added rounds, themes and why a tree beats line comments.

## 1.1.1 (2026-11-18)
Fixes from a full review done with the Claude in Chrome extension, and a stable link between review rounds.

### Same link every round
- Each plan file is served at the same address on every round (same port and token, kept in the data folder). Before, every run picked a new random port and token, so when Claude revised the plan and opened it again you got a new link and the old tab pointed at nothing.
- The finished tab now watches that address and shows **Open the next round** when Claude opens the plan again. An open tab whose plan Claude changed offers a reload.

### Fixes
- The note box is a fresh element for each node, so the browser's undo (Ctrl+Z) can no longer bring back another node's text and save it here.
- K, X, C and A all leave focus on the map; C and A no longer jump into the note box, so typing a note after X can't fire shortcuts on other nodes. Each decision shows a notice ("Cut: Fire safety NOC · Enter to add a note · U to undo"); **U** or Ctrl+Z on the map undoes the last decision.
- The hover tooltip no longer shows a decision you just removed.
- Selecting, opening branches and filtering save quietly: "Draft saved" appears only after you change something.
- The outline starts below the search bar whatever its height.
- The legend opens only on your first visit (when there is room) and stays closed after that unless you open it.
- Choosing a filter moves the map to the matches (all of them when they fit at reading size).
- Shift+N goes to the previous item without a decision.

## 1.1.0 (2026-11-17)
Readability and gate fixes found while recording the demo, and fixes from a real review of a 105-node map.

### Large maps
- Expand all, Collapse and the first view fit at a readable zoom (labels stay about 10 px or larger) and you pan for the rest; F / Fit still shows the whole map.
- Outline view (button or `O`): the same tree as an indented list with each node's note inline. It shares open branches, selection and decisions with the map and is remembered.
- Search (`/`) and a filter: not reviewed yet, with my decision, Change or Ask, human steps, to do, done. Matching branches open, the rest fades, Enter jumps to the next match.
- Hovering any node shows its path, note and your decision.
- Progress counts end items (nodes with no children). Keep, Cut, Change or Ask on a branch counts for everything under it that has no decision of its own, so one K keeps the rest of a branch. `N` jumps to the next node not covered yet.

### Fixes
- Jumping with `N`, the decision list or the send sheet selected the node only after the animation, so a key pressed right away went to the previous node (and could clear its decision). Selection is now immediate, and the composer names the node a decision applies to.
- The header's Close / Send / Approve buttons stay pinned on the right when the window narrows; the layout stacks only below 640 px.

### Send step
- Copy as Markdown and Download JSON in the send sheet, to hand the decisions to another session.
- "Back to the map" closes the send sheet (it did nothing), and so does a click outside it. Zero counts are hidden.

### Feedback for every action (from a design, code, e2e and accessibility review)
- Notes save as you type; the button is now **Done** (Ctrl+Enter), which shows "Saved ✓ 14:02" and pulses the node. The save status shows next to what you last edited, the general note included.
- Short notices on the map for: every item covered, "Select a node first", sending, the Expand all hint (once per session), and Fit or zoom pressed in the outline.
- Items covered by a branch decision show a hollow badge; the panel says "Covered by Keep on Backend".
- A locked Approve says what is left and opens the next branch. In a gate review, Expand all, selecting a top-level branch, or a decision on the root count as looking.
- Losing the server shows a banner and "Reconnected" when it is back; a review restarted by Claude says to open the new link. Requests time out after 5 s.
- Search: Enter and Shift+Enter step through matches ("3 of 14") with focus kept in the box; Esc or Clear resets search and filter. Fading on the map works (it was overridden by the entry animation), links fade too, and the selected node stays visible.
- Selecting a node when zoomed out zooms back to reading size; nodes no longer hide under the search bar or legend.
- Drafts keep the newer of the server and browser copy (edits made while the server was down survive a restart) and reselect the node you were on.
- The server answers 409 to a second finish instead of a silent OK, and the page says the review already ended.

### Layout and accessibility
- The composer sits right under the selected node (shorter Tab path, no dead space); on phones it comes first and stays pinned, the header is compact and its actions get their own row.
- Keyboard: the legend opens with Enter or Space (Space used to collapse the map); arrows skip filtered-out rows; the outline no longer loses or bounces focus.
- Screen readers: quieter live regions, node notes as descriptions, set size and position, "covered by" in labels, and a modal end screen with focus on its heading.
- Higher contrast for nodes under a Cut, and reduced motion also covers zoom.

### Map
- Long node labels wrap to two lines (balanced at a word break, hard break for very long words) instead of cutting at 34 characters; only text past about 70 characters gets "…", and the full name is in the tooltip and panel.
- Fit fits every visible node: bounds come from the layout rather than the mid-animation SVG box, it keeps clear of the legend and zoom buttons, and it can zoom out further (min 5%).
- The legend opens on first use, folds away after your first decision, and remembers whether you opened or closed it.
- A restored draft reopens the branches that were open, so the map matches the "Branches n/N" counter (older drafts reopen the branches already looked at).

### Panel and gate
- Larger side-panel type (15 px base, 18 px node title); decision notes show in full and wrap.
- With `--gate`, a hint next to Approve says what is left ("Review 2 more branches: Database, Rollout"); clicking it opens the next one.
- End screens (Sent, Approved, Change requests sent, Closed) are full-screen, large and high-contrast, colour-coded, with a count per decision.

### Agent side
- Drafts also store `open` (ids of expanded nodes).
- Result stats add `items`, `items_covered` and `on_branches`; the Markdown says "Reviewed: 60/83 items with 18 decisions" and, when a branch was ruled on, that the decision applies to everything under it.

## 1.0.0 (2026-11-16)
First plugin release, evolved from the `canopy` user skill.

### Security
- Per-session token in the page, required as `X-Canopy-Token` on every POST; Host and Origin checks; JSON only; 1 MB body cap; page served only at `/s/<token>/`; strict CSP; all node text escaped.

### Offline
- d3 v7.8.5 bundled in `assets/` (sha256 in README); system fonts; no network requests at runtime.

### Review
- Per-node decisions Keep / Cut / Change / Ask (keys K X C A) plus optional text; "Reviewed n/N" and `N` for next unreviewed.
- Label click selects, chevron toggles; clicked node stays put; opening pans to show children; arrow-key tree navigation with tree semantics.
- Composer fixed at the bottom of the side panel; summary sheet before every send; in-page Close confirmation; legend; status colours separate from branch colours.
- `--gate`: Approve / Request changes, Approve only after every top-level branch was opened or ruled on.

### Agent side
- `--json` output with `status`, decisions keyed by stable node `id`, `general`, `stats`; Markdown remains the default and always starts with a status line.
- Stable node ids (given or generated from the name path); duplicate ids fixed with a warning.
- Drafts saved server-side in `${CLAUDE_PLUGIN_DATA}/drafts/` (fallback `~/.canopy/drafts`), kept on Close, timeout and closed tab.
- Default timeout 110 min; heartbeat every 20 s, `closed_tab` after 90 s without one.
- BOM-tolerant loader; outline parser fixes (several top-level items, any indent, numbered bullets, `std::vector`); input validation with node paths; `--export-plan PLAN.md`.
- Launchers trying `python3`, `python`, `py -3`. Exit codes 0 / 2 / 3 / 4.
