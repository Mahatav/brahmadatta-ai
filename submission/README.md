# AI Kavach / Terrier Cyber Quest 2026 — Brahmadatta AI submission

The organisers' initial submission: **five slides**, following their exact structure
(introduction/ideation → methodology → stack/architecture → features/novelty → deliverables).

Built 2026-08-30 against `main` @ `0616e15`. Every substantive technical claim is
repository-grounded — the trace is in [`evidence-notes.md`](evidence-notes.md).

## Files

| File | What it is |
|---|---|
| `brahmadatta-ai-aikavach-2026.pptx` | **Submission master.** 16:9, one full-bleed rendered slide per page — pixel-identical to the design below. Opens in PowerPoint / Keynote / Google Slides. |
| `brahmadatta-ai-aikavach-2026-editable.pptx` | Native PowerPoint version — real text boxes, shapes and a vector architecture diagram, for editing wording. Layout may reflow slightly by renderer; the master above is the reference look. |
| `brahmadatta-ai-aikavach-2026.pdf` | Pixel-perfect PDF (1280×720 per page), for emailing / printing / quick review. |
| `brahmadatta-ai-aikavach-2026.html` | The design source. Self-contained; the `.pptx`/`.pdf` are generated from it. Open in a browser; **Print → Save as PDF** reproduces the PDF. |
| `build_pptx.py` | Generator for the editable `.pptx` (`pip install python-pptx && python build_pptx.py`). |
| `preview/slide-1…5.png` | Slide images (3× / ~3840px wide). |
| `evidence-notes.md` | Claim-by-claim map to the file, decision record, or evidence run that backs it. |

## Regenerating

```sh
# from repo root
python3 -m http.server 8899 -d submission &
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="submission/brahmadatta-ai-aikavach-2026.pdf" \
  "http://localhost:8899/brahmadatta-ai-aikavach-2026.html"
python3 -c "import fitz; d=fitz.open('submission/brahmadatta-ai-aikavach-2026.pdf'); \
  [d[i].get_pixmap(matrix=fitz.Matrix(3,3)).save(f'submission/preview/slide-{i+1}.png') for i in range(d.page_count)]"
python3 submission/build_pptx.py            # -> editable .pptx
```

## Design

Follows the Brahmadatta **Command Center** visual system
(`docs/09-company/04-design-system.md`, `packages/ui-components/tokens.css`): one flat
saturated indigo field (`#141C8C`), no borders/glass/glow, panels located by hairline
corner crop marks, every utility label a bracketed monospace string, display type in
Instrument Serif, utility type in Fragment Mono. Semantic colour only — green = verified,
amber = roadmap / disclosed-not-run, coral = rejected. The Slide 3 architecture diagram is
original hairline SVG (geometry only — the design system forbids depicted figures).

## What the deck says, in one paragraph

Brahmadatta AI is an authorised, defensive Cyber-Reasoning System. On a C/C++ repository the
operator owns, it runs one nine-step pipeline across three evidence-gated tiers — deterministic
triage, then destructive sandbox fuzzing with a self-hosted CodeLlama-7B drafting a patch,
then (designed-only) heavy repository reasoning. A patch is accepted only when the reproducer,
the regression suite, static checks and renewed fuzzing prove it — `derive_verdict()` takes the
gate matrix and nothing else. The differentiator, demonstrated live on 2026-08-20: one mission,
one gate matrix, two verdicts — a correct patch VERIFIED and a plausible crash-only patch
REJECTED — with a sha256-manifested evidence bundle a judge can audit offline. Repository
content never leaves for a hosted API; rented GPU was cut entirely; the whole system is four
processes on one machine.
