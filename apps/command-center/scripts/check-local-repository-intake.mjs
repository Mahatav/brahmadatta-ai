import { readFile } from 'node:fs/promises';
import path from 'node:path';

const appRoot = path.resolve(import.meta.dirname, '..');
const intakePath = path.join(appRoot, 'src/components/LocalRepositoryIntake.tsx');

async function main() {
  const source = await readFile(intakePath, 'utf8');
  const handler = bodyOfFunction(source, 'chooseRepositoryFromFiles');

  assert(source.includes('[ CHOOSE BROWSER FOLDER ]'), 'folder chooser action is missing');
  assert(!source.includes('[ BROWSER FOLDER FALLBACK ]'), 'dead browser folder fallback action returned');
  assert(source.includes('data-folder-picker="directory"'), 'folder input marker is missing');
  assert(source.includes('webkitdirectory'), 'folder input must keep the Chrome directory marker');
  assert(source.includes('directory'), 'folder input must keep a generic directory marker');
  assert(handler.includes('const input = event.currentTarget;'), 'folder handler must capture the input synchronously');
  assert(!handler.includes('event.currentTarget.value'), 'folder handler must not clear React event currentTarget after async work');
  assert(handler.includes('file.webkitRelativePath'), 'folder handler must reject plain file-only selections');

  console.warn('local repository intake ok: real folder chooser, no dead fallback, stable async input handling');
}

function bodyOfFunction(source, name) {
  const start = source.indexOf(`function ${name}`);
  assert(start >= 0, `${name} is missing`);
  const firstBrace = source.indexOf('{', start);
  assert(firstBrace >= 0, `${name} has no body`);
  let depth = 0;
  for (let index = firstBrace; index < source.length; index += 1) {
    const char = source[index];
    if (char === '{') {
      depth += 1;
    }
    if (char === '}') {
      depth -= 1;
      if (depth === 0) {
        return source.slice(firstBrace + 1, index);
      }
    }
  }
  throw new Error(`${name} body was not closed`);
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
