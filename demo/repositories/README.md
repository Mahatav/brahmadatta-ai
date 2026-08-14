# Demo Repositories

This directory contains controlled, deliberately vulnerable repositories used by
Brahmadatta AI for authorized demonstrations, tests, and evidence fixtures.

The code here is not production software. Defects inside these repositories are expected
when they are documented by the fixture and contained to the fixture tree. They become a
security concern only if Brahmadatta misrepresents them, runs them outside the authorized
sandbox/fixture boundary, leaks their contents, or lets a fixture influence non-fixture
code paths.

Current fixtures:

| Path | Purpose | Notes |
|---|---|---|
| `pktcfg/` | C/C++ parser target for fuzzing, reproducer replay, patch generation, and verification demos | Contains a seeded heap-buffer-overflow and four benchmark candidate patches. |

Before adding another demo repository:

- document who authorized it
- document whether defects are seeded or discovered
- keep fixture build artifacts out of Git
- keep all exploitability claims tied to deterministic evidence
- make sure the root `SECURITY.md` scope still describes it correctly
