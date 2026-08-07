import { useEffect, useState } from 'react';

import { getSystemHealth, type SystemHealth } from '../lib/api/client';

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
            message: error instanceof Error ? error.message : 'The control API request failed.',
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
        <div><dt>STATUS</dt><dd>{health.status}</dd></div>
        <div><dt>SERVICE</dt><dd>{health.service}</dd></div>
        <div><dt>VERSION</dt><dd>{health.version}</dd></div>
        <div><dt>TRACE</dt><dd>{health.trace_id}</dd></div>
      </dl>
    </div>
  );
}
