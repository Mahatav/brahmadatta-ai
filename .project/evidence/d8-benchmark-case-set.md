# D8 Benchmark Case Set

Issue: #61  
Target: `demo/repositories/pktcfg`  
Status: Defined, with missing candidate fixtures now committed.

## Publication Rule

The current controlled set is not large enough to publish percentage benchmark claims.
Metric rows remain targets until a measured benchmark run produces a defensible denominator.

## Cases

| Case | Role | Artifact | Expected outcome |
|---|---|---|---|
| BD-001 | Positive defect | `.project/evidence/d5-live-fuzzing.json` | Sanitizer-confirmed heap-buffer-overflow |
| BD-001-A | Correct candidate | `candidate-a-correct-bounds-fix.patch` | Verified |
| BD-001-B | Wrong candidate | `candidate-b-rejected-crash-only-fix.patch` | Rejected by regression |
| BD-001-P | Policy candidate | `candidate-p-policy-rejected-out-of-scope.patch` | Rejected before verification |
| BD-001-C | Compile candidate | `candidate-c-compile-failure.patch` | Rejected by compile gate |
| BD-001-M | Model attempts | `.project/evidence/d6-model-generation-attempts.json` | At least 3 of 10 local CodeLlama candidates accepted by schema/policy |
| BD-002 | Clean control | Candidate A applied | Zero findings, stated as a measured zero only |
| BD-003 | Budget control | Baseline with 10s fuzz budget | Budget exhausted, not reported as zero |
| BD-004 | Authorization control | Unauthorized repository reference | Refused before mission creation |

## Why This Closes The Definition Gap

Before this record, success metrics had targets but no case list, denominator, or false-positive
opportunity. This set supplies the missing denominator and explicitly marks which claims are
ready to measure versus which remain non-publishable targets.
