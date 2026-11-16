# Add CSV export to the reports page
Scope review before coding: rule on each branch (Keep / Cut / Change / Ask).

- Backend [id:backend] :: New endpoint plus a streaming writer
  - Export endpoint :: GET /api/reports/:id/export?format=csv
  - Streaming CSV writer :: Rows streamed, so 1M-row reports don't load into memory
  - Permission check :: Same rule as viewing the report [done]
  - Rate limit :: 5 exports per minute per user [todo]
- Frontend [id:frontend] :: Button and progress state
  - Export button :: In the report header, next to Share
  - Progress toast :: Shows while the download starts
  - Column picker :: Choose which columns to export [todo]
- Tests [id:tests]
  - Unit tests for the writer :: Quoting, commas, newlines, unicode
  - E2E download test :: Playwright: click, file appears
- Rollout [id:rollout]
  - Feature flag :: csv_export, off by default
  - Announce to beta users [human] :: Product writes the note
