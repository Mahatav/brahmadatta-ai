import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import {
  sanitizeDisplayList,
  sanitizeDisplayText,
  sanitizeJsonReportValue,
  sanitizeMarkdownText,
  TRUNCATED_MARKER,
} from '../src/lib/security/renderSafety.mjs';

const appRoot = path.resolve(import.meta.dirname, '..');
const sourceRoot = path.join(appRoot, 'src');
const finaleCspPath = path.resolve(appRoot, '../../infrastructure/compose/nginx/includes/csp-finale.conf');
const forbiddenRawHtmlTokens = ['set:html', 'innerHTML', 'dangerouslySetInnerHTML'];

async function main() {
  assertHostileFixturesAreInert();
  await assertNoRawHtmlRendering();
  await assertFinaleCspBlocksInlineScripts();
  console.warn('render safety ok: hostile strings inert, raw HTML absent, finale CSP script-src strict');
}

function assertHostileFixturesAreInert() {
  const hostile = [
    'src/<img src=x onerror=alert(1)>.c',
    'commit `fix` <script>alert(1)</script>',
    'compiler \u001B[31merror\u001B[0m: bad.c:1',
    'rtl-safe abc\u202Egnp.exe',
    `long-${'x'.repeat(5000)}`,
    'null\u0000byte\tand\ncontrol',
  ].join(' | ');

  const display = sanitizeDisplayText(hostile, { maxLength: 160 });
  assert(!display.includes('\u001B'), 'display text kept an ANSI escape');
  assert(!display.includes('\u202E'), 'display text kept an RTL override');
  assert(!display.includes('\u0000'), 'display text kept a control character');
  assert(display.includes(TRUNCATED_MARKER), 'display text did not mark truncation');
  assert(display.length <= 160, 'display text exceeded its max length');

  const report = sanitizeJsonReportValue(hostile);
  assert(!report.includes('\u001B'), 'JSON report text kept an ANSI escape');
  assert(!report.includes('\u202E'), 'JSON report text kept an RTL override');
  assert(report.length <= 4000, 'JSON report text exceeded its max length');

  const markdown = sanitizeMarkdownText(hostile);
  assert(!markdown.includes('<script>'), 'Markdown report left raw script markup');
  assert(markdown.includes('&lt;script&gt;'), 'Markdown report did not escape markup');

  const list = sanitizeDisplayList(['<b>one</b>', '\u001B[32mtwo', 'three'], { maxItems: 2, maxLength: 32 });
  assert(list.length === 2, 'display list did not apply maxItems');
  assert(!list[1].includes('\u001B'), 'display list kept an ANSI escape');
}

async function assertNoRawHtmlRendering() {
  const files = await listFiles(sourceRoot);
  const checkedExtensions = new Set(['.astro', '.mjs', '.ts', '.tsx']);
  for (const file of files) {
    if (!checkedExtensions.has(path.extname(file))) {
      continue;
    }
    const source = await readFile(file, 'utf8');
    for (const token of forbiddenRawHtmlTokens) {
      assert(!source.includes(token), `${path.relative(appRoot, file)} contains forbidden raw HTML token ${token}`);
    }
  }
}

async function assertFinaleCspBlocksInlineScripts() {
  const source = await readFile(finaleCspPath, 'utf8');
  const uncommented = source
    .split('\n')
    .filter((line) => !line.trimStart().startsWith('#'))
    .join('\n');
  const scriptDirective = uncommented.match(/script-src[^;"]*/)?.[0] ?? '';
  assert(scriptDirective, 'finale CSP does not define script-src');
  assert(!scriptDirective.includes("'unsafe-inline'"), 'finale CSP allows unsafe-inline scripts');
  assert(!scriptDirective.includes("'unsafe-eval'"), 'finale CSP allows unsafe-eval scripts');
  assert(scriptDirective.includes("'self'"), 'finale CSP script-src is not same-origin anchored');
}

async function listFiles(root) {
  const entries = await readdir(root, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const absolute = path.join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...await listFiles(absolute));
      continue;
    }
    if (entry.isFile()) {
      files.push(absolute);
    }
  }
  return files;
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
