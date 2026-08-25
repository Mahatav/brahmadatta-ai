import { useRef, useState } from 'react';

import { CandidateCompareOverlay } from '../components/CandidateCompareOverlay';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { emptyMissionSnapshot, type MissionSnapshot } from '../lib/events/store';

/**
 * #56 — a real-component keyboard-operability test harness, not a reimplementation.
 *
 * Both `ConfirmDialog` and `CandidateCompareOverlay` are only ever reachable in the live app
 * behind real state that takes a full mission run (or a live Django backend) to reach: an
 * active mission for the confirm dialogs, two `VerificationRecord`s for the compare overlay.
 * This harness mounts the exact same component modules the production build ships, fed
 * deterministic mock data, purely so `scripts/verify-keyboard-operability.mjs` can drive them
 * with a real keyboard in a real browser without standing up the whole backend.
 *
 * Excluded from every real build the same way `PresentationMissionCommandCenter` is (#52,
 * D-058 §2.2): this file is never imported from `src/pages/`, so Astro's file-based router
 * never discovers it. `astro.config.mjs`'s `keyboardHarnessIntegration` only calls
 * `injectRoute` when `BD_KEYBOARD_HARNESS_BUILD=true` was set for that build/dev invocation —
 * a plain `npm run dev`/`npm run build` never sees this route at all. See
 * `scripts/check-keyboard-harness-exclusion.sh`.
 */

const mockFinding: MissionSnapshot['finding'] = {
  id: 'harness-finding-0001',
  mission_id: 'harness-mission-0001',
  category: 'HEAP_BUFFER_OVERFLOW',
  title: 'heap-buffer-overflow in parse_config',
  severity: 'HIGH',
  discovery_method: 'FUZZING_CAMPAIGN',
  fingerprint: 'harness-fp-0001',
  crash_count: 1,
  detected_at: '2026-08-24T12:00:00Z',
  reproducible: true,
  tool: 'ADDRESS_SANITIZER',
  location: { file_path: 'src/parse_config.c', line: 128, function: 'parse_config' },
};

const mockReproducer: MissionSnapshot['reproducer'] = {
  id: 'harness-repro-0001',
  finding_id: 'harness-finding-0001',
  created_at: '2026-08-24T12:01:00Z',
  minimized: true,
  replay_attempts: 5,
  replay_successes: 5,
  test_command: './harness @@',
  artifact: { kind: 'reproducer', uri: 'artifact://harness-mission-0001/reproducer/1', size_bytes: 128, sha256: null },
};

function mockGate(status: 'PASS' | 'FAIL' | 'NOT_RUN' | 'ERROR', detail: string): MissionSnapshot['verifications'][number]['gates'][keyof MissionSnapshot['verifications'][number]['gates']] {
  return {
    name: 'COMPILE',
    status,
    detail,
    evidence_source: status === 'NOT_RUN' ? 'REPLAYED_ARTIFACT' : 'TOOL_EXECUTION',
    evidence_ref: null,
    tool: status === 'NOT_RUN' ? null : 'ctest',
  } as never;
}

function mockCandidate(id: string, provenance: 'MODEL_GENERATED' | 'OPERATOR_SUPPLIED', policyStatus: 'ACCEPTED' | 'REJECTED_TOO_MANY_LINES'): MissionSnapshot['patchCandidates'][number] {
  return {
    id,
    mission_id: 'harness-mission-0001',
    finding_id: 'harness-finding-0001',
    created_at: '2026-08-24T12:02:00Z',
    diff: [
      '--- a/src/parse_config.c',
      '+++ b/src/parse_config.c',
      '@@ -120,7 +120,9 @@',
      ' int parse_config(const char *path) {',
      '-  char buf[16];',
      '+  char buf[64];',
      '   FILE *f = fopen(path, "r");',
      '+  if (!f) { return -1; }',
      '   while (fgets(buf, sizeof(buf), f)) {',
      '     process_line(buf);',
      '   }',
    ].join('\n'),
    files_changed: 1,
    lines_changed: policyStatus === 'ACCEPTED' ? 4 : 40,
    policy_status: policyStatus,
    policy_detail: policyStatus === 'ACCEPTED' ? '' : 'diff exceeds the 25-line policy limit',
    provenance,
    rationale: 'Widen the stack buffer and guard the fopen() failure path.',
    model: provenance === 'MODEL_GENERATED' ? { confidence: 0.74 } as never : null,
  };
}

