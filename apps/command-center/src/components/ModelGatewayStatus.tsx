import { useEffect, useState } from 'react';

import { getModelGatewayStatus, type ModelGatewayStatus as ModelGatewayStatusPayload } from '../lib/api/client';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

type RequestState =
  | { kind: 'loading' }
  | { kind: 'success'; status: ModelGatewayStatusPayload }
  | { kind: 'error'; message: string };

export function ModelGatewayStatus() {
  const [state, setState] = useState<RequestState>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    getModelGatewayStatus(controller.signal).then(
      (status) => setState({ kind: 'success', status }),
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            kind: 'error',
            message: sanitizeDisplayText(
              error instanceof Error ? error.message : 'The local model bridge failed.',
              { fallback: 'The local model bridge failed.', maxLength: 220 },
            ),
          });
        }
      },
    );
    return () => controller.abort();
  }, []);

  if (state.kind === 'loading') {
    return <p className="status status--idle">[ · D5 MODEL · CHECKING ]</p>;
  }

  if (state.kind === 'error') {
    return <p className="status status--error" role="alert">[ × D5 MODEL · UNKNOWN ] {state.message}</p>;
  }

  const { status } = state;
  const ready = status.status === 'ready';
  const warning = status.status === 'missing-model';
  const className = ready ? 'status--verified' : warning ? 'status--warning' : 'status--error';
  const glyph = ready ? '+' : warning ? '!' : '×';
  const label = ready ? 'CONNECTED' : warning ? 'MODEL MISSING' : 'UNREACHABLE';

  return (
    <div className="health-result model-gateway-result">
      <p className={`status ${className}`}>
        [ {glyph} D5 MODEL · {label} ]
      </p>
      <dl>
        <div><dt>BACKEND</dt><dd>{sanitizeDisplayText(status.backend, { fallback: 'unknown', maxLength: 80 })}</dd></div>
        <div><dt>MODEL</dt><dd>{sanitizeDisplayText(status.model, { fallback: 'unknown', maxLength: 120 })}</dd></div>
        <div><dt>ENDPOINT</dt><dd>{sanitizeDisplayText(status.endpoint, { fallback: 'unknown', maxLength: 180 })}</dd></div>
        <div><dt>LATENCY</dt><dd>{status.latencyMs} ms</dd></div>
        <div><dt>STATE</dt><dd>{sanitizeDisplayText(status.message, { fallback: 'unknown', maxLength: 240 })}</dd></div>
      </dl>
    </div>
  );
}
