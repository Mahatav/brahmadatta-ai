import type { FindingSummary } from '../api/client';
import { STAGE_ROWS } from '../design/phases.ts';
import type { MissionStage } from '../events/store';

/**
 * The "risky-change summary" half of #26's git-history panel, built from real data.
 *
 * `Mission`/`Snapshot` (`apps/control-api/missions/models.py`, read directly — see
 * D-151) record exactly one ingested commit per mission; there is no multi-commit log or
 * per-commit diff anywhere in the contract. So "recent history" cannot honestly mean "a
 * list of recent commits" today — that data does not exist. What *does* exist, real and
 * already flowing through `GET /missions/{id}/findings`, is every `Finding` whose
 * `discovery_method` is `STATIC_ANALYSIS` (contracts/enums.py): Semgrep matches (#22) and
 * compiler diagnostics (#23), both "surfaced by reading source text... with no execution
 * and no crash involved" per that enum's own docstring. Grouped by file, that is a real,
 * literal reading of "risky-change summary" — which files in the ingested snapshot carry
 * a static-analysis-flagged risk signal — without overclaiming a commit history this
 * system does not track.
 */

export type RiskyFileSeverity = FindingSummary['severity'];

export interface RiskyFileGroup {
  filePath: string;
  findingCount: number;
  topSeverity: RiskyFileSeverity;
  sampleTitle: string;
}

const SEVERITY_RANK: Record<RiskyFileSeverity, number> = {
  CRITICAL: 4,
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
  INFO: 0,
};

/**
 * Groups the subset of findings surfaced by static analysis (never fuzzing/replay) by
 * file path, ranked by the highest severity present in that file, then by finding count.
 * Findings from any other `discovery_method` are excluded — a fuzzer-discovered crash is
 * not a "risky change" signal in the git-history sense this panel is honest about.
 */
export function summarizeRiskyChanges(findings: readonly FindingSummary[]): RiskyFileGroup[] {
  const byFile = new Map<string, FindingSummary[]>();
  for (const finding of findings) {
    if (finding.discovery_method !== 'STATIC_ANALYSIS') {
      continue;
    }
    const filePath = finding.location.file_path;
    const existing = byFile.get(filePath) ?? [];
    existing.push(finding);
    byFile.set(filePath, existing);
  }

  const groups: RiskyFileGroup[] = Array.from(byFile.entries()).map(([filePath, fileFindings]) => {
    const topSeverity = fileFindings.reduce<RiskyFileSeverity>(
      (top, finding) => (SEVERITY_RANK[finding.severity] > SEVERITY_RANK[top] ? finding.severity : top),
      fileFindings[0]?.severity ?? 'INFO',
    );
    const sample = fileFindings.find((finding) => finding.severity === topSeverity) ?? fileFindings[0];
    return {
      filePath,
      findingCount: fileFindings.length,
      topSeverity,
      sampleTitle: sample?.title ?? '',
    };
  });

  return groups.sort((a, b) => {
    if (SEVERITY_RANK[b.topSeverity] !== SEVERITY_RANK[a.topSeverity]) {
      return SEVERITY_RANK[b.topSeverity] - SEVERITY_RANK[a.topSeverity];
    }
    return b.findingCount - a.findingCount;
  });
}

/**
 * Whether `ANALYZE` (the stage that runs Semgrep/#22 and captures compiler diagnostics
 * during `BASELINE`/#23 — see `docs/09-company/06-architecture-spec.md`'s `TRIAGE` row)
 * has run to completion for this mission — the same "any row strictly before the current
 * stage has necessarily already completed" reasoning `StageTimeline.tsx::deriveRowState`
 * already uses, extracted here so this panel can render an honest "0 static findings, ANALYZE
 * ran clean" instead of confusing that with "ANALYZE has not run yet" (C8's real-zero rule).
 */
export function hasAnalyzeStageBeenReached(
  snapshot: { completedStages: readonly MissionStage[]; stage: MissionStage | null },
): boolean {
  if (snapshot.completedStages.includes('ANALYZE')) {
    return true;
  }
  const analyzeIndex = STAGE_ROWS.findIndex((row) => row.stage === 'ANALYZE');
  const currentIndex = snapshot.stage ? STAGE_ROWS.findIndex((row) => row.stage === snapshot.stage) : -1;
  return currentIndex > analyzeIndex;
}
