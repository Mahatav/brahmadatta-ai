import type { paths } from './schema';

export type SystemHealth = paths['/api/v1/system/health']['get']['responses'][200]['content']['application/json'];

export async function getSystemHealth(signal?: AbortSignal): Promise<SystemHealth> {
  const response = await fetch('/api/v1/system/health', {
    headers: { Accept: 'application/json' },
    ...(signal ? { signal } : {}),
  });

  if (!response.ok) {
    throw new Error(`Control API returned HTTP ${response.status}.`);
  }

  return (await response.json()) as SystemHealth;
}
