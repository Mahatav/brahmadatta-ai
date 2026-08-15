#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '../..');
const evidenceDir = path.join(repoRoot, '.project/evidence');
const stamp = '2026-08-15';
const jsonPath = path.join(evidenceDir, `d9-finale-closure-readiness-${stamp}.json`);
const mdPath = path.join(evidenceDir, `d9-finale-closure-readiness-${stamp}.md`);

const rel = (target) => path.relative(repoRoot, target);
const check = (id, description, status, detail, evidence = []) => ({
  id,
  description,
  status,
  detail,
  evidence,
});

const run = (command, args, options = {}) => {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    text: true,
    encoding: 'utf8',
    timeout: options.timeout ?? 120_000,
  });
  return {
    command: [command, ...args].join(' '),
    status: result.status,
    signal: result.signal,
    stdout: (result.stdout ?? '').trim().slice(-4000),
    stderr: (result.stderr ?? '').trim().slice(-4000),
    timedOut: Boolean(result.error && result.error.code === 'ETIMEDOUT'),
    missing: Boolean(result.error && result.error.code === 'ENOENT'),
  };
};

const hashFile = (filePath) =>
  createHash('sha256').update(readFileSync(filePath)).digest('hex');

const checks = [];
const commands = [];

const envPath = path.join(repoRoot, '.env');
if (!existsSync(envPath)) {
  checks.push(check('env', 'Finale .env exists with host-local secrets', 'blocked', '.env is missing; finale-up.sh correctly refuses to boot without it.'));
} else {
  const envText = readFileSync(envPath, 'utf8');
  const mode = (statSync(envPath).mode & 0o777).toString(8);
  checks.push(check(
    'env',
    'Finale .env exists with host-local secrets',
    envText.includes('REPLACE_ME') ? 'fail' : 'pass',
    `.env present, mode ${mode}${envText.includes('REPLACE_ME') ? ', but contains REPLACE_ME placeholders' : ''}.`,
  ));
}

const distPath = path.join(repoRoot, 'apps/command-center/dist');
checks.push(check(
  'command-center-dist',
  'Command Center production build output exists',
  existsSync(distPath) ? 'pass' : 'blocked',
  existsSync(distPath) ? 'apps/command-center/dist exists.' : 'apps/command-center/dist is missing; run npm run build in apps/command-center.',
));

const fallbackPath = path.join(repoRoot, '.project/evidence/fallback-demo-d6.html');
const fallbackManifestPath = path.join(repoRoot, '.project/evidence/fallback-demo-d6-manifest.json');
if (existsSync(fallbackPath) && existsSync(fallbackManifestPath)) {
  const manifest = JSON.parse(readFileSync(fallbackManifestPath, 'utf8'));
  const sha = hashFile(fallbackPath);
  const manifestSha = manifest.artifact?.sha256;
  checks.push(check(
    'fallback-recording',
    'Fallback recording exists as a complete playable local file',
    manifest.artifact?.playable_offline === true && sha === manifestSha ? 'pass' : 'fail',
    `fallback-demo-d6.html sha256=${sha}; manifest playable_offline=${manifest.artifact?.playable_offline}.`,
    [rel(fallbackPath), rel(fallbackManifestPath)],
  ));
} else {
  checks.push(check('fallback-recording', 'Fallback recording exists as a complete playable local file', 'fail', 'Fallback HTML or manifest is missing.'));
}

commands.push(run('docker', ['info'], { timeout: 30_000 }));
const dockerAvailable = commands.at(-1).status === 0;
checks.push(check(
  'docker',
  'Docker daemon is reachable for finale rehearsal',
  dockerAvailable ? 'pass' : 'blocked',
  dockerAvailable ? 'docker info succeeded.' : 'docker info failed; finale stack and zero-stray checks cannot run on this host session.',
));

