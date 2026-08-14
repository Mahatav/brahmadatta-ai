# Security Policy

## Scope

Brahmadatta AI is an authorized defensive security system. Reports are welcome for
vulnerabilities in the orchestration code, model gateway, command center, infrastructure,
workers, adapters, schemas, and documentation that could affect confidentiality,
integrity, availability, or evidence correctness.

The repositories under `demo/repositories/` are deliberately vulnerable fixtures. A crash,
memory-safety defect, weak parser behavior, or rejected patch inside those fixture trees is
in scope only when it escapes the fixture boundary or causes Brahmadatta to make a false
claim about authorization, containment, provenance, or verification.

## Reporting

Use GitHub private vulnerability reporting or a private maintainer channel when available.
Do not open a public issue for a sensitive vulnerability until the maintainer has confirmed
it is safe to discuss publicly.

For non-sensitive bugs, documentation defects, and fixture corrections, use normal GitHub
issues and include:

- affected path or component
- reproduction steps
- expected and actual behavior
- whether the issue affects a real product surface or only a demo fixture

## Rules For Research

- Test only repositories and systems you own or are explicitly authorized to assess.
- Do not scan, attack, or exploit third-party targets through this project.
- Do not submit secrets, proprietary source code, or private repository snapshots in a
  public report.
- Do not rely on model confidence as proof. Security claims must be backed by deterministic
  evidence such as tests, sanitizer output, replay artifacts, logs, or signed-off decisions.

## Fixture Disclosure

`demo/repositories/pktcfg` intentionally contains a seeded memory-safety defect and paired
candidate patches for the competition demo. Those files are not production software and
must not be reused as a library.
