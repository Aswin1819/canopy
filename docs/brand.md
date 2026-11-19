# Canopy brand and UI guide

One reference for colour, type, shape and wording, so every Canopy surface (the review page, the README, the icon, the demo) looks and reads the same. The tokens live at the top of `assets/template.html`. Change them there, never with a hard-coded value in a rule or in the script.

## Principles

- **Decisions own their colours.** Keep, Cut, Change, Ask and Note have one colour each, and no branch, badge or decoration uses those hues. A decision always shows its letter too (K X C A ✎), so colour is never the only signal.
- **Same meaning in both themes.** Decision colours use the same hex in light and dark. White text on them is at least 4.5:1, and the fill is at least 3:1 on every surface.
- **Flat and quiet.** Limited colour, thin lines, small shadows, short transitions. The plan content is the loudest thing on the page.
- **Tokens, not values.** Components use semantic tokens (`--raised`, `--ink`, `--keep`), never raw hex. SVG gets them through `style()`, because `var()` in SVG presentation attributes is not reliable.

## Colour tokens

### Decisions (both themes)

| Token | Hex | White text on it | On light bg | On dark bg |
|---|---|---|---|---|
| `--keep` | `#15803d` | 5.02 | 5.02 | 3.62 |
| `--cut` | `#c8352f` | 5.24 | 5.24 | 3.47 |
| `--change` | `#b45309` | 5.02 | 5.02 | 3.62 |
| `--ask` | `#0a72b0` | 5.19 | 5.19 | 3.50 |
| `--note` | `#686d75` | 5.21 | 5.21 | 3.49 |
| `--human` (human step) | `#776d5f` | 5.08 | 5.08 | 3.58 |

### Neutrals and status

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#ffffff` | `#11161c` | page, map, outline |
| `--surface` | `#f8fafc` | `#161c23` | side panel |
| `--raised` | `#ffffff` | `#1c232b` | buttons, chips, inputs, dialogs, tooltips |
| `--hover` / `--pressed` | `#f1f4f7` / `#e4e8ee` | `#232b34` / `#2b3440` | hover, toggled on |
| `--ink` / `--ink-soft` / `--muted` | `#1f2933` / `#33404c` / `#5b6672` | `#e6ebf0` / `#c9d1d9` / `#9aa6b2` | text |
| `--line` / `--line-control` | `#dfe3e8` / `#808a96` | `#2e3843` / `#6b7785` | dividers / input edges (3:1) |
| `--focus` | `#3b4bd1` | `#8b98ff` | focus ring, changed-since-last-round dot |
| `--warn-*` | `#fff4e5` bg, `#7a4a06` ink | `#2a1f0f` bg, `#f5c77e` ink | banner, gate hint, warnings |
| `--info-*` | `#eef4fb` bg | `#0f2233` bg | round chip, round diff, next round |
| `--root-fill` | `#1f2933` | `#e6ebf0` | the root node (inverts in dark) |

### Branches

Eight branch hues, in order. The stroke is used for the outline, links and +/−. The tint fills top-level branches. All of them stay clear of the decision colours and the focus colour (CIE76 ΔE ≥ 21 between branches, ≥ 26 to every decision colour).

| # | Name | Light stroke / tint | Dark stroke / tint |
|---|---|---|---|
| 1 | canopy teal | `#0e7c86` / `#e7f2f3` | `#2bb3bf` / `#152f36` |
| 2 | dusk indigo | `#4459d0` / `#eceefa` | `#8d9cf5` / `#252b3f` |
| 3 | iris violet | `#8a3fd0` / `#f3ecfa` | `#c18ef2` / `#2d293e` |
| 4 | orchid magenta | `#b0358f` / `#f7ebf4` | `#e07ac8` / `#322638` |
| 5 | rose | `#c2365a` / `#f9ebee` | `#f28ca3` / `#352932` |
| 6 | moss olive | `#5f7d12` / `#eff2e7` | `#9fbd4a` / `#283123` |
| 7 | ochre | `#8a6a0c` / `#f3f0e7` | `#d2a83a` / `#302d21` |
| 8 | bark brown | `#8a5a3c` / `#f3eeec` | `#cf9a78` / `#2f2b2b` |

The icon's leaves should use the light branch strokes (teal, indigo, violet, orchid, rose, ochre for the large leaves; moss, bark and indigo for the small nodes) and its trunk `--ink`, never a decision colour.

## Type and shape

- Font: the system UI stack (`--f`); ids and code in `--f-mono`. No web fonts, so the page stays offline.
- Sizes: 11 / 12 / 13 / 14 / 15 / 18 / 24 / 36 (`--fs-2xs` … `--fs-3xl`). The end-screen mark (56) is the only exception.
- Radii: 4 (badges), 8 (cards, inputs, chips), 12 (dialogs, overlays), pill (buttons, chips in the header), node 15 / root 20.
- Lines: 1 px for controls, 1.5 px for node and SVG strokes, 2 px for focus and selection.
- Shadows: `--shadow-1` (overlays), `--shadow-2` (tooltip, toast), `--shadow-3` (dialogs) only.

## Words

| Use | Not | Meaning |
|---|---|---|
| node | box | any entry in the tree |
| branch / top-level branch | group | a node with children; the gate counts top-level branches |
| item | leaf, end point | a node with no children; progress counts items |
| decision, decide | ruling, rule on | Keep / Cut / Change / Ask |
| covered | reviewed | an item with a decision of its own or under a branch with one |
| note / general note | comment | free text on a node / on the whole plan |
| plan | mind map | the content; "map" is only the graphical view |
| round | session | each time the same plan file is opened again |
| human step, to do, done | human, todo | node tags |

UI copy rules: sentence case on buttons; "…" only on buttons that open a dialog (Close…, Send review…, Approve…, Request changes…); short active sentences; say what happens ("Saved · 14:02", "Sent to Claude"). The gate rule is always one sentence: "Approve unlocks once every top-level branch has a decision (on the branch or anything in it)."
