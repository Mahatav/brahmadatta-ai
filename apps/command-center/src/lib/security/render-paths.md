# Command Center Render-Path Audit

Issue: #90, Frontend security review: untrusted strings rendered into the Command Center.

Rule: repository-derived, tool-derived, and model-derived strings enter the UI through `renderSafety.mjs`. React remains the escaping boundary for DOM text. Raw HTML rendering is forbidden unless the call site explains why it is safe.

## Panels

| Panel | Target-derived strings | Boundary |
| --- | --- | --- |
| Local Repository | local path scan errors, repository name, detected stack markers, browser-selected relative paths | `LocalRepositoryIntake` sanitizes status copy and stores sanitized repository context; the manifest digest is computed from raw local metadata before display sanitization. |
| Command Bar | mission repository ref, mission state, latest timestamp, local repository name | `store.ts` sanitizes mission repository refs and local repository context; `MissionCommandCenter` renders text only. |
| Repo Intel | local repository display name, stack, manifest fingerprint | `store.ts` and `LocalRepositoryIntake` sanitize strings; hashes are displayed as bounded prefixes. |
| Automation Progress | stage labels, progress percentages | enum-owned values only; no raw target text. |
| Live Work | finding title, severity/category, file path/function/line, baseline counts, latest mission message | `store.ts` sanitizes event messages and finding summaries before they reach component state. |
| Local AI Core | selected repository name and operator prompt echo | `AIParticleCore` sanitizes repo labels, prompts, and transcript text before display. |
| Control Plane | control API error messages and health identifiers | `SystemStatus` sanitizes error, service, version, status, and trace display strings. |
| Exported Markdown/JSON report | future Command Center export copy | `sanitizeJsonReportValue` and `sanitizeMarkdownText` use the same ANSI/control/bidi stripping and length caps; Markdown additionally escapes HTML-significant characters. |

## Raw HTML Review

No `set:html`, `innerHTML`, `dangerouslySetInnerHTML`, or Astro raw-HTML directive is used in the Command Center source. `scripts/check-render-safety.mjs` fails if one appears.

## Length And Control Characters

Display strings are capped by default at 240 characters with a visible `...[truncated]` marker. Report strings are capped at 4000 characters. ANSI escapes, C0/C1 controls, and bidi/RTL override characters are stripped before render.
