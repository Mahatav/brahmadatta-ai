import path from 'node:path';

const baseUrl = process.env.COMMAND_CENTER_URL ?? 'http://127.0.0.1:4321';
const repositoryPath = process.env.COMMAND_CENTER_REPO_PATH ?? path.resolve(process.cwd(), '../..');

async function main() {
  const page = await fetchText('/');
  assert(page.includes('Command Center'), 'home page did not render Command Center');
  assert(page.includes('[ DEV PATH SCAN ]'), 'home page did not render local path scan action');
  assert(page.includes('[ BROWSER FOLDER FALLBACK ]'), 'home page did not render browser folder fallback');
  assert(page.includes('data-folder-picker="directory"'), 'browser fallback marker is missing');
  assert(page.includes('[ LOCAL AI CORE ]'), 'home page did not render the local AI core');
  assert(page.includes('[ SITUATION ]'), 'home page did not render the situation panel');
  assert(page.includes('[ NO AUTOMATED ACTION RUNNING ]'), 'home page did not render automation progress state');
  assert(!page.includes('[ ASK NEXT ]'), 'home page still renders the prompt suggestion panel');
  assert(!page.includes('[ SIX-STAGE TIMELINE ]'), 'home page still renders the old mission timeline');
  for (const label of ['Authorize', 'Ingest', 'Baseline', 'Analyze', 'Stress', 'Correlate', 'Patch', 'Verify', 'Export']) {
    assert(page.includes(label), `home page did not render mission progress stage: ${label}`);
  }

  const defaultPath = await fetchJson('/__local/repository-default');
  assert(typeof defaultPath.path === 'string' && defaultPath.path.length > 0, 'default repository path missing');

  const scan = await fetchJson('/__local/repository-scan', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path: repositoryPath }),
  });
  assert(scan.name === path.basename(repositoryPath), 'scan returned unexpected repository name');
  assert(Number.isInteger(scan.fileCount) && scan.fileCount > 0, 'scan did not count repository files');
  assert(Array.isArray(scan.manifestLines) && scan.manifestLines.length > 0, 'scan did not produce a manifest');
  assert(typeof scan.primaryStack === 'string' && scan.primaryStack.length > 0, 'scan did not detect stack state');

  const rejected = await fetch(`${baseUrl}/__local/repository-scan`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path: '' }),
  });
  assert(rejected.status === 400, 'empty path should be rejected');

  console.warn(
    `local smoke ok: ${scan.name}, ${scan.fileCount} files, ${formatBytes(scan.totalBytes)}, ${scan.primaryStack}`,
  );
}

async function fetchText(route) {
  const response = await fetch(`${baseUrl}${route}`);
  assert(response.ok, `${route} returned ${response.status}`);
  return response.text();
}

async function fetchJson(route, options) {
  const response = await fetch(`${baseUrl}${route}`, options);
  const body = await response.json();
  assert(response.ok, `${route} returned ${response.status}: ${JSON.stringify(body)}`);
  return body;
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function formatBytes(value) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${Math.round(value / 1024)} KiB`;
  }
  return `${Math.round(value / (1024 * 1024))} MiB`;
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
