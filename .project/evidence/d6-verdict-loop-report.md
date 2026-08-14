# D6 Verdict Loop Report

Source evidence: `.project/evidence/d6-verdict-loop-gate.json`
Recorded at: `2026-08-13T04:07:24.185927+00:00`

## Gate

- Name: `D6_TWO_VERDICTS_FROM_ONE_ACTION_TWICE`
- Consecutive runs: `2`
- Passed: `True`
- Model generation attempts: `10 of 10 - pass - 10 of 10 live CodeLlama attempts returned schema-valid patch candidates (.project/evidence/d6-model-generation-attempts.json)`

## Run 1

- Mission: `ff510e8a-d826-4dbd-978b-11c71c8fec70`
- Elapsed ms: `0.339`

### Verdict Summary

- Mission verdict: `VERIFIED`
- Verified candidates: `1`
- Rejected candidates: `1`

### Candidate `d52c98ab-f6a6-46cb-a502-844cfa3f55d4`

Verdict: `VERIFIED`

| Gate | Status | Detail |
|---|---|---|
| compile | PASS | fixture compiles |
| reproducer_eliminated | PASS | reproducer eliminated |
| regression_preserved | PASS | regression preserved |
| static_delta | NOT_RUN | cut from seven-day build; disclosed |
| renewed_fuzzing | NOT_RUN | cut from seven-day build; disclosed |

### Candidate `d5ffab14-f99c-4d9a-ad8c-fc1c7e366ed4`

Verdict: `REJECTED`

| Gate | Status | Detail |
|---|---|---|
| compile | PASS | fixture compiles |
| reproducer_eliminated | PASS | reproducer eliminated |
| regression_preserved | FAIL | tab expansion regression failed |
| static_delta | NOT_RUN | cut from seven-day build; disclosed |
| renewed_fuzzing | NOT_RUN | cut from seven-day build; disclosed |

## Run 2

- Mission: `a25be200-7448-4462-b9e3-b78ac916021f`
- Elapsed ms: `0.224`

### Verdict Summary

- Mission verdict: `VERIFIED`
- Verified candidates: `1`
- Rejected candidates: `1`

### Candidate `2e6121f8-db43-4097-9463-30bf0cfc147a`

Verdict: `VERIFIED`

| Gate | Status | Detail |
|---|---|---|
| compile | PASS | fixture compiles |
| reproducer_eliminated | PASS | reproducer eliminated |
| regression_preserved | PASS | regression preserved |
| static_delta | NOT_RUN | cut from seven-day build; disclosed |
| renewed_fuzzing | NOT_RUN | cut from seven-day build; disclosed |

### Candidate `dead1b67-9ba1-41f3-a90e-0403e4902fd7`

Verdict: `REJECTED`

| Gate | Status | Detail |
|---|---|---|
| compile | PASS | fixture compiles |
| reproducer_eliminated | PASS | reproducer eliminated |
| regression_preserved | FAIL | tab expansion regression failed |
| static_delta | NOT_RUN | cut from seven-day build; disclosed |
| renewed_fuzzing | NOT_RUN | cut from seven-day build; disclosed |
