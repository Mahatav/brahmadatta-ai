import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const temporaryDirectory = mkdtempSync(join(tmpdir(), 'brahmadatta-openapi-'));
const generatedPath = join(temporaryDirectory, 'schema.d.ts');
const committedPath = new URL('../src/lib/api/schema.d.ts', import.meta.url);

try {
  const result = spawnSync(
    process.platform === 'win32' ? 'openapi-typescript.cmd' : 'openapi-typescript',
    ['../../packages/schemas/openapi.json', '-o', generatedPath],
    { cwd: new URL('..', import.meta.url), encoding: 'utf8' },
  );

  if (result.status !== 0) {
    process.stderr.write(result.stderr ?? result.error?.message ?? 'openapi-typescript failed.\n');
    process.exit(result.status ?? 1);
  }

  if (readFileSync(generatedPath, 'utf8') !== readFileSync(committedPath, 'utf8')) {
    console.error('Generated API types are stale. Run npm run generate:api.');
    process.exit(1);
  }

  process.stdout.write('Generated API types match packages/schemas/openapi.json.\n');
} finally {
  rmSync(temporaryDirectory, { recursive: true, force: true });
}
