import { useStore } from '@nanostores/react';
import { useEffect, useRef, useState } from 'react';

import {
  $localRepository,
  setLocalRepositoryContext,
  type LocalRepositoryContext,
} from '../lib/events/store';
import type { ChangeEvent } from 'react';

interface ScanResult {
  fileCount: number;
  totalBytes: number;
  detectedFiles: string[];
  manifestLines: string[];
}

interface LocalPathScanResponse extends ScanResult {
  name: string;
  path: string;
  primaryStack: string;
}

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

const stackMarkers: Record<string, string> = {
  'CMakeLists.txt': 'C/C++ CMake',
  'Makefile': 'C/C++ Make',
  'package.json': 'Node/TypeScript',
  'pyproject.toml': 'Python',
  'requirements.txt': 'Python',
  'Cargo.toml': 'Rust',
  'go.mod': 'Go',
};

export function LocalRepositoryIntake() {
  const localRepository = useStore($localRepository);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const [authorized, setAuthorized] = useState(false);
  const [authorizedBy, setAuthorizedBy] = useState('');
  const [localPath, setLocalPath] = useState('');
  const [status, setStatus] = useState('ready');

  const canPick = authorized && authorizedBy.trim().length > 0;

  useEffect(() => {
    folderInputRef.current?.setAttribute('webkitdirectory', '');
    folderInputRef.current?.setAttribute('directory', '');

    fetch('/__local/repository-default')
      .then((response) => response.ok ? response.json() : null)
      .then((body: { path?: string } | null) => {
        if (body?.path) {
          setLocalPath(body.path);
        }
      })
      .catch(() => undefined);
  }, []);

  async function scanLocalPath(pathToScan = localPath) {
    if (!canPick) {
      setStatus('enter name and confirm authority');
      return;
    }
    if (!pathToScan.trim()) {
      setStatus('enter local repository path');
      return;
    }

    setStatus('scanning local path');
    try {
      const response = await fetch('/__local/repository-scan', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ path: pathToScan.trim() }),
      });
      const body = await response.json() as LocalPathScanResponse | { error?: string; message?: string };
      if (!response.ok || !('manifestLines' in body)) {
        setStatus(('message' in body && body.message) ? body.message : 'local path scan failed');
        return;
      }
      await registerRepository(body);
    } catch {
      setStatus('local dev scan endpoint unavailable');
    }
  }

  async function chooseRepositoryFromFiles(event: ChangeEvent<HTMLInputElement>) {
    if (!canPick) {
      setStatus('enter name and confirm authority');
      return;
    }

    const files = event.currentTarget.files;
    if (!files || files.length === 0) {
      setStatus('folder selection cancelled');
      return;
    }

    setStatus('scanning browser selection');
    const { repositoryName, scan } = scanFileList(files);
    await registerRepository({
      name: repositoryName,
      path: repositoryName,
      primaryStack: detectStack(scan.detectedFiles),
      ...scan,
    });
    event.currentTarget.value = '';
  }

  async function registerRepository(scan: LocalPathScanResponse) {
    const manifestSha256 = await digestManifest(scan.manifestLines);
    const repository: LocalRepositoryContext = {
      name: scan.name,
      authorizedBy: authorizedBy.trim(),
      authorizedAt: new Date().toISOString(),
      fileCount: scan.fileCount,
      totalBytes: scan.totalBytes,
      manifestSha256,
      detectedFiles: scan.detectedFiles,
      primaryStack: scan.primaryStack,
      localOnly: true,
    };
    setLocalRepositoryContext(repository);
    setLocalPath(scan.path);
    setStatus('local repository selected');
  }

  return (
    <section className="local-intake" aria-labelledby="local-intake-title">
      <div>
        <h2 id="local-intake-title">[ LOCAL REPOSITORY ]</h2>
        <p className="detail">
          Bind code on this computer. The scan maps metadata locally and does not upload source.
        </p>
      </div>

      <div className="local-intake-controls">
        <label className="text-field">
          <span>HUMAN</span>
          <input
            type="text"
            value={authorizedBy}
            onChange={(event) => setAuthorizedBy(event.target.value)}
            placeholder="name"
          />
        </label>
        <label className="text-field">
          <span>LOCAL PATH</span>
          <input
            type="text"
            value={localPath}
            onChange={(event) => setLocalPath(event.target.value)}
            placeholder="/Users/name/path/to/repository"
          />
        </label>
        <label className="check-field">
          <input
            type="checkbox"
            checked={authorized}
            onChange={(event) => setAuthorized(event.target.checked)}
          />
          <span>I own this code or am authorized to run local analysis on it.</span>
        </label>
        <button type="button" onClick={() => scanLocalPath()}>
          [ DEV PATH SCAN ]
        </button>
        <label className="local-folder-input">
          <span>[ BROWSER FOLDER FALLBACK ]</span>
          <input ref={folderInputRef} type="file" multiple data-folder-picker="directory" onChange={chooseRepositoryFromFiles} />
        </label>
      </div>

      <dl className="local-repo-summary">
        <div><dt>STATUS</dt><dd>{status}</dd></div>
        <div><dt>REPOSITORY</dt><dd>{localRepository?.name ?? 'not scanned'}</dd></div>
        <div><dt>STACK</dt><dd>{localRepository?.primaryStack ?? 'scan required'}</dd></div>
        <div><dt>FILES</dt><dd>{localRepository ? formatCount(localRepository.fileCount) : 'not mapped'}</dd></div>
        <div><dt>BYTES</dt><dd>{localRepository ? formatBytes(localRepository.totalBytes) : 'not measured'}</dd></div>
        <div><dt>MANIFEST</dt><dd>{localRepository?.manifestSha256.slice(0, 12) ?? 'not created'}</dd></div>
      </dl>
    </section>
  );
}

function applyScanFile(result: ScanResult, path: string, file: File): void {
  const basename = path.split('/').at(-1) ?? path;
  result.fileCount += 1;
  result.totalBytes += file.size;
  result.manifestLines.push(`${path}:${file.size}:${file.lastModified}`);
  if (basename in stackMarkers || path === 'src/main.rs' || path.endsWith('.c') || path.endsWith('.cpp')) {
    result.detectedFiles.push(path);
  }
}

function scanFileList(files: FileList): { repositoryName: string; scan: ScanResult } {
  const result: ScanResult = {
    fileCount: 0,
    totalBytes: 0,
    detectedFiles: [],
    manifestLines: [],
  };
  const localFiles = Array.from(files);
  const firstPath = localFiles.find((file) => file.webkitRelativePath)?.webkitRelativePath ?? '';
  const repositoryName = firstPath.split('/').filter(Boolean)[0] ?? 'selected-local-code';

  for (const file of localFiles) {
    const relativePath = file.webkitRelativePath || file.name;
    const segments = relativePath.split('/').filter(Boolean);
    const pathSegments = segments[0] === repositoryName ? segments.slice(1) : segments;
    if (pathSegments.slice(0, -1).some((segment) => ignoredDirectories.has(segment))) {
      continue;
    }

    const path = pathSegments.join('/') || file.name;
    applyScanFile(result, path, file);
    if (result.fileCount >= 5000) {
      break;
    }
  }

  result.detectedFiles.sort();
  result.manifestLines.sort();
  return { repositoryName, scan: result };
}

async function digestManifest(lines: string[]): Promise<string> {
  const bytes = new TextEncoder().encode(lines.join('\n'));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

function detectStack(detectedFiles: string[]): string {
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

function formatCount(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${Math.round(value / 1024)} KiB`;
  }
  return `${Math.round(value / (1024 * 1024))} MiB`;
}