const mockSnapshot: MissionSnapshot = {
  ...emptyMissionSnapshot,
  missionId: 'harness-mission-0001',
  state: 'VERIFY',
  stage: 'VERIFY',
  finding: mockFinding,
  reproducer: mockReproducer,
  patchCandidates: [
    mockCandidate('harness-candidate-0001', 'MODEL_GENERATED', 'ACCEPTED'),
    mockCandidate('harness-candidate-0002', 'OPERATOR_SUPPLIED', 'ACCEPTED'),
  ],
  verifications: [
    {
      id: 'harness-verification-0001',
      mission_id: 'harness-mission-0001',
      patch_id: 'harness-candidate-0001',
      started_at: '2026-08-24T12:03:00Z',
      finished_at: '2026-08-24T12:04:00Z',
      verdict: 'REJECTED',
      worktree_sha256: 'harness-sha-1',
      resource_usage: null,
      gates: {
        compile: mockGate('PASS', 'clean build'),
        reproducer_eliminated: mockGate('FAIL', 'reproducer still crashes'),
        regression_preserved: mockGate('PASS', 'ctest 42/42 passed'),
        static_delta: mockGate('PASS', 'no new findings'),
        renewed_fuzzing: mockGate('NOT_RUN', 'skipped after an earlier gate failed'),
      },
    } as never,
    {
      id: 'harness-verification-0002',
      mission_id: 'harness-mission-0001',
      patch_id: 'harness-candidate-0002',
      started_at: '2026-08-24T12:05:00Z',
      finished_at: '2026-08-24T12:06:00Z',
      verdict: 'VERIFIED',
      worktree_sha256: 'harness-sha-2',
      resource_usage: null,
      gates: {
        compile: mockGate('PASS', 'clean build'),
        reproducer_eliminated: mockGate('PASS', 'reproducer no longer crashes, 5/5 replays'),
        regression_preserved: mockGate('PASS', 'ctest 42/42 passed'),
        static_delta: mockGate('PASS', 'no new findings'),
        renewed_fuzzing: mockGate('PASS', '10-minute renewed campaign, 0 new crashes'),
      },
    } as never,
  ],
};

export function KeyboardHarness() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  // Mirrors `MissionCommandCenter.openCompare` exactly (D-059 §3.4): capture whatever had focus
  // at the moment the trigger was activated, in the click handler itself — never during render
  // — so `CandidateCompareOverlay`'s own cleanup can restore it for real on close.
  const compareReturnFocus = useRef<HTMLElement | null>(null);

  function openCompare(): void {
    compareReturnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setCompareOpen(true);
  }

  return (
    <div className="bd-app" style={{ padding: '2rem', display: 'grid', gap: '1rem' }}>
      <h1 style={{ font: 'inherit' }}>[ #56 KEYBOARD HARNESS — NOT A REAL SCREEN ]</h1>
      <p>Mounts the real `ConfirmDialog` and `CandidateCompareOverlay` components with deterministic mock data for keyboard-trap verification.</p>

      <button type="button" className="bd-bracket-control bd-bracket-control--critical" onClick={() => setConfirmOpen(true)}>
        [ OPEN CONFIRM DIALOG ]
      </button>
      <button type="button" className="bd-bracket-control" onClick={openCompare}>
        [ OPEN CANDIDATE COMPARE ]
      </button>

      {confirmOpen && (
        <ConfirmDialog
          title="Cancel mission harness-mission-0001."
          consequence="The sandbox is destroyed and any unexported evidence is lost. This cannot be undone."
          confirmLabel="CANCEL MISSION"
          destructive
          onConfirm={() => setConfirmOpen(false)}
          onCancel={() => setConfirmOpen(false)}
        />
      )}

      <CandidateCompareOverlay
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        snapshot={mockSnapshot}
        returnFocusRef={compareReturnFocus}
      />
    </div>
  );
}
