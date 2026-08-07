## Summary

<!-- What changed and why. Link the issue: Closes #___ -->

## Evidence

Paste real command output — not "should pass".

- [ ] Unit / integration / E2E tests as relevant, **run**, output below
- [ ] Sanitized screenshots or reports for UI or evidence-format changes

```
<!-- test output -->
```

## Security

- [ ] No secrets, credentials, or private source in the diff or in logs
- [ ] No unapproved change to sandbox isolation, model routing, or network access
- [ ] Cleanup works on failure and on cancel
- [ ] Repository content still never reaches an external inference API

## Performance / resource impact

<!-- Wall time, memory, GPU minutes. Measured, or stated as an estimate. -->

## Docs / migrations

<!-- Which docs/ files were updated, which migrations run. -->

## Rollback

<!-- How to undo this if the finale run breaks. -->

## Review chain

Nothing merges on the author's own say-so — see [`.claude/COMPANY.md`](../.claude/COMPANY.md).

- [ ] Reviewed by the seat above the author
- [ ] `cybersecurity` sign-off (required for isolation, auth, secrets, or verification-gate changes)
- [ ] `qa-engineer` verdict where a gate applies
