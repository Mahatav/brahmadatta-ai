import { useStore } from '@nanostores/react';

import { $streamState } from '../lib/events/store';

export function LiveEventStatus() {
  const streamState = useStore($streamState);
  const failed = streamState === 'error';

  return (
    <p className={failed ? 'status status--error' : 'status status--idle'}>
      [ {failed ? '×' : '·'} SHARED STREAM · {streamState.toUpperCase()} ]
    </p>
  );
}