commands.push(run('node', ['--version'], { timeout: 10_000 }));
checks.push(check(
  'node',
  'Node runtime exists for Command Center checks',
  commands.at(-1).status === 0 ? 'pass' : 'fail',
  commands.at(-1).status === 0 ? `node ${commands.at(-1).stdout}` : commands.at(-1).stderr || 'node unavailable',
));

if (dockerAvailable) {
  commands.push(run('infrastructure/scripts/nginx-validate.sh', ['finale']));
  checks.push(check(
    'nginx-static',
    'Finale nginx profile validates statically',
    commands.at(-1).status === 0 ? 'pass' : 'fail',
    commands.at(-1).status === 0 ? 'nginx-validate.sh finale passed.' : commands.at(-1).stderr || commands.at(-1).stdout,
  ));
} else {
  checks.push(check('nginx-static', 'Finale nginx profile validates statically', 'blocked', 'Skipped because nginx validation runs in Docker and Docker is unavailable.'));
}

if (existsSync(envPath)) {
  commands.push(run('docker', ['compose', '--env-file', envPath, '-f', 'infrastructure/compose/docker-compose.finale.yml', 'config', '--quiet']));
  checks.push(check(
    'compose-config',
    'Finale compose config validates with the host .env',
    commands.at(-1).status === 0 ? 'pass' : 'fail',
    commands.at(-1).status === 0 ? 'docker compose config --quiet passed.' : commands.at(-1).stderr || commands.at(-1).stdout,
  ));
} else {
  checks.push(check('compose-config', 'Finale compose config validates with the host .env', 'blocked', 'Skipped because .env is missing.'));
}

if (dockerAvailable) {
  commands.push(run('docker', ['ps', '-a', '--format', '{{.Names}} {{.Status}}']));
  checks.push(check(
    'docker-strays',
    'Docker container list captured for stray-process review',
    commands.at(-1).status === 0 ? 'pass' : 'fail',
    commands.at(-1).stdout || 'docker ps -a returned no containers.',
  ));
} else {
  checks.push(check('docker-strays', 'Docker container list captured for stray-process review', 'blocked', 'Skipped because Docker is unavailable.'));
}

const blocked = checks.filter((row) => row.status === 'blocked');
const failed = checks.filter((row) => row.status === 'fail');
const pass = failed.length === 0 && blocked.length === 0;
const record = {
  kind: 'finale-closure-readiness',
  schema_version: 'finale-closure-readiness/1',
  generated_at: new Date().toISOString(),
  issues: [50, 57, 59, 60],
  status: pass ? 'pass' : failed.length > 0 ? 'fail' : 'blocked',
  summary: pass
    ? 'Finale closure preflight has no blockers in this run.'
    : 'Finale closure is not claimable yet; blocked or failed checks remain.',
  checks,
  commands,
  closeability: {
    issue_50: pass ? 'ready-to-run-live-demo' : 'blocked until finale-up and nine-step run execute successfully',
    issue_57: 'blocked until at least three full timed rehearsals run after issue #50 passes',
    issue_59: 'blocked on CEO decision for physical roster and registration/travel constraints',
    issue_60: 'blocked until issue #57 passes, release tag is cut, rollback is tested, and branch protection is tightened',
  },
};

writeFileSync(jsonPath, `${JSON.stringify(record, null, 2)}\n`);

const rows = checks.map((row) => `| ${row.id} | ${row.status} | ${row.detail.replace(/\|/g, '\\|')} |`).join('\n');
writeFileSync(mdPath, `# D9 Finale Closure Readiness

Status: **${record.status}**

${record.summary}

| Check | Status | Detail |
|---|---|---|
${rows}

## Closeability

- #50: ${record.closeability.issue_50}
- #57: ${record.closeability.issue_57}
- #59: ${record.closeability.issue_59}
- #60: ${record.closeability.issue_60}

Full command output is recorded in \`${rel(jsonPath)}\`.
`);

console.log(`${record.status}: wrote ${rel(jsonPath)} and ${rel(mdPath)}`);
process.exit(record.status === 'fail' ? 1 : 0);
