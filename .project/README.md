# `.project/` — company state

Working state for the multi-agent company. Read `state.md` first on every session.

| File | What's in it |
|---|---|
| `intake.md` | The answered project brief, derived from `docs/` with sources cited. DEFERRED items list what the CEO still owns. |
| `state.md` | Phase log — status, date, GO/NO-GO verdict, blockers, deferred items. The current-truth file. |
| `decisions.md` | Append-only decision records from every role. Never edit history; append a correction. |

Roster, hire/fire rules, and the review chain live in [`../.claude/COMPANY.md`](../.claude/COMPANY.md).
Deliverables go in `docs/`, not here — continue that directory's existing numbering rather than
assuming a fixed table.

`state.md` can go stale if work happens outside a `/company` invocation. Check `git log` and the
actual files before trusting a phase status.
