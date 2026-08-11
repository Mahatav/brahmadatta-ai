import { useStore } from '@nanostores/react';

import { $missionSnapshot, $streamState } from '../lib/events/store';

export function LiveEventStatus() {
  const snapshot = useStore($missionSnapshot);
  const streamState = useStore($streamState);
  const failed = streamState === 'error';
  const label = snapshot.missionId ? `SHARED STREAM · ${streamState.toUpperCase()}` : 'MISSION STREAM · NO MISSION SELECTED';

  return (
    <p className={failed ? 'status status--error' : 'status status--idle'}>
      [ {failed ? '×' : '·'} {label} ]
    </p>
  );
}
