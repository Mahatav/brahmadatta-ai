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

export default defineConfig({
  integrations: [react()],
  output: 'static',
  vite: {
    plugins: [localRepositoryPlugin()],
  },
});

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
