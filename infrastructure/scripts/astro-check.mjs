#!/usr/bin/env node
// Run `astro check` against apps/command-center, if there is one.
//
// `astro check` cannot be run from the repository root: it needs the Astro toolchain and
// tsconfig from inside the app, and it is a dependency of the app, not of the root
// tooling. Hence this small shim, so `npm run typecheck` and the CI job have one command
// that behaves sensibly both before and after the app exists.
//
// It reports SKIPPED (exit 0) when apps/command-center is missing, and it says so loudly.
// A silent skip that later hides a real failure is worse than no check at all — so once
// the app exists, a missing `check` script is a HARD FAILURE, not another skip.

import { existsSync, readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const appDir = join(repoRoot, 'apps', 'command-center');
const pkgPath = join(appDir, 'package.json');

if (!existsSync(pkgPath)) {
  console.log('astro check: SKIPPED — apps/command-center/package.json does not exist yet.');
  console.log('             This stops being a skip the moment the Astro app lands.');
  process.exit(0);
}

const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
if (!pkg.scripts || !pkg.scripts.check) {
  console.error('astro check: FAILED — apps/command-center exists but has no "check" script.');
  console.error('             Add:  "check": "astro check"   to its package.json.');
  process.exit(1);
}

if (!existsSync(join(appDir, 'node_modules'))) {
  console.log('astro check: installing apps/command-center dependencies (npm ci)');
  const install = spawnSync('npm', ['ci', '--no-audit', '--no-fund'], {
    cwd: appDir,
    stdio: 'inherit',
  });
  if (install.status !== 0) process.exit(install.status ?? 1);
}

const result = spawnSync('npm', ['run', 'check'], { cwd: appDir, stdio: 'inherit' });
process.exit(result.status ?? 1);
