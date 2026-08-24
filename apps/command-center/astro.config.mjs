import react from '@astrojs/react';
import { defineConfig } from 'astro/config';
import { readdir, stat } from 'node:fs/promises';
import path from 'node:path';

const ignoredDirectories = new Set([
  '.git',
  '.astro',
  '.next',
  '.pytest_cache',
  '.venv',
  '__pycache__',
  'build',
  'dist',
  'node_modules',
  'target',
  'venv',
]);

const stackMarkers = {
  'CMakeLists.txt': 'C/C++ CMake',
  'Makefile': 'C/C++ Make',
  'package.json': 'Node/TypeScript',
  'pyproject.toml': 'Python',
  'requirements.txt': 'Python',
  'Cargo.toml': 'Rust',
  'go.mod': 'Go',
};

const repositoryRoot = path.resolve(process.cwd(), '../..');
const ollamaEndpoint = process.env.OLLAMA_ENDPOINT || 'http://127.0.0.1:11434/api';
const codellamaModel = process.env.CODELLAMA_MODEL || 'codellama:7b-instruct';

// #52 / D-058 §2.2 — "a build-time flag, not a runtime toggle... read once, at Astro build
// time." `process.env`, not `import.meta.env`: this has to be evaluated here, in Node, while
// `astro.config.mjs` itself decides what to build, not inside client code that could read a
// flag at runtime. Defaults unset/false, per D-049's standing rule that a default points at the
// humbler claim — plain `npm run build`/`npm run dev` never sees this branch taken at all.
const presentationBuild = process.env.BD_PRESENTATION_BUILD === 'true';
const fixtureReplayUrl = process.env.BD_PRESENTATION_FIXTURE_URL || 'http://127.0.0.1:8971';

export default defineConfig({
  integrations: [react(), presentationBuild ? presentationModeIntegration() : undefined].filter(Boolean),
  output: 'static',
  vite: {
    plugins: [localRepositoryPlugin()],
    // Dev/preview convenience only — irrelevant to the finale/production artifact, which never
    // runs `astro dev`/`astro preview` and gets its `/api/v1` routing from nginx instead
    // (`infrastructure/compose/nginx/templates.*`). Only ever configured when
    // `BD_PRESENTATION_BUILD=true`, so an ordinary `npm run dev` against the real control API
    // is completely unaffected.
    ...(presentationBuild
      ? {
          server: { proxy: { '/api/v1': { target: fixtureReplayUrl, changeOrigin: true } } },
          preview: { proxy: { '/api/v1': { target: fixtureReplayUrl, changeOrigin: true } } },
        }
      : {}),
  },
});

/**
 * #52 / D-058 §2.2 — the build-time exclusion mechanism. `src/presentation/presentation.astro`
 * lives outside `src/pages/`, so Astro's file-based router never discovers it on its own; this
 * integration is the ONLY thing that ever turns it into a real route, and it only runs at all
 * when `presentationBuild` is true. A plain `npm run build`/`npm run dev` never calls
 * `injectRoute`, so the finale/production artifact contains no HTML, no JS chunk, and no route
 * table entry for `/presentation` — not "present but disabled," genuinely absent, which is what
 * #52's acceptance criterion 1 (grep the built bundle) checks for. See
 * `scripts/check-presentation-build-exclusion.sh`.
 */
function presentationModeIntegration() {
  return {
    name: 'brahmadatta-presentation-mode',
    hooks: {
      'astro:config:setup': ({ injectRoute, logger }) => {
        injectRoute({
          pattern: '/presentation',
          entrypoint: './src/presentation/presentation.astro',
        });
        logger.warn(
          'BD_PRESENTATION_BUILD=true — this build includes the rehearsal-only presentation-mode ' +
            'route (/presentation). Never build the finale/production artifact this way ' +
            '(docs/09-company/10-fallback-ladder.md §2.5, D-058).',
        );
      },
    },
  };
}

function localRepositoryPlugin() {
  return {
    name: 'brahmadatta-local-repository-api',
    configureServer(server) {
      server.middlewares.use('/__local/repository-default', (_request, response) => {
        sendJson(response, 200, { path: repositoryRoot });
      });

      server.middlewares.use('/__local/model-gateway-status', async (_request, response) => {
        const status = await readOllamaStatus();
        sendJson(response, 200, status);
      });

      server.middlewares.use('/__local/repository-scan', async (request, response) => {
        if (request.method !== 'POST') {
          sendJson(response, 405, { error: 'method_not_allowed' });
          return;
        }

        try {
          const body = await readJsonBody(request);
          const requestedPath = typeof body.path === 'string' ? body.path.trim() : '';
          if (!requestedPath) {
            sendJson(response, 400, { error: 'path_required' });
            return;
          }

          const rootPath = path.resolve(requestedPath);
          const rootStats = await stat(rootPath);
          if (!rootStats.isDirectory()) {
            sendJson(response, 400, { error: 'path_not_directory' });
            return;
          }

          const scan = await scanDirectory(rootPath);
          sendJson(response, 200, {
            name: path.basename(rootPath),
            path: rootPath,
            ...scan,
          });
        } catch (error) {
          sendJson(response, 400, {
            error: 'scan_failed',
            message: error instanceof Error ? error.message : 'Unable to scan local path.',
          });
        }
      });
    },
  };
}

