# Project State — Brahmadatta AI

| Field | Value |
|---|---|
| Repository | https://github.com/Mahatav/brahmadatta-ai (private) |
| Board | https://github.com/users/Mahatav/projects/3 |
| Deadline | **2026-08-20** · build target **2026-08-13** |
| Current phase | 1 — discovery & product definition (CEO seat done; PM seat pending) |
| Last updated | 2026-08-07 |

## Phase log

### Phase 0 — Repository founding · 2026-08-06 · **GO**

**Completed**
- `brahmadatta-ai` created on GitHub, private, `main` protected (PRs required, force-push and deletion blocked, admin enforcement off).
- Full MVP documentation pack (79 documents) imported to `docs/`.
- `CLAUDE.md`, `.gitignore`, top-level `README.md`, `.github/` PR and issue templates.
- `.claude/COMPANY.md` — dynamic roster, hire/fire rules, review chain.
- Four project-specific agent seats defined on the bench.
- `.project/intake.md` pre-filled from the doc pack rather than re-interviewing the CEO.

**Decisions** — D-001 … D-005.

**Verdict: GO.**

### Phase 1 — Discovery & product definition · 2026-08-06 · **partial**

**Hired:** `ceo` (drafting seat). **Retired** after delivery.

**Completed**
- `docs/09-company/01-vision-and-p0-cut.md` — forced P0/P1/P2 ranking (15/10/12), the nine-step minimum viable demo, checkable kill criteria, the four CEO-owned decisions with last-responsible-moment dates, and a critique of the pack. Decisions D-006 … D-012.
- `docs/09-company/02-two-person-24h-cycle.md` — Kelowna/India shift protocol, written handoffs, work split at the API seam.
- `docs/09-company/03-seven-day-plan.md` — the compressed plan replacing the 8-week timeline.
- Board built: 63 issues, 10 day-milestones, `Brahmadatta Delivery` project with per-person columns.

**Not done:** the `product-manager` seat has not run. Its four inherited open questions are on the board as #61, #62, #63, #64 rather than being answered in a phase-1 deliverable — the compressed schedule made a full PM pass less valuable than getting the board built.

**Decisions** — D-013 (stack: Astro + Django + nginx), D-014 (14-day deadline), D-015 (rented GPU cut), D-016 (scaffold removed).

**Verdict: CONDITIONAL GO.** Proceeding to implementation without a formal phase 2–4 pass, because the doc pack already contains architecture, stack, UX direction and a task breakdown, and the seven-day budget cannot absorb three more phase gates. Recorded as a deliberate deviation, not an oversight.

---

## Phase status

| # | Phase | Status |
|---|---|---|
| 1 | Discovery & product definition | partial — CEO seat done, PM seat skipped |
| 2 | Technical strategy & architecture | architect spec and CTO review both in flight (retrofitted after the CEO called out the skipped gates) |
| 3 | UX design | **done** — `04-design-system.md` + `tokens.css`, PR #70, pending PM review |
| 4 | Task breakdown | **audited** — `07-task-breakdown-audit.md`; four coverage gaps closed as #71, #72, #73 and the #49 resequence |
| 5 | Implementation | ready to start at D1 |
| 6 | Security review | D8–11 (#53) |
| 7 | QA | D8–11 (#57) |
| 8 | Deployment prep | folded into D1–D2 (#9, #10, #11) |
| 9 | Documentation | D12–14 (#58) |
| 10 | Post-launch feedback | not applicable — competition MVP |

## Open, owned by the CEO

1. **#2 — confirm the AI Kavach submission deadline.** The 14-day figure came from the CEO; the plan now assumes 2026-08-20. If that is wrong, every milestone shifts.
2. **#3 — competition rules on team composition and agent-authored code.** Potentially disqualifying if assumed wrong.
3. **#63 — whether `git bisect` stays cut.** It carries the git-aware root-cause novelty claim.
4. **Whether Astro survives if D1 slips** — the engineering-manager's cut list puts falling back to Django templates second. That touches D-013, which is the CEO's.

Closed: #8 (visual references) answered by D-017 and D-018. GPU provider and budget made moot by D-015.
