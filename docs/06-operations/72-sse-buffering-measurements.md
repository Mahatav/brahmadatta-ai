# SSE buffering — what was measured, and what it settles

| Field | Value |
|---|---|
| Project | Brahmadatta AI |
| Owner | devops |
| Status | Measured 2026-08-08; supersedes the comment previously carried alone in `sse.conf` |
| Related | #114, D-013, `infrastructure/compose/nginx/includes/sse.conf`, `infrastructure/scripts/smoke-sse.sh` |

## Why this document exists

`infrastructure/compose/nginx/includes/sse.conf` carried a comment claiming
`proxy_buffering off` is what keeps the mission event stream alive through nginx — that
without it, SSE works against Django directly and dies silently behind the proxy. Nobody
had reproduced that stall. The `security-research-engineer` seat tried it while building a
negative control for #71 on nginx 1.27 and got a clean pass under every condition it tried:
`proxy_buffering on`, 256k buffers, `proxy_cache`, `gzip`. It withdrew its control rather
than ship a check that passes regardless of the setting, and correctly filed it as a
finding (#114) rather than quietly cutting the check.

This document is the answer: the stall reproduces, the comment's outcome was right, and its
mechanism was incomplete. The corrected mechanism is now in `sse.conf` itself, condensed;
this file carries the full method and numbers behind each line of it.

## Method

Stub upstream (`infrastructure/scripts/testing/sse-stub.py`), real committed nginx config,
raw-socket HTTP/1.1 probe pinning ALPN so the transport cannot silently upgrade to HTTP/2
(`infrastructure/scripts/testing/sse-timing-probe.py`). Two nginx versions:
`nginxinc/nginx-unprivileged:1.27.5` and `:1.29.8`. All results below were identical
between the two versions — this is not a version behaviour.

## Findings

### 1. `proxy_buffering off` is required for HTTP/1.1 — and it is a byte threshold, not "held until the response ends"

| config | frame size | first frame |
|---|---|---|
| `proxy_buffering off` | ~110 B | 0.003s |
| `proxy_buffering on` | ~110 B | 4.86s (i.e. all 12 frames released together, at the point the stub finished writing — never, on a real infinite stream) |
| `proxy_buffering on` | 512 B | 4.86s |
| `proxy_buffering on` | 1,400 B | 4.05s |
| `proxy_buffering on` | 1,600 B | 3.64s |
| `proxy_buffering on` | 4,096 B | 1.21s |
| `proxy_buffering on` | 8,192 B | 0.41s |
| `proxy_buffering on` | 16,384 B | 0.004s — no stall at all |

nginx releases accumulated proxy buffers once roughly 16 KB has piled up, not when the
response ends. This is why naive reproduction attempts kept coming back clean: the security
review's own note says its negative control used buffers "wider than the entire mission's
event stream" — with frames that large, buffering on and off are indistinguishable. Real
mission events are ~110-400 bytes. At that size, buffering on means 40-150 events of
silence, which is the entire demo.

Raised buffer size (`proxy_buffers 8 256k`) neither causes nor prevents the stall — the
threshold tracks accumulated bytes, not buffer count or size.

### 2. HTTP/2 does not stall, and that is the trap in this whole area

Same nginx, same buffering-on config, same ~110-byte frames, negotiated over ALPN h2:

| config | transport | first frame | spread |
|---|---|---|---|
| `proxy_buffering on` | h2 | 0.108s | 4.355s (STREAMING) |
| `proxy_buffering off` | h2 | 0.109s | 4.358s (STREAMING) |

Both listeners in `conf.d.dev` and `conf.d.finale` have `http2 on`. A browser talking to
the Command Center would very likely stream fine even with `proxy_buffering on` — the
stall is HTTP/1.1-only. This does NOT make the setting optional:

- every non-browser consumer of this stream is HTTP/1.1: `curl`, `urllib`, `requests`,
  `httpx` without the `h2` extra, and every test harness in this repository
- the moment a second proxy hop, a load balancer, or `http2 off` lands in front of the
  ingress, the transport downgrades and the stall becomes total
- it costs nothing to keep

It IS the reason a naive probe can report "buffering is fine" and be wrong: `curl`
negotiates HTTP/2 by default over TLS. Any reproduction of this bug must pin HTTP/1.1
explicitly. `sse-timing-probe.py` does this via `ssl_context.set_alpn_protocols(["http/1.1"])`.

### 3. `proxy_read_timeout 3600s` — required, and this is the untested half of the original comment

The original comment asserted 3600s "covers the longest phase" without ever testing the
timeout itself. `proxy_read_timeout` measures the gap between two reads FROM THE UPSTREAM —
so only a genuinely idle upstream exercises it. Stub: 2 frames, then 20s of silence, then 4
more.

| `proxy_read_timeout` | outcome |
|---|---|
| `3600s` (committed) | 6 frames, spread 21.6s, connection survived the 20s gap |
| `5s` (injected violation) | nginx closed the client connection at 5.411s. 2 frames delivered. |

Between mission phases (a fuzzing campaign, a ten-attempt patch generation run) nothing is
emitted for minutes. The nginx default of 60s would drop the connection mid-mission with no
operator-visible error.

### 4. `gzip off` — required only if gzip is ever made to apply, and it is easy to test wrong

| config | outcome |
|---|---|
| `gzip on`, nothing else | first frame at 0.003s — no effect whatsoever |
| `gzip on` + `gzip_proxied any` + `gzip_types text/event-stream` | `Content-Encoding: gzip`, zero decodable frames in 9 seconds — total stall |

`gzip on` alone does nothing to this response because nginx defaults `gzip_proxied off`
(never compress a proxied response) and `gzip_types text/html` (our content type is not
listed). This is why casually flipping `gzip on` in a test and seeing no breakage proves
nothing — the two extra directives are what actually turn gzip on for this response. When
it does apply, gzip's own output buffering coalesces frames and the stream dies for the
same underlying reason `proxy_buffering on` does. Keeping `gzip off` in `sse.conf` blocks a
future `gzip_types text/event-stream` added at the `http` level from silently reaching this
location.

### 5. `proxy_cache off` — prudent, not demonstrated. Kept, relabelled.

The original comment claimed a cached infinite response is an infinite cache write. This
was tested directly with a real `proxy_cache_path` zone, `proxy_cache` enabled, and
`proxy_ignore_headers Cache-Control` (so the stub's `no-cache` header could not opt out on
its own):

- the stream still arrived incrementally, first frame at 0.004s
- `/tmp/expcache` stayed empty — 4.0K, no files — both DURING the stream and after it ended

nginx does not commit a cache entry for a response it never observed complete. So this
directive is a guard against a future `proxy_cache` addition changing behaviour that has
not been characterised here, not a fix for an observed failure. It costs one directive to
keep. The `sse.conf` comment says so plainly rather than citing it as a proven control.

### 6. Checked and found not to matter

- **Slow consumer.** A client reading 512 B every 0.5s against a producer emitting far
  faster backpressures identically with `proxy_buffering` on and off; `/tmp/proxy_temp`
  stayed empty in both within a 20s observation window. No differential found.
- **nginx version.** 1.27.5 and 1.29.8 behave identically in every case above.

## What this closes, and what it does not

Closes #114's acceptance criteria: the stall reproduces, the mechanism is identified (byte
threshold, HTTP/1.1-only), `proxy_read_timeout` on a genuinely idle stream is now tested,
and `proxy_cache off` is relabelled from "control" to "prudent guard" rather than asserted
without evidence.

Does not close: a slow-consumer stall under sustained backpressure over a longer window
than 20s was not observed to differ, but 20s is not a mission-length window. If a future
finding needs that, it is a new measurement, not an extrapolation from this one.

## Reproducing this

```
infrastructure/scripts/smoke-sse.sh
```

runs four cases against the real committed config — two of them injected violations that
must fail — and is the CI-enforced version of the table above (`ingress` job in
`.github/workflows/ci.yml`).