async function readOllamaStatus() {
  const started = performance.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1200);
  try {
    const result = await fetch(`${ollamaEndpoint.replace(/\/$/, '')}/tags`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
    const latencyMs = Math.max(0, Math.round(performance.now() - started));
    if (!result.ok) {
      return {
        backend: 'ollama',
        status: 'unreachable',
        endpoint: ollamaEndpoint,
        model: codellamaModel,
        modelPresent: false,
        latencyMs,
        message: `Ollama returned HTTP ${result.status}.`,
      };
    }
    const body = await result.json();
    const models = Array.isArray(body.models)
      ? body.models
        .map((model) => (typeof model?.name === 'string' ? model.name : ''))
        .filter(Boolean)
      : [];
    const modelPresent = models.includes(codellamaModel);
    return {
      backend: 'ollama',
      status: modelPresent ? 'ready' : 'missing-model',
      endpoint: ollamaEndpoint,
      model: codellamaModel,
      modelPresent,
      models,
      latencyMs,
      message: modelPresent
        ? 'Ollama is serving CodeLlama locally.'
        : `Ollama is reachable, but ${codellamaModel} is not pulled locally.`,
    };
  } catch (error) {
    return {
      backend: 'ollama',
      status: 'unreachable',
      endpoint: ollamaEndpoint,
      model: codellamaModel,
      modelPresent: false,
      models: [],
      latencyMs: Math.max(0, Math.round(performance.now() - started)),
      message: error instanceof Error ? error.message : 'Ollama is not reachable.',
    };
  } finally {
    clearTimeout(timeout);
  }
}

function sendJson(response, statusCode, body) {
  response.statusCode = statusCode;
  response.setHeader('content-type', 'application/json');
  response.end(JSON.stringify(body));
}

async function readJsonBody(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

async function scanDirectory(rootPath) {
  const result = {
    fileCount: 0,
    totalBytes: 0,
    detectedFiles: [],
    manifestLines: [],
  };
  await scanDirectoryEntries(rootPath, '', result, 0);
  result.detectedFiles.sort();
  result.manifestLines.sort();
  return {
    fileCount: result.fileCount,
    totalBytes: result.totalBytes,
    detectedFiles: result.detectedFiles,
    manifestLines: result.manifestLines,
    primaryStack: detectStack(result.detectedFiles),
  };
}

async function scanDirectoryEntries(rootPath, prefix, result, depth) {
  if (depth > 6 || result.fileCount >= 5000) {
    return;
  }

  const entries = await readdir(path.join(rootPath, prefix), { withFileTypes: true });
  for (const entry of entries) {
    const relativePath = path.join(prefix, entry.name);
    if (entry.isDirectory()) {
      if (!ignoredDirectories.has(entry.name)) {
        await scanDirectoryEntries(rootPath, `${relativePath}/`, result, depth + 1);
      }
      continue;
    }
    if (!entry.isFile()) {
      continue;
    }

    const fileStats = await stat(path.join(rootPath, relativePath));
    const manifestPath = relativePath.split(path.sep).join('/');
    result.fileCount += 1;
    result.totalBytes += fileStats.size;
    result.manifestLines.push(`${manifestPath}:${fileStats.size}:${fileStats.mtimeMs}`);
    if (isStackMarker(manifestPath)) {
      result.detectedFiles.push(manifestPath);
    }
    if (result.fileCount >= 5000) {
      return;
    }
  }
}

function isStackMarker(filePath) {
  const basename = filePath.split('/').at(-1) ?? filePath;
  return basename in stackMarkers || filePath === 'src/main.rs' || filePath.endsWith('.c') || filePath.endsWith('.cpp');
}

function detectStack(detectedFiles) {
  for (const file of detectedFiles) {
    const basename = file.split('/').at(-1) ?? file;
    const stack = stackMarkers[basename];
    if (stack) {
      return stack;
    }
  }
  if (detectedFiles.some((file) => file.endsWith('.c') || file.endsWith('.cpp'))) {
    return 'C/C++ source';
  }
  return detectedFiles.length > 0 ? 'mixed local code' : 'unknown';
}
