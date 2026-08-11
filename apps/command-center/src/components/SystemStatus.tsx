import { useEffect, useState } from 'react';

import { getSystemHealth, type SystemHealth } from '../lib/api/client';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

type RequestState =
  | { kind: 'loading' }
  | { kind: 'success'; health: SystemHealth }
  | { kind: 'error'; message: string };

export function SystemStatus() {
  const [state, setState] = useState<RequestState>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    getSystemHealth(controller.signal).then(
      (health) => setState({ kind: 'success', health }),
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            kind: 'error',
            message: sanitizeDisplayText(
              error instanceof Error ? error.message : 'The control API request failed.',
              { fallback: 'The control API request failed.', maxLength: 220 },
            ),
          });
        }
      },
    );
    return () => controller.abort();
  }, []);

  if (state.kind === 'loading') {
    return <p className="status status--idle">[ · CONTROL API · CONNECTING ]</p>;
  }

  if (state.kind === 'error') {
    return <p className="status status--error" role="alert">[ × CONTROL API · UNREACHABLE ] {state.message}</p>;
  }

  const { health } = state;
  const connected = health.status === 'ok';
  return (
    <div className="health-result">
      <p className={`status ${connected ? 'status--verified' : 'status--warning'}`}>
        [ {connected ? '+' : '!'} CONTROL API · {connected ? 'CONNECTED' : 'DEGRADED'} ]
      </p>
      <dl>
        <div><dt>STATUS</dt><dd>{sanitizeDisplayText(health.status, { fallback: 'unknown', maxLength: 80 })}</dd></div>
        <div><dt>SERVICE</dt><dd>{sanitizeDisplayText(health.service, { fallback: 'unknown', maxLength: 120 })}</dd></div>
        <div><dt>VERSION</dt><dd>{sanitizeDisplayText(health.version, { fallback: 'unknown', maxLength: 80 })}</dd></div>
        <div><dt>TRACE</dt><dd>{sanitizeDisplayText(health.trace_id, { fallback: 'unknown', maxLength: 120 })}</dd></div>
      </dl>
    </div>
  );
}
