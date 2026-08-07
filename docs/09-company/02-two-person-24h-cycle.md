# Two-Person 24-Hour Cycle

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Document | Company-workflow operating protocol |
| Status | Active |
| Date | 2026-08-06 |

Two humans, twelve and a half hours apart. Used well that is close to double the calendar
throughput of one person. Used badly it is two people who each wake up to a broken `main` and
no idea why.

## The clock

| | Mahatav — Kelowna (PDT, UTC−7) | Raunak — India (IST, UTC+5:30) |
|---|---|---|
| Shift start | 09:00 | 09:00 |
| Shift end | 18:00 | 18:00 |
| That is, in the other's clock | 21:30 → 06:30 IST | 20:30 → 05:30 PDT (previous day) |

The shifts do not overlap. India's working day happens during Kelowna's night, and India
finishes about three and a half hours before Kelowna starts. That is the good case — it means
handoffs are fresh, not stale.

One shared timeline, read against whichever clock is yours. Each band is that person's
09:00–18:00 on their own row.

```
Kelowna (PDT)   06    09    12    15    18    21    00    03    06
                      ├──── MAHATAV ────┤     ├──── RAUNAK ─────┤
India   (IST)   18    21    00    03    06    09    12    15    18
                                        ▲                       ▲
                              handoff → Raunak    handoff → Mahatav
```

**Daily sync, if you want a live one:** India 09:00–09:30 IST = Kelowna 20:30–21:00 PDT.
India's morning, Kelowna's evening. The mirror slot — Kelowna 09:00 PDT = India 21:30 IST —
works equally well if evenings suit Kelowna better. Pick one and keep it; do not alternate.

## The handoff

Both handoffs are written, on the issue, not in chat. Chat scrolls; issues do not.

Ending your shift, on every issue you touched:

```
### Handoff <YYYY-MM-DD>
State: <in progress | blocked | ready for review | done>
Branch: <branch name, pushed>
What works: <what you actually ran, with output>
What doesn't: <the specific failure, not "still debugging">
Next step: <the one thing you'd do first tomorrow>
Running: <any long job left executing, and where its output lands>
```

Then relabel: `handoff:to-raunak` or `handoff:to-mahatav`.

Starting your shift: read every issue carrying a handoff label pointed at you, before opening
an editor.

**Push everything, always, even broken.** A WIP branch that does not compile is worth more than
a clean local tree the other person cannot see. Nothing stays on one laptop overnight.

## The split

The seam is the **event schema and control API contract** — frozen in week 1, changed only by
agreement.

| | Owns |
|---|---|
| **Mahatav** (Kelowna) | Command Center UI, control API surface, evidence records and reports, competition materials |
| **Raunak** (India) | Orchestrator state machine, sandbox, C/C++ toolchain adapter, fuzzing, model gateway |

This is a starting assumption, not a verdict — it was assigned from the architecture's
dependency seam, not from either person's actual strengths. If it is wrong, swap the
`owner:` labels and carry on; nothing else depends on it.

`owner:either` is a real pool, not a dumping ground. Whoever starts their shift with nothing
blocked takes from it.

## What the night shift is actually for

The throughput gain is not "twice the typing". It is **long-running jobs that cost wall-clock
time rather than attention**: a fuzzing campaign, a ten-attempt patch generation run, a full
regression sweep, a GPU spike.

The pattern worth building the habit around: end your shift by *starting* one of those and
writing down where the output lands. The other person reads the result at the top of theirs.
Issues where this applies carry `handoff:to-raunak` / `handoff:to-mahatav` from the moment they
are created, not as an afterthought.

## Rules that keep this from going wrong

1. **Never merge your own PR.** The other person merges it during their shift. This is also the
   review chain in [`.claude/COMPANY.md`](../../.claude/COMPANY.md) — it costs one cycle of
   latency and catches things nobody catches in their own diff.
2. **`parallel-safe` means it — no shared files.** If two issues touch the same file, they are
   not parallel-safe and one of them waits.
3. **A `blocked` issue gets the blocking issue number in a comment**, immediately, before you
   move on. Twelve hours is a long time to be blocked on something nobody was told about.
4. **Kill-criterion issues are checked by whoever's shift ends the week**, and the verdict goes
   in the issue. Failing one triggers the cut written in
   [`01-vision-and-p0-cut.md`](01-vision-and-p0-cut.md) §4 — not a conversation about whether
   to extend.
5. **Anything labelled `needs:ceo` stops being worked on.** Do not guess and proceed on a
   decision only Mahatav can make; it goes in the next escalation batch.
