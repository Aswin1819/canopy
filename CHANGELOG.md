# Changelog

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
